"""
Simple script to verify the Keithley library installation and version.

"""

# %%
import os
import sys

# This library
# %%

try:
    import wg_toolkit as wgtk
    from wg_toolkit.logprint import print_info, print_warning, print_done, print_error

    print("\n")
    print_info(f"## Python version: {sys.version}")
    print_info(f"Python executable: {sys.executable}")
    if ".venv" in sys.executable:
        print_warning("It looks like you are using a .venv environment.")

    print("\n")
    print_done("wg_toolkit imported successfully")
    print_info(f"wg_toolkit Library Location: {os.path.dirname(wgtk.__file__)}\n\n")

except ImportError as e:
    print(f"[ERROR] Error importing wg_toolkit: {e}")
    print("[ERROR] Please ensure that wg_toolkit is installed and available in your Python environment.")
    raise e

# %%
try:
    import keithley_utils as kthu

    print_done("keithley_utils python library is installed ###")
    # Print the installation path of the keithley_utils library
    print_info(f"keithley_utils Library Location: {os.path.dirname(kthu.__file__)}\n")
except ImportError as e:
    print_error(f"Error importing keithley_utils: {e}")
    print_error("Please ensure that keithley_utils is installed and available in your Python environment.")
    raise e
