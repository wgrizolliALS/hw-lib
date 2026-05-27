# file: t8_system.py


from datetime import datetime
import csv
import os

from labjack import ljm
import time
import numpy as np
from typing import Dict, List

# ============================================
# CONFIGURATION (at __main__ level)
# ============================================


def _time_now_str():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class SystemConfig:
    """Dynamic configuration for T8 system"""

    # Hardware connection
    CONNECTION_TYPE = "USB"  # "USB" or "ETHERNET"
    IP_ADDRESS = "192.168.1.100"  # For Ethernet connection
    USB_DEVICE = "ANY"  # "ANY" for first found, or specific serial number

    # ADC Configuration
    ADC_CHANNELS = ["AIN0", "AIN1", "AIN2"]  # Easy to change
    ADC_STREAM_RATE = 1000  # Hz

    # DAC Configuration (with custom functions)
    DAC_CONFIG = {
        "DAC0": {
            "enabled": True,
            "control_rate": 50,  # Hz
            "custom_function": None,  # Will be set in __main__
        },
        "DAC1": {
            "enabled": False,
            "control_rate": 50,
            "custom_function": None,
        },
    }

    # DIO Configuration
    DIO_CONFIG = {
        "DIO0": {
            "enabled": True,
            "mode": "clock",  # "clock" or "toggle"
            "frequency": 1000,  # Hz (for clock mode)
        },
        "DIO1": {
            "enabled": False,
            "mode": "toggle",
            "frequency": 10,  # Hz (for toggle mode)
        },
    }


# ============================================
# HARDWARE ABSTRACTION
# ============================================


class T8Hardware:
    """Low-level T8 operations"""

    def __init__(self, connection_type="USB", device_identifier="ANY"):
        """
        Initialize T8 connection

        Args:
            connection_type: "USB" or "ETHERNET"
            device_identifier: For USB: "ANY" or serial number
                             For Ethernet: IP address string
        """
        self.connection_type = connection_type

        if connection_type.upper() == "USB":
            # USB connection
            if device_identifier == "ANY":
                # Connect to first available USB T8
                self.handle = ljm.openS("T8", "USB", "ANY")
            else:
                # Connect to specific serial number
                self.handle = ljm.openS("T8", "USB", device_identifier)
        elif connection_type.upper() == "ETHERNET":
            # Ethernet connection (original behavior)
            self.handle = ljm.open(ljm.constants.dtT8, ljm.constants.ctETHERNET, device_identifier)
        else:
            raise ValueError(f"Unsupported connection type: {connection_type}. Use 'USB' or 'ETHERNET'")

        # Print connection info
        info = ljm.getHandleInfo(self.handle)
        print(f"Connected to T8 via {connection_type}:")
        print(f"  Device Type: {info[0]}")
        print(f"  Connection Type: {info[1]}")
        print(f"  Serial Number: {info[2]}")
        if connection_type.upper() == "ETHERNET":
            print(f"  IP Address: {device_identifier}")
        print()

    def start_streaming(self, channels: List[str], rate: int):
        """Start streaming specified channels"""
        addresses = []
        for channel in channels:
            addr, _ = ljm.nameToAddress(channel)
            addresses.append(addr)

        ljm.eStreamStart(
            self.handle,
            scansPerRead=256,
            scanRate=rate,
            numAddresses=len(addresses),
            aScanList=addresses,
        )

    def stop_streaming(self):
        """Stop streaming"""
        ljm.eStreamStop(self.handle)

    def read_stream(self):
        """Read one batch of streamed data"""
        return ljm.eStreamRead(self.handle)

    def write_analog(self, channel: str, value: float):
        """Write to DAC"""
        ljm.eWriteName(self.handle, channel, value)

    def setup_dio_clock(self, channel: str, frequency: int, duty_cycle: int = 50):
        """Setup DIO as hardware PWM clock"""
        try:
            # First, ensure the pin is properly reset
            ljm.eWriteName(self.handle, f"{channel}_EF_ENABLE", 0)
            time.sleep(0.01)  # Small delay to ensure disable takes effect

            # Configure as PWM output (EF Index 0)
            ljm.eWriteName(self.handle, f"{channel}_EF_INDEX", 0)
            ljm.eWriteName(self.handle, f"{channel}_EF_CONFIG_A", frequency)
            ljm.eWriteName(self.handle, f"{channel}_EF_CONFIG_B", duty_cycle)
            ljm.eWriteName(self.handle, f"{channel}_EF_ENABLE", 1)

        except Exception as e:
            print(f"      WARNING: Failed to setup {channel} as clock: {e}")
            print(f"      Continuing without {channel} clock output...")
            return False
        return True

    def disable_dio_clock(self, channel: str):
        """Disable DIO clock"""
        ljm.eWriteName(self.handle, f"{channel}_EF_ENABLE", 0)

    def write_dio(self, channel: str, value: int):
        """Write to DIO (toggle mode)"""
        ljm.eWriteName(self.handle, channel, int(value))

    def close(self):
        """Clean shutdown"""
        ljm.close(self.handle)


# ============================================
# CONTROL SYSTEM
# ============================================


class T8ControlSystem:
    """Main control system"""

    def __init__(self, config: SystemConfig):
        self.config = config

        # Initialize hardware with appropriate connection type
        if config.CONNECTION_TYPE.upper() == "USB":
            self.hw = T8Hardware("USB", config.USB_DEVICE)
        elif config.CONNECTION_TYPE.upper() == "ETHERNET":
            self.hw = T8Hardware("ETHERNET", config.IP_ADDRESS)
        else:
            raise ValueError(f"Invalid connection type: {config.CONNECTION_TYPE}")

        # Store latest ADC readings
        self.adc_readings: Dict[str, float] = {}

        # Store latest DAC outputs
        self.dac_outputs: Dict[str, float] = {}

        # DIO toggle state for toggle mode
        self.dio_states: Dict[str, int] = {}
        self.dio_last_toggle: Dict[str, float] = {}

        # CSV logging
        self.csv_file = None
        self.csv_writer = None
        self.csv_filename = None

    def setup(self):
        """Initialize system"""

        print("=" * 50)
        print(f"[{_time_now_str()}] [INFO] Initializing T8 Control System")
        print("=" * 50)

        # Setup ADC streaming
        print(f"\n[{_time_now_str()}] [ADC] Streaming: {self.config.ADC_CHANNELS}")
        print(f"      Rate: {self.config.ADC_STREAM_RATE} Hz")
        self.hw.start_streaming(self.config.ADC_CHANNELS, self.config.ADC_STREAM_RATE)

        # Setup DIO
        print(f"\n[{_time_now_str()}] [DIO] Configuration:")
        for dio_name, dio_config in self.config.DIO_CONFIG.items():
            if not dio_config["enabled"]:
                continue

            if dio_config["mode"] == "clock":
                print(f"      {dio_name}: Clock @ {dio_config['frequency']} Hz", end="")
                success = self.hw.setup_dio_clock(dio_name, dio_config["frequency"])
                if success:
                    print(" ✓")
                else:
                    print(" ✗")

            elif dio_config["mode"] == "toggle":
                print(f"      {dio_name}: Toggle @ {dio_config['frequency']} Hz")
                self.dio_states[dio_name] = 0
                self.dio_last_toggle[dio_name] = time.perf_counter()

        # Setup DAC
        print(f"\n[{_time_now_str()}] [DAC] Configuration:")
        for dac_name, dac_config in self.config.DAC_CONFIG.items():
            if not dac_config["enabled"]:
                continue

            if dac_config["custom_function"] is None:
                print(f"      {dac_name}: DISABLED (no custom function)")
                dac_config["enabled"] = False
            else:
                print(f"      {dac_name}: Enabled @ {dac_config['control_rate']} Hz")
                # Initialize DAC output tracking
                self.dac_outputs[dac_name] = 2.5  # Default safe value

        # Setup CSV logging
        self._setup_csv_logging()

        print("\n" + "=" * 50 + "\n")

    def update_adc_readings(self, stream_data):
        """Extract ADC values from stream and store"""

        for i, channel_name in enumerate(self.config.ADC_CHANNELS):
            samples = stream_data[0][i]
            value = np.mean(samples)  # Average streamed samples
            self.adc_readings[channel_name] = value

    def _setup_csv_logging(self):
        """Setup CSV file for data logging"""
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_filename = f"t8_data_{timestamp}.csv"

        print(f"[{_time_now_str()}] [CSV] Logging to: {self.csv_filename}")

        # Open CSV file
        self.csv_file = open(self.csv_filename, "w", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_file)

        # Create header row
        headers = ["timestamp", "iteration"]

        # Add ADC columns
        for channel in self.config.ADC_CHANNELS:
            headers.append(f"{channel}_V")

        # Add DAC columns
        for dac_name, dac_config in self.config.DAC_CONFIG.items():
            if dac_config["enabled"]:
                headers.append(f"{dac_name}_V")

        # Add DIO columns
        for dio_name, dio_config in self.config.DIO_CONFIG.items():
            if dio_config["enabled"]:
                headers.append(f"{dio_name}_state")

        # Write header
        self.csv_writer.writerow(headers)
        self.csv_file.flush()

    def _log_data_to_csv(self, iteration):
        """Log current data to CSV"""
        if not self.csv_writer:
            return

        # Create data row
        row = [datetime.now().isoformat(), iteration]

        # Add ADC data
        for channel in self.config.ADC_CHANNELS:
            row.append(self.adc_readings.get(channel, 0.0))

        # Add DAC data
        for dac_name, dac_config in self.config.DAC_CONFIG.items():
            if dac_config["enabled"]:
                row.append(self.dac_outputs.get(dac_name, 0.0))

        # Add DIO data
        for dio_name, dio_config in self.config.DIO_CONFIG.items():
            if dio_config["enabled"]:
                if dio_config["mode"] == "toggle":
                    row.append(self.dio_states.get(dio_name, 0))
                else:  # clock mode
                    row.append(1)  # Always 1 for active clock

        # Write row
        self.csv_writer.writerow(row)

        # Flush every 10 iterations to ensure data is saved
        if iteration % 10 == 0:
            self.csv_file.flush()

    def process_dio_toggles(self):
        """Handle DIO toggle mode (separate from clock mode)"""

        current_time = time.perf_counter()

        for dio_name, dio_config in self.config.DIO_CONFIG.items():
            if not dio_config["enabled"] or dio_config["mode"] != "toggle":
                continue

            toggle_period = 1.0 / dio_config["frequency"]

            if current_time - self.dio_last_toggle[dio_name] >= toggle_period:
                # Toggle state
                self.dio_states[dio_name] = 1 - self.dio_states[dio_name]
                self.hw.write_dio(dio_name, self.dio_states[dio_name])
                self.dio_last_toggle[dio_name] = current_time

    def execute_dac_control(self):
        """Execute DAC control functions"""

        for dac_name, dac_config in self.config.DAC_CONFIG.items():
            if not dac_config["enabled"]:
                continue

            # Call custom function with ADC readings
            try:
                dac_voltage = dac_config["custom_function"](self.adc_readings)

                # Clamp to 0-5V
                dac_voltage = max(0, min(5, dac_voltage))

                # Write to DAC
                self.hw.write_analog(dac_name, dac_voltage)

                # Store for logging
                self.dac_outputs[dac_name] = dac_voltage

            except Exception as e:
                print(f"[ERROR] {dac_name} control function failed: {e}")

    def run(self, duration_s: float = None):
        """Main control loop"""

        control_periods = {}
        last_control_times = {}
        iteration = 0

        # Calculate control periods for each enabled DAC
        for dac_name, dac_config in self.config.DAC_CONFIG.items():
            if dac_config["enabled"]:
                control_periods[dac_name] = 1.0 / dac_config["control_rate"]
                last_control_times[dac_name] = time.perf_counter()

        try:
            print(f"[{_time_now_str()}] Running control loop...\n")
            start_time = time.perf_counter()

            while True:
                # Check duration
                if duration_s and (time.perf_counter() - start_time) > duration_s:
                    break

                iteration += 1

                # ========== READ ADC ==========
                stream_data = self.hw.read_stream()
                self.update_adc_readings(stream_data)

                # ========== PROCESS DIO TOGGLES ==========
                self.process_dio_toggles()

                # ========== UPDATE DAC (at configured rates) ==========
                current_time = time.perf_counter()
                for dac_name in control_periods:
                    if current_time - last_control_times[dac_name] >= control_periods[dac_name]:
                        self.execute_dac_control()
                        last_control_times[dac_name] = current_time

                # ========== LOG DATA TO CSV ==========
                self._log_data_to_csv(iteration)

                # ========== STATUS ==========
                if iteration % 10 == 0:
                    status = "  ".join([f"{k}={v:.4f}V" for k, v in self.adc_readings.items()])
                    print(f"[{iteration:5d}] {status}", flush=True)
                else:
                    print(".", end="", flush=True)

        except KeyboardInterrupt:
            print(f"\n\n[{_time_now_str()}] [Warning] User interrupt")

        finally:
            print(f"\n\n[{_time_now_str()}] [SUCCESS] Stream Complete. Shutting down system...")
            self.shutdown()

    def shutdown(self):
        """Clean shutdown"""
        print(f"\n\n[{_time_now_str()}] [INFO] Shutting down...")

        # Stop DACs
        for dac_name in self.config.DAC_CONFIG:
            self.hw.write_analog(dac_name, 2.5)

        # Stop DIO clocks
        for dio_name, dio_config in self.config.DIO_CONFIG.items():
            if dio_config["mode"] == "clock":
                self.hw.disable_dio_clock(dio_name)

        # Stop streaming
        self.hw.stop_streaming()
        self.hw.close()

        # Close CSV file
        if self.csv_file:
            self.csv_file.close()
            print(f"[{_time_now_str()}] [INFO] CSV data saved to: {self.csv_filename}")

        print(f"[{_time_now_str()}] [INFO] Done")


# ============================================
# CUSTOM FUNCTIONS (defined at __main__ level)
# ============================================


def pid_control_function(adc_readings: Dict[str, float]) -> float:
    """
    Example PID control function
    Takes: dict of {port_name: value}
    Returns: DAC voltage (0-5V)
    """

    feedback = adc_readings.get("AIN0", 0.0)
    setpoint = 3.0

    error = setpoint - feedback
    dac_voltage = 2.5 + 0.5 * error

    return dac_voltage


def average_control_function(adc_readings: Dict[str, float]) -> float:
    """
    Example: Average of multiple ports
    Average AIN0 and AIN1, use for control
    """

    values = [adc_readings.get("AIN0", 0.0), adc_readings.get("AIN1", 0.0)]
    avg = np.mean(values)

    setpoint = 2.5
    error = setpoint - avg
    dac_voltage = 2.5 + 0.3 * error

    return dac_voltage


def empty_control_function(adc_readings: Dict[str, float]) -> float:
    """
    Empty function - does nothing
    Use as template for your custom logic
    """

    # Your custom logic here
    # You have access to all ADC readings:
    # adc_readings["AIN0"], adc_readings["AIN1"], etc.

    return 2.5  # Return safe value


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    # ========== CONFIGURE SYSTEM ==========
    config = SystemConfig()

    # ========== CONNECTION CONFIGURATION ==========
    # Choose connection type: "USB" or "ETHERNET"
    config.CONNECTION_TYPE = "USB"  # Change to "ETHERNET" for network connection

    # For USB: "ANY" for first found device, or specific serial number
    config.USB_DEVICE = "ANY"  # e.g., "440010117" for specific device

    # For Ethernet: IP address (only used if CONNECTION_TYPE is "ETHERNET")
    # config.IP_ADDRESS = "192.168.1.100"

    # Define which ADCs to read
    config.ADC_CHANNELS = ["AIN0", "AIN1"]
    config.ADC_STREAM_RATE = 1000  # Hz

    # Configure DAC0 with control function
    config.DAC_CONFIG["DAC0"]["enabled"] = True
    config.DAC_CONFIG["DAC0"]["control_rate"] = 50  # Hz
    config.DAC_CONFIG["DAC0"]["custom_function"] = average_control_function

    # Configure DAC1 (optional)
    config.DAC_CONFIG["DAC1"]["enabled"] = False

    # Configure DIO0 as 1 kHz clock
    config.DIO_CONFIG["DIO0"]["enabled"] = False
    config.DIO_CONFIG["DIO0"]["mode"] = "clock"
    config.DIO_CONFIG["DIO0"]["frequency"] = 1000  # Hz

    # Configure DIO1 as toggle
    config.DIO_CONFIG["DIO1"]["enabled"] = False
    config.DIO_CONFIG["DIO1"]["mode"] = "toggle"
    config.DIO_CONFIG["DIO1"]["frequency"] = 10  # Hz

    # ========== RUN SYSTEM ==========
    system = T8ControlSystem(config)
    system.setup()

    try:
        system.run(duration_s=5)  # Run for XX seconds (or None for infinite)
    except Exception as e:
        print(f"Fatal error: {e}")
