"""
02d_ophyd_T8_simple_streaming.py - Simple Real-Time Streaming

Simple approach with just 2 main functions:
1. setup_plot() - Initialize the plot
2. update_plot() - Get data and update plot with undersampling

Performance optimization:
- Limits plot updates to 200 points/second max
- Undersamples high-rate data using stride
"""

import time
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

import ophyd_labjack_t8 as lt8o
from ophyd_labjack_t8 import LabJackT8Ophyd


def datenow_str():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def print_info(message):
    print(f"[INFO {datenow_str()}] {message}")


class SimpleLabJackStreamer:
    """Simple streaming with just 2 main functions."""

    def __init__(self, detector, plot_window_seconds=3.0, max_plot_rate=200):
        self.detector = detector
        self.plot_window_seconds = plot_window_seconds
        self.max_plot_rate = max_plot_rate  # Max points per second to plot

        # Calculate stride for undersampling - FIX THE CALCULATION
        points_per_acquisition = int(detector.sample_rate * detector.acq_time)
        acquisitions_per_second = 1.0 / detector.acq_time
        actual_points_per_second = detector.sample_rate  # This is the real rate

        self.stride = max(1, int(actual_points_per_second / max_plot_rate))

        print_info(f"Streaming at {detector.sample_rate:.0f} Hz, showing {max_plot_rate} points/s")

        # Data storage
        self.plot_times = []
        self.plot_data = {ch: [] for ch in detector.channel_names}

        # Setup plot
        self.setup_plot()

    def setup_plot(self):
        """Initialize the matplotlib plot."""
        print_info("Setting up plot...")

        num_channels = len(self.detector.channel_names)
        self.fig, self.axes = plt.subplots(num_channels, 1, figsize=(12, 4 * num_channels))

        if num_channels == 1:
            self.axes = [self.axes]

        # Create lines
        colors = ["blue", "red", "green", "orange", "purple"]
        self.lines = []

        for i, (ax, ch_name) in enumerate(zip(self.axes, self.detector.channel_names)):
            color = colors[i % len(colors)]
            (line,) = ax.plot([], [], color=color, linewidth=1.0, marker=".", alpha=0.8)
            self.lines.append(line)

            ax.set_title(f"{ch_name} - Live Stream", fontsize=14)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Voltage (V)")
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.ion()
        plt.show()
        print_info("Plot ready!")

    def update_plot(self):
        """Get new data and update plot."""
        try:
            # Get new data
            status = self.detector.trigger()
            while not status.done:
                time.sleep(0.001)

            # Get waveforms and add to plot data immediately
            sample_rate = self.detector.sample_rate

            for ch_name in self.detector.channel_names:
                waveform_attr = f"{ch_name}_waveform"
                if hasattr(self.detector, waveform_attr):
                    waveform = getattr(self.detector, waveform_attr).get()

                    if hasattr(waveform, "__len__") and len(waveform) > 0:
                        # Create time vector for this waveform
                        dt = 1.0 / sample_rate
                        if self.plot_times:
                            start_time_waveform = self.plot_times[-1] + dt
                        else:
                            start_time_waveform = 0.0

                        times = [start_time_waveform + i * dt for i in range(len(waveform))]

                        # Undersample using stride for better performance
                        if self.stride > 1:
                            waveform = waveform[:: self.stride]
                            times = times[:: self.stride]

                        # Add to plot data
                        self.plot_data[ch_name].extend(waveform)
                        if ch_name == self.detector.channel_names[0]:  # Only add times once
                            self.plot_times.extend(times)

            # Trim old data outside window (keep data moving)
            if self.plot_times:
                current_plot_time = self.plot_times[-1]
                cutoff_time = current_plot_time - self.plot_window_seconds

                # Remove old points efficiently
                while self.plot_times and self.plot_times[0] < cutoff_time:
                    self.plot_times.pop(0)
                    for ch_name in self.detector.channel_names:
                        if self.plot_data[ch_name]:
                            self.plot_data[ch_name].pop(0)

            # Update plot lines efficiently
            for i, ch_name in enumerate(self.detector.channel_names):
                if len(self.plot_data[ch_name]) > 1 and len(self.plot_times) > 1:
                    # Use all available data for smooth plotting
                    min_len = min(len(self.plot_times), len(self.plot_data[ch_name]))
                    if min_len > 1:
                        x_data = self.plot_times[-min_len:]
                        y_data = self.plot_data[ch_name][-min_len:]

                        # Update line data
                        self.lines[i].set_data(x_data, y_data)

                        # Auto-scale axes for real-time view
                        if x_data:
                            x_range = self.plot_window_seconds
                            x_max = x_data[-1]
                            x_min = x_max - x_range
                            self.axes[i].set_xlim(x_min, x_max + 0.1)

                        if y_data:
                            y_min, y_max = min(y_data), max(y_data)
                            margin = (y_max - y_min) * 0.1 if y_max != y_min else 0.1
                            self.axes[i].set_ylim(y_min - margin, y_max + margin)

            # Refresh plot
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()

        except Exception as e:
            print_info(f"Update error: {e}")
            return False

        return True


def main(
    name,
    active_AI_channels,
    sample_rate,  # Very low rate for fast acquisitions
    acq_time,  # 10ms acquisitions = 1 point each, 100 Hz update rate
    enable_waveforms,
    verbose,
    save_raw_to_csv,
):
    """Main execution."""
    print_info("🚀 Starting Simple LabJack Streaming")

    try:
        # Clean up any existing connections
        lt8o.close_all_labjacks()
        time.sleep(0.2)

        # Initialize detector - MINIMAL settings for maximum speed
        detector = LabJackT8Ophyd(
            name=name,
            active_AI_channels=active_AI_channels,
            sample_rate=sample_rate,
            acq_time=acq_time,
            enable_waveforms=enable_waveforms,
            verbose=verbose,
            save_raw_to_csv=save_raw_to_csv,
        )

        print_info("✅ LabJack initialized")

        # Start continuous streaming
        detector.start_continuous_stream(buffer_size_seconds=1.0)

        # Create streamer
        streamer = SimpleLabJackStreamer(
            detector=detector,
            plot_window_seconds=3.0,
            max_plot_rate=200,
        )

        # Main loop - run for 60 seconds then auto-stop
        print_info("🎬 Starting stream... (will run for 60 seconds)")
        start_time = time.time()
        acquisition_count = 0

        while time.time() - start_time < 60:
            success = streamer.update_plot()
            if not success:
                break

            acquisition_count += 1
            if acquisition_count % 100 == 0:
                print_info(f"Acquisition #{acquisition_count} - running...")

    except Exception as e:
        print_info(f"Error: {e}")

    finally:
        # Cleanup
        try:
            detector.stop_continuous_stream()
            detector.close()
            print_info("🔌 LabJack closed")
        except Exception as e:
            print_info(f"Cleanup fallback: {e}")
            lt8o.close_all_labjacks()
        print_info("✅ Cleanup completed")


if __name__ == "__main__":
    main(
        name="simple_stream",
        active_AI_channels=[0, 1],
        sample_rate=100.0,  # Very low rate for fast acquisitions
        acq_time=0.01,  # 10ms acquisitions = 1 point each, 100 Hz update rate
        enable_waveforms=True,
        verbose=False,
        save_raw_to_csv=False,
    )
    print_info("📊 Plot stays open - close window when done")
    plt.show(block=True)
