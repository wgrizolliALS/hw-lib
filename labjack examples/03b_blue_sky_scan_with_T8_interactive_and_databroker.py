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

# %%
import matplotlib
# import numpy as np

# print(matplotlib.backends.backend_registry.list_builtin())
matplotlib.use("qtagg")
# matplotlib.use("ipympl")  # For Jupyter notebooks, use the interactive backend
import matplotlib.pyplot as plt  # noqa: E402
# show current backend


# %%
from bluesky import RunEngine  # type: ignore
from bluesky.plans import count, scan  # type: ignore  # noqa: F401
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd.sim import motor  # type: ignore

from ophyd_labjack_t8 import LabJackT8Ophyd

from databroker import Broker  # noqa: F401


# %% Change plot style and parameters

print("Current Matplotlib backend:", matplotlib.get_backend())  # type: ignore
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

print("[INFO] Initializing LabJack T8...")
try:
    t8 = LabJackT8Ophyd(name="t8", channels=[0, 1, 2, 4], act_time=1.0, sample_rate=1000.0, verbose=True)
    print("[INFO] LabJack T8 initialized.")
    print("[INFO] info:", t8.handle_info)
except Exception as e:
    print(f"[ERROR] Failed to initialize LabJack T8: {e}")
    exit(1)

# %%
# Initialize Bluesky
print("[INFO] Initializing RunEngine and BestEffortCallback...")
RE = RunEngine({})
print("[INFO] Bluesky RunEngine STARTED. State: ", RE.state)

for key, val in RE.md["versions"].items():
    print(f"[INFO] {key} version {val}")

RE.md["any metadata you want to add"] = "example value"

# %%
# Link the BestEffortCallback for real-time visualization (optional but recommended)
RE.subscribe(BestEffortCallback())  # type: ignore
print("[INFO] BestEffortCallback subscribed to RunEngine.")
# Link the internal saver
RE.subscribe(t8.csv_saver)
print("[INFO] RunEngine and BestEffortCallback initialized.")


# %%
# Initialize databroker (make sure you have configured a named broker, e.g. 'temp')
print("[INFO] Initializing Databroker and subscribing to RunEngine...")
db = Broker.named("temp")
RE.subscribe(db.insert)
print("[INFO] Databroker initialized and subscribed to RunEngine.")


# %%
plt.ion()
plt.close("all")
# %% SCAN EXECUTION
try:
    print("[INFO] Starting scan...")
    # run a scan and capture uid
    (uid,) = RE(scan([t8], motor, -5, 5, 5))  # type: ignore # blocks until complete

    print("[INFO] Scan finished. uid:", uid)
    plt.show(block=False)
except Exception as e:
    print(f"[ERROR] Error during scan execution: {e}")

# %%
plt.show(block=True)

# %% Read back from databroker

print("[INFO] Retrieving run data from Databroker...")
run = db[uid]  # or db[-1]

# %% Post-processing and visualization

print("[INFO] Post-processing run data...")
df = run.table()

df = df.set_index("time")
df["seconds"] = df.index.astype("int64") / 1_000_000_000.0  # convert from nanoseconds to seconds

print("[RESULT] DataFrame Columns:\n", df.columns)
print("[RESULT] DataFrame head:\n", df.head())

# %%
if t8 is not None:
    t8.close()
# %%
