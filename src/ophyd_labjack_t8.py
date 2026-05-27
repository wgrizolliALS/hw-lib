import csv
import time
import threading
import numpy as np
from datetime import datetime
from ophyd import Device, Signal
from labjack import ljm


def _channel_number(ch, prefix="AIN"):
    """
    Normalize channel identifiers to integer indices.

    Parameters
    ----------
    ch : iterable
        Channel identifiers as integers, floats, or strings (e.g., ``'AIN0'``).
    prefix : str, optional
        Prefix to strip from string identifiers. Default is ``'AIN'``.

    Returns
    -------
    list of int
        Integer channel indices.
    """
    return [int(c) if isinstance(c, (int, float)) else int(str(c).upper().replace(prefix, "")) for c in ch]


def _channel_name(ch_n, prefix="AIN"):
    """
    Convert integer channel indices to canonical register names.

    Parameters
    ----------
    ch_n : iterable of int
        Integer channel indices.
    prefix : str, optional
        Prefix for channel names. Default is ``'AIN'``.

    Returns
    -------
    list of str
        Channel names (e.g., ``['AIN0', 'AIN1']``).
    """
    return [f"{prefix}{n}" for n in ch_n]


class LabJackT8(Device):
    """
    A self-contained Ophyd device for the LabJack T8.

    Notes
    -----
    Provides hardware connection via LJM, asynchronous triggering (threading),
    per-channel mean computation for Bluesky, optional raw CSV logging, and
    optional per-channel waveform signal recording.

    Parameters
    ----------
    name : str
        The name of the device for Ophyd/Bluesky.
    AI_channels : list[int] | list[str] | int | str | None, optional
        AIN channel indices or names to read (e.g., ``[0, 1]`` or
        ``['AIN0', 'AIN1']``). Defaults to ``[0]``.
    handle : int | None, optional
        An existing open LJM handle. If ``None``, a new connection is opened.
    acq_time : float, optional
        The duration of the stream acquisition in seconds. Default is 0.5s.
    sample_rate : float, optional
        The sampling frequency in Hz. Default is 20.0 Hz.
    connectionType : str, optional
        LJM connection type (e.g., "USB", "ETHERNET", "ANY").
    identifier : str, optional
        LJM identifier (e.g., "ANY", or a specific serial number).
    save_raw_to_csv : bool, optional
        If ``True``, saves raw waveform data to CSV during scans. Default is ``True``.
    csv_fname : str | None, optional
        Filename for the raw data CSV export. If ``None``, a timestamped name
        is generated automatically each time a scan starts. Any value provided
        here is used as-is; it is not regenerated between scans unless reset
        to ``None``.
    verbose : bool, optional
        If ``True``, print connection and status messages. Default is ``False``.
    verbose_stream : bool, optional
        If ``True``, print per-acquisition start/stop messages. Default is ``False``.
    enable_waveforms : bool, optional
        If ``True``, exposes per-channel waveform signals and a shared time
        vector. Default is ``False``.
    ranges : dict | None, optional
        Backwards-compatible per-channel range settings. Keys may be channel
        integers (e.g. `0`) or channel name strings (e.g. `'AIN0'` or
        `'AIN0_RANGE'`). Values are numeric and will be written to the
        corresponding `AIN#_RANGE` register on device initialization.
        Values for T8 model are: ±11 V, ±9.6 V, ±4.8 V, ±2.4 V, ±1.2 V,
        ±0.6 V, ±0.3 V, ±0.15 V, ±0.075 V, ±0.036 V, ±0.018 V. See T8 documentation
        at https://support.labjack.com/docs/14-3-2-analog-inputs-t8-t-series-datasheet
    writes : dict | None, optional
        Generic register writes to apply at initialization. Keys are the
        LJM register names (strings) and values are numeric. Useful for
        setting arbitrary device registers (including `AIN#_RANGE`).
    writes_raise : bool, optional
        If True, any failure performing the ``writes`` register writes will
        raise a ``RuntimeError`` and abort initialization. If False (default),
        failures are logged as warnings and initialization continues. Failures
        in ``ranges`` writes are always logged, never raised.
    Examples
    --------
    - Set per-channel ranges (legacy style):

        LabJackT8('t8', AI_channels=[0,1], ranges={0: 10, 'AIN1': 2.44})

    - Generic register writes (recommended for arbitrary registers):

        LabJackT8('t8', writes={'AIN0_RANGE': 10, 'DIO0_EF_CLOCK0_ENABLE': 1})
    """

    def __init__(
        self,
        name,
        active_AI_channels: list[int] | list[str] | None = None,
        handle: int | None = None,
        acq_time: float = 0.5,
        sample_rate: float = 20.0,
        connectionType: str = "ANY",
        identifier: str = "ANY",
        save_raw_to_csv: bool = True,
        csv_fname: str | None = None,
        verbose: bool = False,
        verbose_stream: bool = False,
        enable_waveforms: bool = False,
        ranges: dict | None = None,
        writes: dict | None = None,
        writes_raise: bool = False,
        **kwargs,
    ):

        super().__init__(name=name, **kwargs)

        # Accept scalar AI_channels (int/str) or iterable; normalize to list
        if active_AI_channels is None:
            active_AI_channels = [0]
        elif not isinstance(active_AI_channels, (list, tuple)):
            active_AI_channels = [active_AI_channels]

        self.handle_info = None
        self._ljm_ready = False
        # AI channel configuration (prepare for other channel types like DAC later)
        # `AI_channels` accepts ints or string names like 'AIN0' on input
        # normalized integer indices for AI channels
        self.AI_channels_n = _channel_number(active_AI_channels)
        self.AI_channels_name = _channel_name(self.AI_channels_n)
        self.channel_names = list(self.AI_channels_name)

        self.save_raw_to_csv = save_raw_to_csv
        self._scan_results = []
        self._raw_block_for_csv = None  # Only for CSV saving, not exposed as a Signal
        # Add per-channel waveform signals
        self._waveform_signals = {}
        self._waveform_time_signal = None
        self._record_waveform_signals = enable_waveforms
        self._ch_map = {}
        self._hint_fields = []
        self._csv_file = None
        self._csv_writer = None
        self.csv_fname = csv_fname

        self.verbose = verbose
        self.verbose_stream = verbose_stream

        # Backwards-compatible ranges dict and generic writes dict
        self.AI_ranges = {}
        self.AI_actual_range = {}

        if ranges is not None:
            # Normalize provided range keys to canonical 'AIN{n}' and ensure float values
            for key, val in ranges.items():
                # determine integer index using helper behaviour
                if isinstance(key, (int, float)):
                    ch_n = int(key)
                elif isinstance(key, str):
                    k = key.upper().replace("_RANGE", "")
                    if k.startswith("AIN"):
                        ch_n = int(k.replace("AIN", ""))
                    else:
                        ch_n = int(k)
                else:
                    raise ValueError(f"Invalid AI channel: {key}")

                key_name = f"AIN{ch_n}"
                try:
                    self.AI_ranges[key_name] = float(val) if val is not None else None
                except (TypeError, ValueError):
                    raise ValueError(f"Invalid range value for {key_name}: {val}")
                self.AI_actual_range[key_name] = None

            # Ensure all configured channels appear in AI_ranges (fill missing with None)
            for _ch_name in self.channel_names:
                if _ch_name not in self.AI_ranges:
                    self.AI_ranges[_ch_name] = None
                    self.AI_actual_range[_ch_name] = None

        self.writes = writes or {}
        self.writes_raise = bool(writes_raise)

        self.acq_time = acq_time
        self.sample_rate = sample_rate
        self.last_scan_actual_rate = None

        for ch in self.AI_channels_name:
            # Scalar signal (mean)
            full_name = f"{name}_{ch.lower()}"
            sig = Signal(name=full_name, kind="hinted")  # type: ignore
            setattr(self, ch, sig)
            self._ch_map[ch] = sig
            self._hint_fields.append(full_name)
            # Waveform signal (optional)
            if self._record_waveform_signals:
                wf_name = f"{name}_{ch.lower()}_waveform"
                wf_sig = Signal(name=wf_name, kind="normal")  # type: ignore
                setattr(self, f"{ch}_waveform", wf_sig)
                self._waveform_signals[ch] = wf_sig
        # Only one time vector for all channels
        if self._record_waveform_signals:
            wf_time_name = f"{name}_waveform_time"
            wf_time_sig = Signal(name=wf_time_name, kind="normal")  # type: ignore
            setattr(self, "waveform_time", wf_time_sig)
            self._waveform_time_signal = wf_time_sig

        from labjack import ljm

        try:
            print("[INFO] Connecting to LabJack T8...")
            self.handle = handle or ljm.openS("T8", connectionType, identifier)
            print("[INFO] Connected!")
            self.ljm_module = ljm
            self._ljm_ready = True
            if self.verbose:
                print("[STATUS] Successfully Connected to LabJack T8")
                info = ljm.getHandleInfo(self.handle)
                self.handle_info = info
                print(
                    f"[INFO] Connected Device: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}\n"
                )
            # Apply `ranges` and `writes` using the wrapper helpers so error handling
            # and verification are centralized. `set_AI_range` will perform optional
            # readback verification; here we skip verification to keep init fast,
            # but respect `writes_raise` for raising on failure.
            # Apply configured ranges and writes. Let helper methods manage errors
            # (they accept flags to raise or log failures).
            # Apply configured ranges: normalize keys and use canonical AI names
            for key_name, v in (self.AI_ranges or {}).items():
                if v is None:
                    continue

                actual_range = self.set_AI_range(key_name, float(v))
                # store under canonical name
                self.AI_actual_range[key_name] = actual_range
                if self.verbose:
                    print(f"[INFO] Set AIN range {key_name} = {v}")

            for name, val in (self.writes or {}).items():
                self.eWriteName(str(name), float(val), raise_on_fail=self.writes_raise)
                if self.verbose:
                    print(f"[INFO] Wrote {name} = {val}")
        except Exception as e:
            self.close()
            raise RuntimeError(f"[ERROR] LJM Connection FAILED: {e}")

    @property
    def hints(self):
        return {"fields": self._hint_fields}

    def trigger(self):
        """
        Start an asynchronous stream acquisition from the LabJack T8.

        Acquires a block of samples, computes per-channel means, and stores
        waveforms and a shared time vector if ``enable_waveforms`` was set at
        construction. The raw block is held in ``_raw_block_for_csv`` for
        optional CSV export.

        Returns
        -------
        ophyd.status.DeviceStatus
            Status object that resolves when the acquisition thread completes.
        """
        scan_rate = self.sample_rate
        scans_per_read = int(scan_rate * self.acq_time)

        def _worker():
            if self.verbose_stream:
                print(f"[INFO] {datetime.now()}: Acquisition STARTED.")
            try:
                aAddresses = self.ljm_module.namesToAddresses(len(self.AI_channels_name), self.AI_channels_name)[0]
                actual_rate = self.ljm_module.eStreamStart(
                    self.handle, scans_per_read, len(aAddresses), aAddresses, scan_rate
                )
                self.last_scan_actual_rate = actual_rate
                ret = self.ljm_module.eStreamRead(self.handle)
                raw_data = ret[0]
                self.ljm_module.eStreamStop(self.handle)

                num_channels = len(self.AI_channels_name)
                reshaped = np.array(raw_data).reshape(-1, num_channels)
                t0 = time.time() - self.acq_time
                n_samples = reshaped.shape[0]
                # Preallocate buffer: first col = timestamp, remaining = channels
                samples = np.empty((n_samples, num_channels + 1), dtype=float)
                samples[:, 0] = t0 + (np.arange(n_samples) / actual_rate)
                # Ensure numeric type for channel data
                samples[:, 1:] = reshaped.astype(float)

                # Scalar (mean) and waveform per channel
                for i, ch in enumerate(self.AI_channels_name):
                    avg = np.mean(reshaped[:, i])
                    self._ch_map[ch].put(avg)
                    # Store waveform as 1D array (fixed shape) if enabled
                    if self._record_waveform_signals and ch in self._waveform_signals:
                        waveform = np.asarray(reshaped[:, i], dtype=float)
                        self._waveform_signals[ch].put(waveform)
                # Store time vector ONCE for all channels
                if self._record_waveform_signals and self._waveform_time_signal is not None:
                    time_vector = np.array([t0 + (j / actual_rate) for j in range(reshaped.shape[0])], dtype=float)
                    self._waveform_time_signal.put(time_vector)

                # Only build and store the raw sample block if needed for
                # waveform Signals or CSV saving to avoid unnecessary work
                # and memory use when those features are disabled.
                if self._record_waveform_signals or self.save_raw_to_csv:
                    # `samples` is already a numeric numpy array
                    self._raw_block_for_csv = samples

                if self.verbose_stream:
                    print(f"[INFO] {datetime.now()}: Acquisition FINISHED.")
                    print(
                        f"[INFO] Acquired {len(reshaped)} samples from {num_channels} channels at {actual_rate:} Hz.\n"
                    )

            except Exception as e:
                print(f"[STREAM ERROR] : {e}")
                try:
                    self.ljm_module.eStreamStop(self.handle)
                except Exception as stop_e:
                    print(f"[STREAM ERROR] Failed to stop stream: {stop_e}")

        from ophyd.status import DeviceStatus

        status = DeviceStatus(self)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _check_done():
            thread.join()
            status.set_finished()

        threading.Thread(target=_check_done, daemon=True).start()
        return status

    def read(self):
        """
        Return the current signal values from all configured channels.

        Includes per-channel mean values and, if ``enable_waveforms`` is
        ``True``, per-channel waveform arrays and the shared time vector.
        Also exposes the last raw acquisition block under the key
        ``<name>_raw_block`` for backward compatibility.

        Returns
        -------
        dict
            Mapping of signal name to ``{'value': ..., 'timestamp': ...}``
            entries as returned by each :class:`~ophyd.Signal`.
        """
        res = super().read()
        for sig in self._ch_map.values():
            res.update(sig.read())
        # Add per-channel waveform signals if enabled
        if self._record_waveform_signals:
            for wf_sig in self._waveform_signals.values():
                res.update(wf_sig.read())
            if self._waveform_time_signal is not None:
                res.update(self._waveform_time_signal.read())  # type: ignore
        # Expose temporary raw block for convenience (matches older behaviour
        # used by some examples). This is not persisted to the event stream;
        # it's a transient view of the last acquired block.
        if self._raw_block_for_csv is not None:
            key = f"{self.name}_raw_block"
            # Provide a minimal read dict with a `value` entry to match legacy
            # code that indexes `readings["..._raw_block"]["value"]`.
            res[key] = {"value": self._raw_block_for_csv}  # type: ignore
        return res

    def describe(self):
        """
        Return metadata describing the signals produced by this device.

        Includes per-channel mean signal descriptors and, if
        ``enable_waveforms`` is ``True``, per-channel waveform and time vector
        descriptors with shape information.

        Returns
        -------
        dict
            Mapping of signal name to descriptor dicts compatible with
            the Bluesky event model.
        """
        res = super().describe()
        scans_per_read = int(self.sample_rate * self.acq_time)
        for sig in self._ch_map.values():
            res.update(sig.describe())
        # Add per-channel waveform signal descriptions if enabled
        if self._record_waveform_signals:
            for i, ch in enumerate(self.AI_channels_name):
                wf_key = f"{self.name}_{ch.lower()}_waveform"
                res[wf_key] = {  # type: ignore
                    "source": f"LabJackT8 {ch} waveform",
                    "dtype": "number",
                    "shape": (scans_per_read,),
                }
            # Only one time vector for all channels
            wf_time_key = f"{self.name}_waveform_time"
            res[wf_time_key] = {  # type: ignore
                "source": "LabJackT8 waveform time",
                "dtype": "number",
                "shape": (scans_per_read,),
            }
        return res

    def csv_saver(self, name, doc):
        """
        Bluesky document callback for saving raw waveform data to CSV.

        Handles ``'start'``, ``'event'``, and ``'stop'`` documents. On
        ``'start'``, opens a CSV file using ``self.csv_fname`` if set, or
        generates a timestamped filename otherwise. Appends rows on each
        ``'event'`` and closes the file on ``'stop'``. Has no effect when
        ``save_raw_to_csv`` is ``False``, so it is safe to subscribe
        unconditionally.

        Output columns: ``Time``, ``motor``, then one column per configured
        AIN channel.

        Parameters
        ----------
        name : str
            Bluesky document type (``'start'``, ``'event'``, or ``'stop'``).
        doc : dict
            The Bluesky document payload.
        """
        if not self.save_raw_to_csv:
            return

        if name == "start":
            self._scan_results.clear()
            if self.csv_fname is None:
                self.csv_fname = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            try:
                self._csv_file = open(self.csv_fname, "w", newline="", encoding="utf-8")
            except Exception as e:
                print(f"[CSV ERROR] Could not open file {self.csv_fname}: {e}")
                self._csv_file = None
                self._csv_writer = None
                return
            fieldnames = ["Time", "motor"] + self.AI_channels_name
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fieldnames)
            self._csv_writer.writeheader()

        elif name == "event":
            m_pos = doc.get("data", {}).get("motor", 0.0)
            raw_data = self._raw_block_for_csv if self._raw_block_for_csv is not None else []
            for sample in raw_data:
                row = {
                    "Time": datetime.fromtimestamp(sample[0]).strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "motor": m_pos,
                }
                for i, ch_name in enumerate(self.AI_channels_name):
                    row[ch_name] = sample[i + 1]
                self._scan_results.append(row)
                if self._csv_writer:
                    try:
                        self._csv_writer.writerow(row)
                    except Exception as e:
                        print(f"[CSV ERROR] Could not write row: {e}")
            if self._csv_file:
                try:
                    self._csv_file.flush()
                except Exception as e:
                    print(f"[CSV ERROR] Could not flush file: {e}")
            self._raw_block_for_csv = None  # Clear after use

        elif name == "stop":
            if self._csv_file:
                try:
                    self._csv_file.close()
                except Exception as e:
                    print(f"[CSV ERROR] Could not close file: {e}")
                print(f"\n[CSV] Saved {len(self._scan_results)} rows to {self.csv_fname}")
                self._csv_file = None

    def close(self):
        """
        Close the LJM connection to the LabJack device.

        Safe to call even if the device was never successfully connected.
        """
        if hasattr(self, "handle") and self.handle:
            self.ljm_module.close(self.handle)
            print("[INFO] LabJack connection closed.")

    def eWriteName(self, name, value, raise_on_fail: bool = False):
        """
        Write a value to a named LabJack register via LJM.

        Parameters
        ----------
        name : str
            LJM register name (e.g., ``'AIN0_RANGE'`` or
            ``'DIO0_EF_CLOCK0_ENABLE'``).
        value : float
            Value to write to the register.
        raise_on_fail : bool, optional
            If ``True``, propagate exceptions from the underlying LJM call.
            If ``False`` (default), catch and log errors without raising.
        """
        if raise_on_fail:
            self.ljm_module.eWriteName(self.handle, str(name), float(value))
            if self.verbose:
                print(f"[INFO] eWriteName: Wrote {name} = {value}")
            return

        try:
            self.ljm_module.eWriteName(self.handle, str(name), float(value))
            if self.verbose:
                print(f"[INFO] eWriteName: Wrote {name} = {value}")
        except Exception as e:
            print(f"[ERROR] eWriteName failed for {name} -> {value}: {e}")

    def eReadName(self, name, raise_on_fail: bool = False) -> float | None:
        """
        Read a single named LabJack register via LJM.

        Parameters
        ----------
        name : str
            LJM register name to read (e.g., ``'AIN0_RANGE'``).
        raise_on_fail : bool, optional
            If ``True``, raise a :exc:`RuntimeError` on failure.
            If ``False`` (default), print the error and return ``None``.

        Returns
        -------
        float or None
            Register value on success, or ``None`` if the read fails and
            ``raise_on_fail`` is ``False``.

        Raises
        ------
        RuntimeError
            If the LJM read fails and ``raise_on_fail`` is ``True``.
        """
        try:
            val = self.ljm_module.eReadName(self.handle, str(name))
            # ljm.eReadName may return a single value or a tuple; handle both
            if isinstance(val, (list, tuple)) and len(val) == 1:
                val = val[0]
            if self.verbose:
                print(f"[INFO] eReadName: Read {name} = {val}")
            return val
        except Exception as e:
            msg = f"[ERROR] eReadName failed for {name}: {e}"
            if raise_on_fail:
                raise RuntimeError(msg)
            print(msg)
            return None

    def set_AI_range(
        self,
        channel,
        value: float,
        delay: float = 0.05,
    ):
        """
        Set the voltage range for a single AIN channel.

        Writes the ``AIN#_RANGE`` register, waits for the specified settling
        delay, reads back the actual value, and stores it in
        ``AI_actual_range``.

        Parameters
        ----------
        channel : int or str
            Channel to configure. Accepts an integer index (``0``), a
            canonical name (``'AIN0'``), or a register name
            (``'AIN0_RANGE'``).
        value : float
            Desired range value in volts (e.g., ``10.0`` for ±10 V).
        delay : float, optional
            Seconds to wait before reading back the register for settling.
            Default is ``0.05``.

        Returns
        -------
        float or None
            The readback value from the device after the write, or ``None``
            if the readback fails.

        Raises
        ------
        ValueError
            If *channel* cannot be parsed to a valid channel index.
        """
        # Normalize channel to canonical AIN name (e.g., 'AIN0')
        if isinstance(channel, int):
            ch_n = int(channel)
        elif isinstance(channel, str):
            # allow either 'AIN0' or '0'
            ch_str = channel.upper().replace("_RANGE", "")
            if ch_str.startswith("AIN"):
                ch_n = int(ch_str.replace("AIN", ""))
            else:
                ch_n = int(ch_str)
        else:
            raise ValueError(f"Invalid channel type: {type(channel)}")

        key = f"AIN{ch_n}"
        reg = f"{key}_RANGE"

        # perform the write (wrapper handles logging/errors)
        self.eWriteName(reg, float(value), raise_on_fail=False)
        # store configured value under canonical key
        self.AI_ranges[key] = float(value)

        if self.verbose:
            print(f"[INFO] Set Range: {reg} = {value:.6f}")

        time.sleep(float(delay))
        readback = self.eReadName(reg, raise_on_fail=False)
        if self.verbose:
            print(f"[INFO] Actual Range: {reg} = {readback:.6f}")
        # record actual/readback value under canonical key
        self.AI_actual_range[key] = readback
        return readback


# ---------------------------------------------------------------------------
# Module-level helpers (moved here so ophyd device is self-contained)
# ---------------------------------------------------------------------------


def detect_labjacks(verbose: bool = False):
    """
    Scan for connected LabJack devices using LJM.

    Parameters
    ----------
    verbose : bool, optional
        If ``True``, print a formatted device list via
        :func:`print_devices`. Default is ``False``.

    Returns
    -------
    list of dict
        One dict per discovered device with keys ``'type'``,
        ``'connection'``, ``'serial number'``, and ``'ip'``.
    """
    devices = []
    try:
        res = ljm.listAllS("ANY", "ANY")
        num = res[0]
        for i in range(num):
            devices.append(
                {
                    "type": res[1][i],
                    "connection": res[2][i],
                    "serial number": res[3][i],
                    "ip": ljm.numberToIP(res[4][i]),
                }
            )
    except Exception as e:
        print(f"[ERROR] detect_labjacks failed: {e}")
    finally:
        if verbose:
            print_devices(devices)

    return devices


def print_devices(devices):
    """
    Print a formatted table of detected LabJack devices.

    Parameters
    ----------
    devices : list of dict
        Device info dicts as returned by :func:`detect_labjacks`.
    """

    if not devices:
        print("[INFO]: No LabJack devices found.")
        return

    print(f"[INFO] detect_labjacks: found {len(devices)} device(s)")
    connection_map = {1: "USB", 2: "ETH", 3: "Wireless"}
    for idx, dev in enumerate(devices):
        conn_name = connection_map.get(dev["connection"], f"Unknown({dev['connection']})")
        port_info = f", Port: {dev['port']}" if dev.get("port") else ""
        usb_info = f", USB Address: {dev['usb_address']}" if dev.get("usb_address") else ""
        print(
            f"[{idx}] Device type: {dev['type']}, Connection: {conn_name}, Serial: {dev['serial number']}, IP: {dev['ip']}{port_info}{usb_info}"
        )


def close_all_labjacks(verbose: bool = False):
    """
    Close all open LabJack LJM connections.

    Parameters
    ----------
    verbose : bool, optional
        If ``True``, print a confirmation message. Default is ``False``.
    """
    try:
        ljm.closeAll()
        if verbose:
            print("[INFO] Closed all LabJack connections")
    except Exception as e:
        print(f"[ERROR] close_all_labjacks: {e}")


def set_DAC_voltage(handle, channel, voltage):
    """
    Set a DAC channel to the specified voltage and return the readback.

    Parameters
    ----------
    handle : int
        Open LJM device handle.
    channel : int
        DAC channel index (e.g., ``0`` for DAC0).
    voltage : float
        Desired output voltage.

    Returns
    -------
    float or None
        Actual voltage read back from the device, or ``None`` on error.
    """
    try:
        ljm.eWriteName(handle, f"DAC{channel}", float(voltage))
        actual = ljm.eReadName(handle, f"DAC{channel}")
        return actual
    except Exception as e:
        print(f"[ERROR] set_DAC_voltage: {e}")
        return None


def set_channels_ranges(handle, num_channels=None, ranges=None, check_ranges=False):
    """
    Set AIN voltage ranges for multiple channels in batch.

    Parameters
    ----------
    handle : int
        Open LJM device handle.
    num_channels : iterable of int, optional
        Channel indices to configure. Defaults to ``range(8)``.
    ranges : dict or list, optional
        Desired range per channel. If a ``dict``, keys are channel indices
        mapping to range values. If a ``list``, values are applied in the
        order of *num_channels*. Defaults to ``10`` V for all channels.
    check_ranges : bool, optional
        If ``True``, read back each range after writing via
        :func:`get_channels_ranges`. Default is ``False``.
    """
    if num_channels is None:
        num_channels = range(8)
    if ranges is None:
        ranges = {idx: 10 for idx in num_channels}
    for idx in num_channels:
        try:
            val = ranges[idx] if isinstance(ranges, dict) else ranges[list(num_channels).index(idx)]
            ljm.eWriteName(handle, f"AIN{idx}_RANGE", float(val))
            if check_ranges:
                _ = get_channels_ranges(handle, num_channels=[idx])
        except Exception as e:
            print(f"[ERROR] set_channels_ranges AIN{idx}: {e}")


def get_channels_ranges(handle, num_channels=None):
    """
    Read AIN voltage ranges from the device for multiple channels.

    Parameters
    ----------
    handle : int
        Open LJM device handle.
    num_channels : iterable of int, optional
        Channel indices to read. Defaults to ``range(8)``.

    Returns
    -------
    dict
        Mapping of channel index to range value (float), or ``None`` for
        channels that could not be read.
    """
    if num_channels is None:
        num_channels = range(8)
    out = {}
    for idx in num_channels:
        try:
            out[idx] = ljm.eReadName(handle, f"AIN{idx}_RANGE")
        except Exception as e:
            print(f"[ERROR] get_channels_ranges AIN{idx}: {e}")
            out[idx] = None
    return out


def get_channel_resolution(handle):
    """
    Read the global AIN resolution index from the device (T8-specific).

    Parameters
    ----------
    handle : int
        Open LJM device handle.

    Returns
    -------
    int or None
        The ``AIN_ALL_RESOLUTION_INDEX`` register value, or ``None`` on
        error.
    """
    try:
        val = ljm.eReadName(handle, "AIN_ALL_RESOLUTION_INDEX")
        return int(val)
    except Exception as e:
        print(f"[ERROR] get_channel_resolution: {e}")
        return None


if __name__ == "__main__":
    # Quick self-test for developers: list devices, read ranges/resolution, then close
    print("[SELFTEST] Detecting connected LabJacks...")
    devs = detect_labjacks(verbose=True)
    if not devs:
        print("[SELFTEST] No devices found.")
    else:
        first = devs[0]
        print(f"[SELFTEST] First device: {first}")
        try:
            # Try opening by serial to read ranges/resolution
            h = ljm.openS("ANY", "ANY", first.get("serial number"))
            print("[SELFTEST] Reading channel ranges for AIN0-AIN3")
            ranges = get_channels_ranges(h, num_channels=[0, 1, 2, 3])
            print(f"[SELFTEST] Ranges: {ranges}")
            res = get_channel_resolution(h)
            print(f"[SELFTEST] Global resolution index: {res}")
            ljm.close(h)
        except Exception as e:
            print(f"[SELFTEST] Could not open/read device: {e}")
    print("[SELFTEST] Closing all LabJack connections (cleanup)")
    close_all_labjacks(verbose=True)
