# %%
"""
%load_ext autoreload
%autoreload 2
"""

import time

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

    # %% Zero Instrument and Check for Errors

    zero_val = kthu.zero_instrument(SERIALPORT, verbose=True)

    # %% Setup Acquisition, Acquire Waveform, Parse Results
    # %% MAIN LOOP: Setup acquisition, acquire waveform, parse results
    num_points = 100
    # nplc = 1.0
    _df_list: list[pd.DataFrame] = []

    _start_t_main_loop = time.time()

    _sel_range_vals = [
        # 3.0e-10,
        # 3.0e-9,
        # 3.0e-8,
        3.0e-7,
        # 3.0e-6,
        # 3.0e-5,
        # 3.0e-4,
        # 3.0e-3,
    ]
    nplc_vals = [0.1, 0.01]
    _step = 0

    for _sel_range in _sel_range_vals:
        for nplc in nplc_vals:
            kthu.set_range(SERIALPORT, set_curr_range=_sel_range, nplc=nplc, verbose=True)

            kthu.setup_waveform_acquisition(
                SERIALPORT,
                num_points=num_points,
                verbose=True,
                debug=False,
            )

            raw = kthu.acq_waveform(SERIALPORT, verbose=True)

            final_range = kthu.get_curr_range(SERIALPORT, verbose=True)

            _df = kthu.parse_raw_waveform_data(raw)
            _df["NPLC"] = nplc
            _df["Range"] = final_range
            _df_list.append(_df)

            _step += 1
            printc(
                "\n########### [INFO] MAIN LOOP: Step "
                + f"{_step} of {len(_sel_range_vals) * len(nplc_vals)}."
                + f" Time elapsed: {time.time() - _start_t_main_loop:.2f} s\n",
                color="purple",
                bold=True,
                timestamp=False,
            )

    # Ensure we actually collected any data before concatenating
    if not _df_list:
        raise RuntimeError("No data collected: _df_list is empty. Check instrument connectivity and acquisition loop.")

    df = pd.concat(_df_list, ignore_index=True)

    df["Time_msecs"] = df["Time_Secs"] * 1000
    df.to_csv("01b_keithley_waveform_data.csv", index=False, header=True)  # Save raw data to CSV for reference

    printc("DONE!", color="green", bold=True)

    # %% Print some results summary
    printc(f"[RESULTS] Acquired samples: {len(df)}", color="green")

    printc("[RESULTS] Samples DataFrame Head 10:", color="green", bold=True)
    print(df.head(10))
    printc("[RESULTS] Samples DataFrame info:", color="green", bold=True)
    print(df.info())
    printc("[RESULTS] Samples DataFrame describe:", color="green", bold=True)
    print(df.describe())

    # %% Post Processing

    df_post = pd.DataFrame(
        {
            "Acq_Time_ms": [],
            "NPLC": [],
            "Range": [],
            "Time_Diffs_ms_Mean": [],
            "Time_Diffs_ms_Max": [],
            "Time_Diffs_ms_Min": [],
            "Mean_Dead_Time_ms": [],
            "Max_Dead_Time_ms": [],
            "Min_Dead_Time_ms": [],
            "Mean_Dead_Time_Percent": [],
            "Max_Dead_Time_Percent": [],
            "Min_Dead_Time_Percent": [],
        }
    )

    for nplc in df["NPLC"].unique():
        act_time_ms = nplc / POWER_LINE_FREQ * 1000
        printc(
            f"[RESULTS] Expected acquisition time based on NPLC={nplc} and PL period: {act_time_ms:.4f} ms",
            color="blue",
        )
        for rng in df["Range"].unique():
            # time_diffs_ms = df[df["NPLC"] == nplc]["Time_msecs"].diff().dropna()
            time_diffs_ms = df.loc[(df["NPLC"] == nplc) & (df["Range"] == rng), "Time_msecs"].diff().dropna()  # type: ignore

            new_row = {
                "Acq_Time_ms": act_time_ms,
                "NPLC": nplc,
                "Range": rng,
                "Time_Diffs_ms_Mean": time_diffs_ms.mean(),
                "Time_Diffs_ms_Max": time_diffs_ms.max(),
                "Time_Diffs_ms_Min": time_diffs_ms.min(),
                "Mean_Dead_Time_ms": time_diffs_ms.mean() - act_time_ms,
                "Max_Dead_Time_ms": time_diffs_ms.max() - act_time_ms,
                "Min_Dead_Time_ms": time_diffs_ms.min() - act_time_ms,
                "Mean_Dead_Time_Percent": (time_diffs_ms.mean() / act_time_ms - 1) * 100,
                "Max_Dead_Time_Percent": (time_diffs_ms.max() / act_time_ms - 1) * 100,
                "Min_Dead_Time_Percent": (time_diffs_ms.min() / act_time_ms - 1) * 100,
            }

            # df_post.loc[len(df_post)] = new_row  #
            df_post.loc[len(df_post)] = pd.Series(new_row)  # append new row to summary DataFrame

    df_post.to_csv("01b_keithley_postprocessing.csv", index=False, header=True)  # Save raw data to CSV for reference

    # %%
    printc(f"[RESULTS] Post-Processing Conditions: {len(df)}", color="green")

    printc("[RESULTS] Post-Processing DataFrame Head 10:", color="green", bold=True)
    print(df_post.head(10))
    printc("[RESULTS] Post-Processing DataFrame info:", color="green", bold=True)
    print(df_post.info())

    # %%
    printc("[RESULTS] Dead Time Only DataFrame:", color="green", bold=True)
    print(df_post.iloc[:, [1, 0, 2, 6, 7, 8]])

    # %%
    _total_t_end = time.time()
    printc(
        f"[RESULTS] Total execution time: {_total_t_end - _total_t_start:.4f} s", color="green", bold=True
    )

    # %%

    # df.loc[(df["NPLC"] == 0.01), "Time_msecs"].diff().to_list()


# %% Some Results for reference:
# [RESULTS] Dead Time Only DataFrame:
#      NPLC  Acq_Time_ms         Range  Mean_Dead_Time_ms  Max_Dead_Time_ms  \
# 0   10.00   166.666667  2.100000e-09           1.193556          1.302533
# 1   10.00   166.666667  2.100000e-06           1.193556          1.302333
# 2   10.00   166.666667  2.100000e-03           1.193556          1.302333
# 3    1.00    16.666667  2.100000e-09           1.128478          1.888043
# 4    1.00    16.666667  2.100000e-06           1.236978          1.888033
# 5    1.00    16.666667  2.100000e-03           1.128478          1.888043
# 6    0.10     1.666667  2.100000e-09           1.154514          1.263023
# 7    0.10     1.666667  2.100000e-06           1.154514          1.263023
# 8    0.10     1.666667  2.100000e-03           1.154514          1.263023
# 9    0.01     0.166667  2.100000e-09           1.569444          1.786460
# 10   0.01     0.166667  2.100000e-06           1.569444          1.786460
# 11   0.01     0.166667  2.100000e-03           1.460938          1.786463

#     Min_Dead_Time_ms
# 0           0.325333
# 1           0.325433
# 2           0.325533
# 3           0.911433
# 4           0.911433
# 5           0.911433
# 6           0.286460
# 7           0.286463
# 8           0.286463
# 9           0.809896
# 10          0.809896
# 11          0.809893
