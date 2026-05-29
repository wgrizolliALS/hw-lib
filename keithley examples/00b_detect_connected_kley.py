# %%

from keithley_utils import print_keithley_properties, detect_keithley_devices

from wg_toolkit.logprint import print_info, print_error

from wg_toolkit.ports import serial_query


if __name__ == "__main__":
    devs = detect_keithley_devices(baudrate=None, verbose=True, debug=False)
    if devs is None:
        print_error("No Keithley devices found. Exiting.")
        exit(1)
    for dev in devs:
        if dev["is_keithley"]:
            print_keithley_properties(dev)
            print_info("Resetting device to default settings...")
            # example of raw command query with keithley
            serial_query("*RST", dev["port"], verbose=True, debug=False)
            print_info("Querying current configuration...")
            serial_query(":CONF?", dev["port"], verbose=True, debug=False)
            print_info("Querying data...")
            read_res = serial_query(":READ?", dev["port"], verbose=True, debug=False)
            if read_res is not None:
                print_info(f"Raw data length: {read_res.count(',') + 1} data points")
            else:
                print_info("No data received from device.")

            print("\n" + "=" * 100 + "\n")

# %%
