"""
Simple script to verify the LabJack LJM library installation and version.
"""

# %%
import os
import sys
from labjack import ljm

# %%

print(f"\n## Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

print("\n### labjack python library version: " + ljm.__version__ + " ###")
# Print the installation path of the LJM library
print(f"LJM Library Location: {os.path.dirname(ljm.__file__)}")

# Print the installation path of the labjackT8_utils library)
print(f"labjack_t8_ophyd Library Location: {os.path.dirname(ljt8o.__file__)}\n")

ljm.closeAll()  # Close any open connections just in case
