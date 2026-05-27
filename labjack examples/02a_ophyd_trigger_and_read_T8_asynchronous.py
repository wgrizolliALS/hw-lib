"""
This example demonstrates how to use the LabJack T8 with the ophyd library in an asynchronous manner.

Summary:
1. We define a custom Ophyd Device for the LabJack T8, which includes methods for triggering and reading data.
2. We implement an asynchronous trigger using Python threading, allowing the main thread to remain responsive while waiting for the acquisition to complete.
3. The script handles both real hardware connections via LJM and simulated data, making it versatile for testing and development.
4. A manual execution loop triggers the device and reads back the averaged results.
5. This standalone test is useful for verifying hardware communication and Ophyd signal logic before integrating the device into a full Bluesky RunEngine scan.


"""

# %%
from datetime import datetime
import time

# --- THE DETECTOR CLASS ---
import ophyd_labjack_t8 as ljt8o


def datenow_str():
    return datetime.now().isoformat(sep=" ", timespec="milliseconds")


# %%
# --- THE STANDALONE TEST ---
def main():
    print(f"[INFO] {datenow_str()}: Starting Detector Test with Ophyd...")
    det = ljt8o.LabJackT8Ophyd(name="test_lj", channels=[0, 1])
    print(f"[INFO] {datenow_str()}: ophyd LabJackT8Ophyd instance created with channels: ", det.active_channels)

    for i in range(3):
        print(f"\n[INFO] {datenow_str()}: Point {i + 1}:")

        print(f"[INFO] {datenow_str()} Triggering the detector...")
        status = det.trigger()
        print(f"[INFO] {datenow_str()}: Detector triggered, waiting for acquisition to complete...")

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
            print(f"[RESULT] {datenow_str()}: {key}: {val['value']}")  # type: ignore

    if det.handle:
        det.close()
        print(f"[INFO] {datenow_str()}: Detector connection closed.")

    print("[INFO] Test Complete.")


if __name__ == "__main__":
    main()

# %%
