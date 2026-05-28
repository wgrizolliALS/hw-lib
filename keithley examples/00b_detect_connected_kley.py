# %%

import keithley_utils as kthu

from wg_toolkit.logprint import print_info, print_error


if __name__ == "__main__":
    devs = kthu.detect_keithley_devices(baudrate=None, verbose=True, debug=False)

    if devs is None:
        print_error("No Keithley devices found. Exiting.")
        exit(1)
    for dev in devs:
        if dev["is_keithley"]:
            kthu.print_keithley_properties(dev)
            print_info("Resetting device to default settings...")
            kthu.serial_query("*RST", dev["port"], verbose=True, debug=False)
            print_info("Querying current configuration...")
            kthu.serial_query(":CONF?", dev["port"], verbose=True, debug=False)
            print_info("Querying data...")
            read_res = kthu.serial_query(":READ?", dev["port"], verbose=True, debug=False)
            if read_res is not None:
                print_info(f"Raw data length: {read_res.count(',') + 1} data points")
            else:
                print_info("No data received from device.")

            print("\n" + "=" * 100 + "\n")

# %%
