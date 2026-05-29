# %%
"""
%load_ext autoreload
%autoreload 2
"""

import matplotlib

matplotlib.use("qtagg")
# print(matplotlib.backends.backend_registry.list_builtin())  # type: ignore
# matplotlib.use("widget")

import time
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import keithley_utils as kthu  # your serial helper module;
from wg_toolkit.logprint import printc

POWER_LINE_FREQ = 60.0  # set to 50.0 if on 50 Hz mains
POWER_LINE_PERIOD = 1 / POWER_LINE_FREQ

DEBUG = False

# %% Example usage in a __main__ block
if __name__ == "__main__":
    pass
    # %% Scan For Instruments and Select Device
    _total_t_start = time.time()
    printc("[INFO] Starting Keithley waveform acquisition example...", color="purple", verbose=True)

    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
        printc("# Scan for hardware ENDED #\n", color="purple")

    except Exception as e:
        printc(f"Error during Keithley detection: {e}", color="red")

    SERIALPORT = devs[0]["port"] if devs[0]["port"] else None  # type: ignore
    if SERIALPORT is None:
        printc("[ERROR] No valid serial port found for device.", color="red", bold=True)
        raise SystemExit(1)

    # %% Reset Instrument and Check for Errors

    _ = kthu.reset_instrument(SERIALPORT, verbose=True)

    # %% Setup Acquisition, Acquire Waveform, Parse Results
    # %% MAIN LOOP: Setup acquisition, acquire waveform, parse results
    num_points = 100
    # _sel_range = None  # auto-range
    _sel_range = 1e-9
    nplc = 1.0

    kthu.set_range(SERIALPORT, set_curr_range=_sel_range, nplc=nplc, verbose=True)
    # %% Zero Instrument and Check for Errors

    zero_val = kthu.zero_instrument(SERIALPORT, verbose=True)

    # %% Setup Acquisition
    kthu.setup_waveform_acquisition(
        SERIALPORT,
        num_points=num_points,
        verbose=True,
        debug=False,
    )

    # %% Acquire Waveform, Parse Results
    _total_t_start = time.time()
    raw = kthu.acq_waveform(SERIALPORT, verbose=True)

    final_range = kthu.get_curr_range(SERIALPORT, verbose=True)

    printc(
        f"[INFO] Acquisition Finished. Elapsed time: {time.time() - _total_t_start:.2f} s", color="purple", bold=True
    )

    df = kthu.parse_raw_waveform_data(raw)
    df["NPLC"] = nplc
    df["Range"] = final_range

    df["Time_msecs"] = df["Time_Secs"] * 1000

    printc(f"[RESULTS] Acquired samples: {len(df)}", color="green")
    # %%
    printc("[RESULTS] Samples DataFrame Head 10:", color="green", bold=True)
    print(df.head(10))
    printc("[RESULTS] Samples DataFrame info:", color="green", bold=True)
    print(df.info())

    # %% Post Processing

    plt.figure()
    plt.plot(df["Time_msecs"], df["Current_Amps"], ".-")
    plt.title(f"Waveform Acquisition (Range: {final_range} A, NPLC: {nplc})")
    plt.xlabel("Time (ms)")
    plt.ylabel("Current (A)")
    plt.grid()
    plt.show(block=False)

    # %%

    plt.figure()
    plt.plot(df["Time_msecs"], np.diff(df["Time_msecs"], append=np.nan) - nplc * POWER_LINE_PERIOD * 1000, ".-")
    plt.title(f"Waveform Acquisition (Range: {final_range} A, NPLC: {nplc})")
    plt.xlabel("Time (ms)")
    plt.ylabel("Time Diff from Expected (ms)")
    plt.grid()
    plt.show(block=True)

# %%
