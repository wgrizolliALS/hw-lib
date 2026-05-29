import serial
import serial.tools.list_ports

import time

import pandas as pd

from wg_toolkit.logprint import printc, print_info, print_warning, print_error, print_log, print_done, print_success  # type: ignore

from wg_toolkit.ports import serial_query  # type: ignore


def detect_keithley_devices(
    baudrate: int | None = 9600,
    timeout: float = 0.5,
    verbose: bool = False,
    debug: bool = False,
) -> list[dict]:
    """Scan available serial ports to identify Keithley instruments.

    For each detected port the function attempts to send `*IDN?` at the
    requested `baudrate`, or over a set of common baud rates if `baudrate` is
    None. Results are returned as a list of dictionaries describing each port
    and whether a valid IDN response was received.

    Args:
        baudrate: If provided, try only this baudrate; otherwise test common rates.
        timeout: Serial timeout used for low-level operations (seconds).
        verbose: Enable informational printing.
        debug: Enable debug printing.

    Returns:
        A list of device dictionaries describing each detected port.
    """
    found_devices = []
    ports = serial.tools.list_ports.comports()
    print_info(f"Detected {len(ports)} serial ports to scan.", verbose=verbose)
    printc(f"[DEBUG] : {ports = }", verbose=debug)

    common_baudrates = [9600, 19200, 38400, 57600, 115200]

    print_info("Loop ports and baudrates", verbose=verbose)
    for port in ports:
        baudrate_list = [baudrate] if baudrate is not None else common_baudrates

        print_info(f"Checking {port.device = }", verbose=verbose)
        for br in baudrate_list:
            try:
                # with serial.Serial(port.device, baudrate=br, timeout=timeout) as ser:
                # ser.write(b"*IDN?\n")
                # time.sleep(0.1)
                # response = ser.readline().decode(errors="ignore").strip()
                response = serial_query("*IDN?", port.device, baudrate=br, verbose=verbose, debug=debug)

                if response:
                    _mnfctr, _model, _sn, _frmwr = response.split(",")
                    found_devices.append(
                        {
                            "port": port.device,
                            "description": port.description,
                            "idn": response,
                            "manufacturer": _mnfctr,
                            "model": _model,
                            "serial_number": _sn,
                            "firmware": _frmwr,
                            "baudrate": br,
                            "is_keithley": "KEITHLEY" in response.upper(),
                            "status": "response",
                        }
                    )
                    break
                else:
                    found_devices.append(
                        {
                            "port": port.device,
                            "description": port.description,
                            "idn": "No response to *IDN?",
                            "baudrate": br,
                            "is_keithley": False,
                            "status": "no_idn",
                        }
                    )
                    break

            except Exception:  # Broad catch to handle any serial exceptions (port busy, permission issues, etc.)
                found_devices.append(
                    {
                        "port": port.device,
                        "description": port.description,
                        "idn": "Port busy or cannot open",
                        "baudrate": br,
                        "is_keithley": False,
                        "status": "busy",
                    }
                )
                break

    if verbose:
        print_keithley_devices(found_devices)
    return found_devices


def print_keithley_devices(devices: list[dict]):
    """Formats and prints the detected serial devices to the console."""
    if not devices:
        print_info("*** No serial devices detected on available serial ports ***")
        print_info("Please check your connections and try again.\n")
        return

    print_info(f"#### FOUND {len(devices)} SERIAL DEVICES ####")
    _n_keithleys = sum(1 for d in devices if d["is_keithley"])
    print_info(f"#### FOUND {_n_keithleys} KEITHLEY DEVICES ####\n")
    print("=" * 100)
    print(
        f"{'Port':<8} | {'Baudrate':<8} | {'Status':<15} | {'Manufacturer':<15} | {'Model':<15} | {'Serial Number':<15}"
    )
    print("-" * 100)
    for dev in devices:
        if dev["status"] == "response":
            status = "[✓] KEITHLEY" if dev["is_keithley"] else "[?] Response"
        elif dev["status"] == "no_idn":
            status = "[ ] No IDN"
        elif dev["status"] == "busy":
            status = "[!] Busy"
        elif dev["status"] == "decode_error":
            status = "[!] DecodeErr"
        else:
            status = "[?] Unknown"
        baudrate = dev.get("baudrate", "?")

        if dev["is_keithley"]:
            print(
                f"{dev['port']:<8} | {baudrate:<8} | {status:<15} | {dev['manufacturer'][0:14]:<15} | {dev['model']:<15} | {dev['serial_number']:<15}"
            )
        else:
            print(f"{dev['port']:<8} | {baudrate:<8} | {status:<15} | {'-':<15} | {'-':<15} | {'-':<15}")
    print("=" * 100, "\n")


def print_keithley_properties(dev: dict):
    """Prints the properties of a detected device in a readable format."""

    print("-" * 100)
    print(f"Port: {dev['port']}")
    print(f"Baudrate: {dev.get('baudrate', 'N/A')}")
    print(f"Description: {dev['description']}")
    if dev.get("status") == "response":
        print(f"IDN: {dev.get('idn', 'N/A')}")
    else:
        print(f"IDN: {dev.get('idn', 'N/A')} (No valid response)")
    if dev.get("is_keithley"):
        print(f"Manufacturer: {dev.get('manufacturer', 'N/A')}")
        print(f"Model: {dev.get('model', 'N/A')}")
        print(f"Serial Number: {dev.get('serial_number', 'N/A')}")
        print(f"Firmware: {dev.get('firmware', 'N/A')}")
    print("-" * 100, "\n")


class KeithleyPicoammeter:
    def __init__(
        self, port: str, baudrate: int = 9600, timeout: float = 0.5, verbose: bool = False, debug: bool = False
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.verbose = verbose
        self.debug = debug

    def query_and_check_batched(
        self,
        cmds: list,
        send_individually: bool = False,
        wait_between_cmds: float = 0.05,
        check_errors: bool = True,
    ) -> list[str] | None:
        """Send a batch of commands, optionally checking for errors after each one."""

        if self.debug:
            printc(
                f"[DEBUG] : Input batch of {len(cmds)} commands to send to {self.port}:\n" + "\n".join(cmds),
                color="purple",
            )

        if check_errors:
            _cmds_with_checks = []
            for _cmd in cmds:
                _cmds_with_checks.append(_cmd)
                _cmds_with_checks.append(":SYST:ERR?")

            cmds = _cmds_with_checks

        if not send_individually:
            _cmds_joint = ";".join(cmds)
            cmds = [_cmds_joint]

        if self.debug:
            printc(
                f"[DEBUG] : Sending batch of {len(cmds)} commands to {self.port}:\n" + "\n".join(cmds), color="purple"
            )

        res_list = []
        for _cmd in cmds:
            _res = serial_query(_cmd, self.port, self.baudrate, verbose=self.verbose, debug=self.debug)
            res_list.append(_res)
            if check_errors:
                time.sleep(wait_between_cmds)
                self.check_inst_errors()
                time.sleep(wait_between_cmds)

        return res_list

    def query_and_check(
        self,
        cmd: str,
        wait_between_cmds: float = 0.05,
        check_errors: bool = True,
        verbose: bool | None = None,
        debug: bool | None = None,
    ) -> str | None:
        """Send a single query command then optionally check the instrument error queue.

        This is a thin wrapper around `serial_query` that performs an optional
        error-checking step (`:SYST:ERR?`) after the query to surface instrument
        errors to the user.

        Args:
            cmd: Query string to send.
            port: Serial device path.
            verbose: Enable informational printing.
            debug: Enable debug printing.
            wait_between_cmds: Seconds to sleep before/after error checking.
            check_errors: If True, call `check_inst_errors` after the query.

        Returns:
            The response string from the device, or `None` on error.
        """

        if verbose is None:
            verbose = self.verbose
        if debug is None:
            debug = self.debug

        _res = serial_query(cmd, self.port, verbose=verbose, debug=debug)
        if check_errors:
            time.sleep(wait_between_cmds)
            self.check_inst_errors()
            time.sleep(wait_between_cmds)
        return _res

    def check_inst_errors(self):
        """Poll the instrument error queue and print any non-zero errors.

        Repeatedly queries `:SYST:ERR?` until the instrument reports `0,` (no error).

        Args:
            port: Serial device path.
            verbose: Enable informational printing.
            debug: Enable debug printing.
        """
        while True:
            print_log("[DEBUG] Checking instrument error queue...", verbose=self.debug)
            err = serial_query(":SYST:ERR?", self.port, verbose=self.debug, debug=self.debug)
            if err is None or err.startswith("0,") or err == "":
                print_log("No instrument errors detected.", verbose=self.debug)
                break
            print_error(f"INSTR ERROR: {err}", verbose=self.debug)

    def wait_operation_complete(self, poll_interval: float = 0.1, timeout=1.0):
        """Wait for the instrument to report operation complete via `*OPC?`.

        This repeatedly queries `*OPC?` until it returns `1` or a timeout occurs.

        Args:
            poll_interval: Seconds to wait between polling attempts.
            timeout: Maximum time to wait for operation complete.
        Returns:
            True if operation complete was received, False on timeout or error.
        """

        _start_acq_time = time.time()
        poll_interval = 0.1  # seconds

        while time.time() - _start_acq_time < timeout:
            print_log(
                f"Waiting for operation to complete... time elapsed: {time.time() - _start_acq_time:.2f}s",
            )

            opc_resp = self.query_and_check("*OPC?", verbose=False, debug=False)
            if opc_resp == "1":
                print_done(
                    f"Operation complete received from {self.port} after {time.time() - _start_acq_time:.2f}s",
                )

                return

            time.sleep(poll_interval)

        raise TimeoutError(f"Timeout waiting for operation complete on {self.port} after {timeout} seconds")

    def reset_instrument(self):
        """Reset instrument to a known state."""
        print_log("Resetting instrument...", verbose=self.verbose)
        _start_t = time.time()
        cmds = [
            "*RST",  # Reset to known state
            ":SYST:REM",  # Remote mode for faster serial response; comment out if you want to use front panel after this
            ":FORM:ELEM READ,TIME",  # Set Format.
            ":SYST:TIME:RESET",  # Reset internal clock to 0:00:00 for consistent timestamps
        ]  # Reset to known state, then remote mode for faster serial response
        self.query_and_check_batched(cmds)
        print_log(f"Reset complete. Time elapsed: {time.time() - _start_t:.2f} s", verbose=self.verbose)

        return True

    def reset_timer(self):
        return self.query_and_check(":SYST:TIME:RESET")

    def is_autorange_ON(self) -> bool:
        """Query autorange status."""

        print_log("Checking autorange status...", verbose=self.verbose)

        _resp = self.query_and_check(":SENS:CURR:RANG:AUTO?")
        autorange_status = _resp.strip() if _resp is not None else None

        if autorange_status is not None and autorange_status == "0":
            print_log("Autorange status: OFF", verbose=self.verbose)
            return False
        else:
            print_log("Autorange status: ON", verbose=self.verbose)
            return True

    def set_autorange(self, enable: bool = True) -> bool:
        """Enable or disable autorange."""
        if enable:
            print_log("Enabling autorange...", verbose=self.verbose)
            self.query_and_check(":SENS:CURR:RANG:AUTO ON")
        else:
            print_log("Disabling autorange...", verbose=self.verbose)
            self.query_and_check(":SENS:CURR:RANG:AUTO OFF")

        return self.is_autorange_ON()

    def get_curr_range(self) -> float:
        """Query current range."""
        if self.is_autorange_ON():
            return -9999.00  # sentinel value to indicate autorange is ON and numeric range is not fixed
        else:
            print_log("Autorange is OFF, querying current range...", verbose=self.verbose)
            _resp = self.query_and_check(":SENS:CURR:RANG?")
            if _resp is None:
                print_warning(
                    "Received empty response when querying current range. Returning None.", verbose=self.verbose
                )
                raise RuntimeError("Failed to query current range; received empty response.")
            curr_range = float(_resp.strip())
            print_log(f"Current range: {curr_range}", verbose=self.verbose)
            return curr_range

    def get_curr_NPLC(self) -> float:
        """Query current NPLC."""
        print_log("Querying current NPLC...", verbose=self.verbose)
        _resp = self.query_and_check(":SENS:CURR:NPLC?")
        if _resp is None:
            print_warning("Received empty response when querying current NPLC. Returning None.", verbose=self.verbose)
            raise RuntimeError("Failed to query current NPLC; received empty response.")
        curr_nplc = float(_resp.strip())
        print_log(f"Current NPLC: {curr_nplc}", verbose=self.verbose)
        return curr_nplc

    def set_range(self, set_curr_range: float | None = None, nplc: float = 1.0) -> tuple[float, float]:
        """
        Enable autorange briefly so the instrument selects a range, read one measurement,
        query the selected range, then lock it and return numeric range.

        AUTORRANGE IS ALWAYS OFF AFTER THIS FUNCTION.
        """
        print_log("Starting autorange selection...", verbose=self.verbose)
        _start_t = time.time()

        cmds = [
            ":SYST:ZCH OFF",  # turn off zero check for faster readings
            ":SYST:AZERO OFF",  # turn off autozero for faster readings
            ":SENS:AVER:STAT 0",  # turn off averaging for faster readings
        ]
        self.query_and_check_batched(cmds)

        if set_curr_range is None:
            print_log(
                "Using AUTORANGE to select initial range based on zero reading...\n"
                + f"AUTORRANGE ON, NPLC = {nplc}...",
                verbose=self.verbose,
            )
            cmds = [
                f":SENS:CURR:NPLC {nplc}",
                ":SENS:CURR:RANGE:AUTO ON",  # enable autorange to let instrument select appropriate range based on zero reading
            ]
        elif isinstance(set_curr_range, float):
            print_log(
                "Using specified range. AUTORANGE is OFF...\n"
                + f"AUTORRANGE OFF, NPLC = {nplc}, RANGE SET POINT = {set_curr_range}...",
                verbose=self.verbose,
            )
            cmds = [
                f":SENS:CURR:NPLC {nplc}",
                ":SENS:CURR:RANGE:AUTO OFF",  # disable autorange to lock the range
                f":SENS:CURR:RANG {set_curr_range}",
            ]
        else:
            raise ValueError(f"Invalid curr_range value: {set_curr_range}, type {type(set_curr_range)}")

        self.query_and_check_batched(cmds)

        # Perform a single read to let instrument choose range

        print_log("Performing initial read to let instrument choose range OR check overflow...", verbose=self.verbose)

        if set_curr_range is None:
            # If autorange is enabled, we need to take a reading to let the instrument determine
            # the appropriate range based on the signal level. The actual value of the reading
            # is not important here; we just need to trigger the instrument's range selection logic.
            _ans = self.acq_read(persistent=True)
            # Lock the detected range and turn autorange off
            print_log("Locking range at detected value and turning autorange off...", verbose=self.verbose)
            self.query_and_check(":SENS:CURR:RANGE:AUTO OFF")

        # Query the selected numeric range
        print_log("Querying Range and NPLC selected by INSTRUMENT...", verbose=self.verbose)

        rng_val = self.get_curr_range()

        if rng_val > 0.0:  # check if autorange is still ON based on sentinel value
            print_done("Autorange is OFF as expected.")
        else:
            print_warning("Autorange is ON, unexpected behavior.", verbose=self.verbose)
            raise RuntimeError("Autorange should be OFF after range selection, but query indicates it is still ON.")

        nplc_val = self.get_curr_NPLC()

        print_log(
            "Autorange selection complete. Time elapsed: {:.2f} s".format(time.time() - _start_t), verbose=self.verbose
        )

        return rng_val, nplc_val

    def zero_instrument(self):
        """
        If curr_range is None, auto-select range first. Then take one zero reading
        """
        _start_t = time.time()
        print_log("Starting zero measurement...", verbose=self.verbose)

        cmds1 = [  # From Manual pg 3-6
            # ":*RST",
            # ":SYST:TIME:RESET",
            ":SYST:ZCH ON",
            ":INIT",
        ]
        cmds2 = [
            ":SYST:ZCOR:STAT OFF",
            ":SYST:ZCOR:ACQ",
            ":SYST:ZCH OFF",
            ":SYST:ZCOR ON",
        ]

        self.query_and_check_batched(
            cmds1,
            send_individually=True,
        )
        self.wait_operation_complete(
            poll_interval=0.1, timeout=5.0
        )  # wait for INIT to complete before starting zeroing sequence.
        self.query_and_check_batched(
            cmds2,
            send_individually=True,
        )

        resp = self.acq_read(persistent=True)

        if resp is None:
            print_warning(
                "Received empty response when acquiring zero measurement. Returning None.", verbose=self.verbose
            )
            return None

        if "A" in resp:
            zero_val = resp.strip().replace("A", "")
        elif "," in resp:
            zero_val = resp.rsplit(",")[0].strip()
        else:
            zero_val = resp.strip()

        try:
            zero_val = float(zero_val)
        except ValueError:
            zero_val = None

        print_done("Zero measurement complete.\n" + f"Zero value: {zero_val}.", verbose=self.verbose)
        print_log(f"Zeroing instrument... ENDED. Time elapsed: {time.time() - _start_t:.2f} s", verbose=self.verbose)

        return zero_val

    def setup_read_acquisition(self, points_for_stat: int = 1):
        """
        Prepare instrument for single-point acquisition with timestamps.
        """
        print_log("Setting up single-point acquisition...", verbose=self.verbose)
        _start_t = time.time()

        # Please note that, according to manual pg 12-2
        # when #CONF is executed, the 6487 is configured as follows:
        # ▪ All controls related to the selected function are defaulted to the *RST values.
        # ▪ The event control sources of the trigger model are set to immediate.
        # ▪ The arm and trigger count values of the trigger model are set to one.
        # ▪ The delay of the trigger model is set to zero.
        # ▪ The 6487 is placed in the idle state.
        # ▪ All math calculations are disabled.
        # ▪ Buffer operation is disabled. A storage operation presently in process will be aborted.
        # ▪ Autozero is enabled.

        self.query_and_check_batched([":CONF:CURR;SYST:AZER ON;:CONF?"])

        print_log(
            f"Single-point acquisition setup complete. Time elapsed: {time.time() - _start_t:.2f} s",
            verbose=self.verbose,
        )
        return True

    def setup_waveform_acquisition(self, num_points: int = 60):
        """
        Prepare instrument for buffered waveform acquisition with timestamps.
        Sets up the internal buffer to store `num_points` readings with timestamps,
        and configures the trigger model for single-trigger sampling to ensure
        even spacing of readings.
        """

        print_log("Setting up buffer and trigger for waveform acquisition...", verbose=self.verbose)
        _start_t = time.time()

        if num_points > 2048 or num_points < 1:
            print_error(f"num_points must be between 1 and 2048, got {num_points}", verbose=self.verbose)
            raise ValueError(f"[ERROR] num_points must be between 1 and 2048, got {num_points}")

        if num_points > 100 or num_points < 1:
            print_warning(
                f"Number of Points is {num_points} > 100. Note that Download of waveform using USB is slow,\n around 10-25 samples/seconds.\n\t(non-linear, higher numbers are faster, but total time keeps\n increase. For reference, 250 samples takes 10s to download))",
                verbose=self.verbose,
            )

        setup_recipe = [  # following pg 6-8 from manual
            # ":FORM:ELEM READ,TIME",
            # ":SENS:CURR:RANGE:AUTO OFF",
            "SYST:AZER OFF",  # turn off autozero for faster readings; comment out if you want autozero between readings
            f":TRIG:COUNT {num_points}",  # single-trigger sampling for even spacing, 1 to 2048
            f":TRAC:POIN {num_points}",  # specify number of readings to store: it can be 1 to 3000, but thigger is limited to 2048, so we set both to 2048 max to avoid overflow issues
            ":TRAC:CLE",  # clear buffer before starting acquisition
            ":TRAC:FEED SENS",  # Store raw input readings (as opposed to calculated values like avg and max/min).
            # ":TRAC:FEED:CONT NEXT"# `NEXT` Enables the buffer. `NEVer disable it. MOVED TO acq_waveform function to ensure it's armed right before acquisition starts
        ]
        self.query_and_check_batched(setup_recipe, send_individually=False)

        print_log(
            f"Setup of buffer and trigger for waveform acquisition complete. Time elapsed: {time.time() - _start_t:.2f} s",
            verbose=self.verbose,
        )

    def acq_read(self, persistent=False, max_attempts=5):

        resp = None
        for _ in range(max_attempts):
            resp = self.query_and_check(":READ?")

            if resp == "":
                print_warning("Received empty response to :READ? Returning None.", verbose=self.verbose)

            if persistent and resp is None:
                continue
            else:
                return resp

        print_error(f"Failed to get valid response after {max_attempts} attempts. Returning None.")
        return resp

    def acq_waveform(self, poll_interval: float = 0.01, timeout: float = 5.0) -> pd.DataFrame:
        """
        Wait for buffer to fill then read buffered data (readings + timestamps).
        Returns raw response string from :TRAC:DATA?; caller should parse into values/times.
        """

        print_log("\nAcquiring waveform...", verbose=self.verbose)
        print_log(
            "Clear Buffer, Prepare Buffer for acquisition, Start acquisition, Poll for completion, Download data from Buffer...",
            verbose=self.verbose,
        )

        _start_total_time = time.time()

        _start_acq_time = time.time()

        print_warning("Acquisition of waveform. This can be slow. Please be patient...", verbose=self.verbose)

        # Arm acquisition
        self.query_and_check(":TRAC:CLE;:TRAC:FEED:CONT NEXT")
        self.query_and_check(
            ":INIT", check_errors=False
        )  # send :INIT by itself. INIT will hang the instrument, and check_inst_errors will not be able to communicate with the instrument until acquisition is complete. So we will wait for acquisition to complete with wait_operation_complete

        # Please note that `:TRAC:FEED:CONT NEXT` enables the buffer and needs to be sent right before acquisition starts. After running `:INIT`, the buffer will change to back to `:TRAC:FEED:CONT NEVER`, and needs to be re-enabled before the next acquisition . If you dont do this, no new data will be stored in the buffer and subsequent queries to `:TRAC:DATA?` will return the same data until you re-enable the buffer with `:TRAC:FEED:CONT NEXT`.

        self.wait_operation_complete(poll_interval=poll_interval, timeout=timeout)

        print_success(f"Acquisition COMPLETED! time elapsed: {time.time() - _start_acq_time:.2f}s")
        print_log(
            "Start Download data... ",
            verbose=self.verbose,
        )
        _downl_time = time.time()

        # Read all buffered readings and timestamps in one transfer
        raw_waveform = self.query_and_check(":TRAC:DATA?")

        print_success(
            f"Buffer Download COMPLETED. Download time: {time.time() - _downl_time:.2f} s.", verbose=self.verbose
        )

        print_done(
            f"Acquisition and Download Completed. TOTAL Time elapsed: {time.time() - _start_total_time:.2f} s",
            verbose=self.verbose,
        )

        # return raw_waveform
        return self._parse_raw_waveform_data(raw_waveform)

    def _parse_raw_waveform_data(self, raw) -> pd.DataFrame:
        """
        Parse a comma-separated stream of READ,TIME,READ,TIME,... into a DataFrame with columns Current_Amps and Time_Secs.

        Usage:
        df_raw = parse_raw_waveform_data(raw_waveform)
        """
        parts = [p.strip() for p in raw.strip().split(",") if p.strip() != ""]
        reads, times = [], []
        for i in range(0, len(parts), 2):
            reads.append(float(parts[i]))
        for i in range(0, len(parts), 2):
            times.append(float(parts[i + 1]))
        df = pd.DataFrame({"Current_Amps": reads, "Time_Secs": times})
        return df
        # return read, times


if __name__ == "__main__":
    devs = detect_keithley_devices(baudrate=None, verbose=True)

    if devs is None:
        print_error("No Keithley devices found. Exiting.")
        exit(1)

    for dev in devs:
        if dev["is_keithley"]:
            print_keithley_properties(dev)
            serial_query("*IDN?", dev["port"], verbose=True)
            kth_dev = KeithleyPicoammeter(port=dev["port"], baudrate=dev["baudrate"], verbose=True)
            read_res = kth_dev.acq_read()
            print(f"[RESULT] Raw data length: {read_res.count(',') + 1} data points")  # type: ignore
