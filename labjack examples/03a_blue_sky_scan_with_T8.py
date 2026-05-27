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

matplotlib.use("qtagg")
import matplotlib.pyplot as plt

# %! matplotlib qt

# %%
from bluesky import RunEngine
from bluesky.plans import count, scan  # type: ignore  # noqa: F401
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd.sim import motor  # type: ignore

from ophyd_labjack_t8 import LabJackT8Ophyd


# %% Initialize Hardware
print("[INFO] Initializing LabJack T8...")
t8 = LabJackT8Ophyd(name="t8", active_AI_channels=[0, 1], acq_time=1.0, sample_rate=1000.0, verbose=True)
# t8 = LabJackT8Ophyd(name="t8", channels=[0, 1, 2, 4], act_time=1.0, sample_rate=10.0, verbose=True)

print("[INFO] LabJack T8 initialized.")
print("[INFO] info:", t8.handle_info)

# %% Initialize Bluesky
print("[INFO] Initializing RunEngine and BestEffortCallback...")
RE = RunEngine({})
print("[INFO] Bluesky RunEngine STARTED")
print("[INFO] Subscribing BestEffortCallback for real-time visualization...")
RE.subscribe(BestEffortCallback())

# Link the internal saver
print("[INFO] Subscribing LabJack T8 CSV saver to RunEngine...")
RE.subscribe(t8.csv_saver)
# %%
plt.ion()
try:
    # High-level command
    print("[INFO] Starting Bluesky Scan with LabJack T8...")
    RE(scan([t8], motor, -5, 5, 3))  # type: ignore
    # RE(count([t8]))  # type: ignore

    plt.show(block=True)
finally:
    t8.close()

# %%
