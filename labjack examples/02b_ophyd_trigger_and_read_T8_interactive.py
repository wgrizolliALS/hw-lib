""" """

# %%
import time
import matplotlib

# --- THE DETECTOR CLASS ---
from ophyd_labjack_t8 import LabJackT8Ophyd


# %%

print("[INFO] Starting Detector Test with Ophyd...")
# det = LabJackT8Ophyd(name="test_lj", channels=[0, 1], act_time=1.0, sample_rate=100, verbose=True)


det = LabJackT8Ophyd(
    name="test_lj",
    channels=[0, 1],
    act_time=1.0,
    sample_rate=100.0,  #
    # ranges={0: 10, "AIN1": 3.44},
    enable_waveforms=True,
    verbose=True,
)

print("[INFO] ophyd LabJackT8Ophyd instance created with channels: ", det.active_channels)

# %%

det.set_range(0, 0.15)
det.set_range(1, 0.095)


# Ranges: ±11 V, ±9.6 V, ±4.8 V, ±2.4 V, ±1.2 V, ±0.6 V, ±0.3 V, ±0.15 V, ±0.075 V, ±0.036 V, ±0.018 V


# %%
print("[INFO] Triggering the detector...")
status = det.trigger()
print("[INFO] Detector triggered, waiting for acquisition to complete...")

# Wait for the trigger to finish
count = 0
while not status.done:
    time.sleep(0.5)
    count += 1
    if count > 10:  # Safety timeout
        print("[TIMEOUT] Status never marked as done!")
        break

# Check values
readings = det.read()
for key, val in readings.items():
    try:
        print(f"[Result] {key}: 10 first rows of array:\n{val['value'][:10]}")  # type: ignore
    except (TypeError, IndexError):
        print(f"[Result] {key}: {val['value']}")  # type: ignore

# %%

if det.handle:
    det.close()
    print("[INFO] Detector connection closed.")


# %% POST PROCESSING
print("\n[POSTPROCESSING] Post Processing STARTED")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib  # noqa: E402, F811

matplotlib.use("qtagg")

# import numpy as np  # noqa: E402
# %% PLOT RAW WAVEFORM

_raw_wvf = readings["test_lj_raw_block"]["value"]  # type: ignore

print("\n[POSTPROCESSING] Plotting raw waveform data with Matplotlib...")
plt.figure()
plt.plot(_raw_wvf[:, 0] - _raw_wvf[0, 0], _raw_wvf[:, 1], ".-")
plt.plot(_raw_wvf[:, 0] - _raw_wvf[0, 0], _raw_wvf[:, 2], ".-")
plt.show(block=True)

# %%

print("\n[INFO] Test Complete.\n")

# %%
