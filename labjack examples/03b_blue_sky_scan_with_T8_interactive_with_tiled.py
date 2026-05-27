"""
Bluesky Scan with LabJack T8 Multi-Channel Detector
This module demonstrates how to use the LabJackMultiChannelDetector with Bluesky to
perform a scan while recording data from multiple channels of the LabJack T8 device.
The workflow includes:
1. Initializing a RunEngine with the BestEffortCallback for real-time data visualization
2. Creating a LabJackMultiChannelDetector instance configured for channels 0, 1, and 2
3. Subscribing the detector's internal CSV saver to the RunEngine for automatic data logging
4. Executing a scan plan that moves a simulated motor from -5 to 5 in 11 steps while
    collecting detector data at each position
5. Properly closing the detector connection in a finally block to ensure resource cleanup
Key Features:
- Multi-channel data acquisition from LabJack T8 hardware
- Automatic CSV data export during scan execution
- Integration with Bluesky's scan plan infrastructure
- Ensures proper hardware resource management
Dependencies:
- bluesky: Experimental control framework
- ophyd: Control layer for hardware devices
- ophyd_local_labjack: Custom LabJack integration module
"""

# %% Regular imports

import matplotlib
# import numpy as np

# print(matplotlib.backends.backend_registry.list_builtin())
matplotlib.use("qtagg")
# matplotlib.use("ipympl")  # For Jupyter notebooks, use the interactive backend
import matplotlib.pyplot as plt  # noqa: E402

# show current backend
import numpy as np
import pandas as pd


# %% Bluesky and Ophyd imports
from bluesky import RunEngine  # type: ignore
from bluesky.plans import count, scan  # type: ignore  # noqa: F401
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd.sim import motor  # type: ignore

# %% Custom LabJackT8Ophyd import
from ophyd_labjack_t8 import LabJackT8Ophyd

# %% Databroker and Tiled imports
from tiled.server import SimpleTiledServer
from tiled.client import from_uri
from bluesky.callbacks.tiled_writer import TiledWriter


# %% Change plot style and parameters

print("[INFO] Current Matplotlib backend:", matplotlib.get_backend())  # type: ignore
plt.style.use("default")

params = {
    "font.size": 10,
    "legend.fontsize": "small",
    "font.family": "serif",
    "figure.facecolor": "white",
    "axes.grid": True,
    "figure.autolayout": True,
    "axes.grid.axis": "both",
    "mathtext.fontset": "stix",
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "figure.figsize": (6, 5),
    "image.origin": "lower",
    "image.interpolation": "none",
    "image.cmap": "magma",
    "lines.marker": "o",
    "lines.linestyle": "-",
}

plt.rcParams.update(params)

# %% Initialize Hardware

print("[SETUP HW] Initializing LabJack T8...")
try:
    t8 = LabJackT8Ophyd(
        name="t8", channels=[0, 1, 2, 4], act_time=1.0, sample_rate=1000.0, verbose=True, enable_waveforms=True
    )
    print("[SETUP HW] LabJack T8 initialized.")
    print("[SETUP HW] info:", t8.handle_info)
except Exception as e:
    print(f"[ERROR] Failed to initialize LabJack T8: {e}")
    print("***STOPPING EXECUTION*** Please check the LabJack connection and try again.")
    exit(1)

# %%
# Initialize Bluesky
print("[SETUP ACQUISITION] Initializing RunEngine and BestEffortCallback...")
RE = RunEngine({})
print("[SETUP ACQUISITION] Bluesky RunEngine STARTED. State: ", RE.state)

for key, val in RE.md["versions"].items():
    print(f"[SETUP ACQUISITION] {key} version {val}")

RE.md["any metadata you want to add"] = "example value"

# %% Additional Bluesky settings and subscriptions
# Link the BestEffortCallback for real-time visualization (optional but recommended)
RE.subscribe(BestEffortCallback())  # type: ignore
print("[SETUP ACQUISITION] BestEffortCallback subscribed to RunEngine.")
# Link the internal saver
RE.subscribe(t8.csv_saver)  # (un)comment this line to enable/disable internal CSV saving
print("[SETUP ACQUISITION] RunEngine and BestEffortCallback initialized.")


# %% Initialize local Tiled server and client
print("[DATASERVER] Initializing local Tiled server and subscribing to RunEngine...")
save_path = "./tiled_labjack_data"
tiled_server = SimpleTiledServer(readable_storage=[save_path])  # type: ignore
tiled_client = from_uri(tiled_server.uri)
tw = TiledWriter(tiled_client)
RE.subscribe(tw)
print("[DATASERVER] Local Tiled server and TiledWriter initialized and subscribed to RunEngine.")


# %%
plt.ion()
plt.close("all")

# %% SCAN EXECUTION
try:
    print("[ACQUISITION] Acquisition STARTED...")
    # run a scan and capture uid
    (uid,) = RE(scan([t8], motor, -5, 5, 5))  # type: ignore # blocks until complete

    print("[ACQUISITION] Acquisition FINISHED. uid:", uid)
    plt.show(block=False)
except Exception as e:
    print(f"[ERROR] Error during scan execution: {e}")
    print("***STOPPING EXECUTION*** Please check the error message and try again.")
    exit(1)

print("[VISUALIZATION] Close plot to proceed (block=True)...")
plt.show(block=True)
# exit(0)  # stop execution here to avoid running post-processing code in case of errors during acquisition

# %% Read back from Tiled
print("[DATASERVER] Retrieving run data from Tiled catalog...")

uid_list = tiled_client.keys()

for i, key in enumerate(uid_list):
    print(f"[DATASERVER] key {i}: {tiled_client[key]}")


print("[DATASERVER] Retrieving dataset from Tiled client...")
ds = tiled_client[uid_list[-1]]  # get the most recent dataset
# ds = tiled_client[key_list[-1]]  # get a past dataset
print("[DATASERVER] LOADED:", ds)

print("[DATASERVER] END DATA RETRIEVAL, BEGINNING POST-PROCESSING")

# %% POST-PROCESSING AND VISUALIZATION

print("[POSTPROCESSING] Inspecting dataset variables...")

stream = ds.primary  # the primary stream is where the TiledWriter writes the data by default, but you can also access other streams if you have them configured (e.g. for metadata, or separate streams for different devices)

ds_xr = stream.read()  # xarray.Dataset containing all the data for this run
# ds_xr is a xarray.Dataset. It is faster to access values because stream will run a yield for each request, while ds_xr has all data in memory. However, ds_xr is not lazy and will load everything into memory at once, so it may not be suitable for very large datasets.
# For large dataset, use stream[key].read() to read one variable at a time, which will yield one event at a time and not load everything into memory at once.

# %% I FOUND A BUG

# This works, returning a np array of floats
foo = stream["t8_ain1_waveform"].read()

# This does not work, returning a np array of strings instead of floats, which is not what we want
bar = stream.read()["t8_ain1_waveform"]

# %% Inspecting the dataset variables and their types/shapes to understand the issue with waveform data
print("[POSTPROCESSING] Getting stream data into a pandas df")

# Prepare a dictionary to hold the data for each key
data = {}
waveform_cols = []
# Loop through each key and read the data
for key in stream.keys():
    arr = stream[key].read()
    # If the data is a 2D array (e.g., waveform: shape (events, waveform_length)), flatten or keep as list
    print(f"  Reading data for key: {key}, type: {type(arr)}, shape: {arr.shape}")
    if isinstance(arr, np.ndarray) and arr.ndim > 1:
        # Store as list of arrays (or you can flatten, or keep as is for further processing)
        data[key] = [a for a in arr]
        waveform_cols.append(key)
    else:
        # Scalar or 1D array
        data[key] = arr

# %% Create a DataFrame
df = pd.DataFrame(data)
df = df.explode(
    waveform_cols
)  # Needed to explode the waveform columns to get one row per event, with the waveform data as a list/array in each row

# %% Adjustments to time columns and indexing
time_cols = [col for col in df.columns if "ts_" in col or "_tim" in col]

print("[POSTPROCESSING] Adjusting time columns and DataFrame index...")
# If the index is still int64, try setting it to the time column
if df.index.dtype == "int64":
    df.index = pd.to_datetime(df["t8_waveform_time"], unit="s")
    df.index.name = "Time and Date"

print("[POSTPROCESSING] DataFrame index set to time column. Index dtype:", df.index.dtype)
# Remove time offset
df[time_cols] = df[time_cols] - (df[time_cols].min()).min()

print("[POSTPROCESSING] END OF POST-PROCESSING. DataFrame ready for analysis and visualization.")
print("[RESULT] DataFrame Columns:\n", df.columns)
print("[RESULT] DataFrame head:\n", df.head())
# %%
print("[VISUALIZATION] Plotting waveforms for each seq_num...")
for _i in df["seq_num"].unique():
    plt.figure()
    print(f"seq_num {_i} has {len(df[df['seq_num'] == _i])} events")

    _x_vec = df[df["seq_num"] == _i]["t8_waveform_time"]

    _x_vec -= _x_vec.min()  # remove time offset for better visualization

    for col in waveform_cols:
        print(f"Plotting {col} for seq_num {_i}")
        _y_vec = df[df["seq_num"] == _i][col]
        plt.plot(_x_vec, _y_vec, ".-", label=f"{col} for seq_num {_i}")

    plt.title(f"seq_num {_i}")
    plt.xlabel("Time (s)")
    plt.ylabel("Signal [Volts]")
    plt.legend()
    plt.show()

print("[VISUALIZATION] Close plot to proceed (block=True)...")
plt.show(block=True)

# %%

print("[VISUALIZATION] Plotting waveforms for all events together...")
for col in waveform_cols:
    plt.figure()
    print(f"seq_num {_i} has {len(df[df['seq_num'] == _i])} events")

    _x_vec = df["t8_waveform_time"]

    print(f"Plotting {col}...")
    _y_vec = df[col]
    plt.plot(_x_vec, _y_vec, ".", label=col)
    plt.plot(_x_vec, _y_vec, "-", c="C0", alpha=0.5)

plt.title(col)
plt.xlabel("Time (s)")
plt.ylabel("Signal [Volts]")

print("[VISUALIZATION] Close plot to proceed (block=True)...")
plt.show(block=True)

print("[VISUALIZATION] END OF VISUALIZATION.")

# %%
print("[INFO] END OF SCRIPT. Closing LabJack T8 connection...")
if t8 is not None:
    t8.close()
print("[INFO] LabJack T8 connection closed.")

print("[INFO] Closing Tiled server connection...")
if tiled_server is not None:
    tiled_server.close()  # or tiled_server.shutdown() if available
print("[INFO] Tiled server connection closed.")

exit(0)
# %%
