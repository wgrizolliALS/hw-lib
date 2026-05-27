# hw-lib

Standalone hardware acquisition library for LabJack T8 and Keithley instruments. No framework dependencies — works without Ophyd or Bluesky.

For Ophyd/Bluesky integration see the companion repository [hw-lib-ophyd](https://github.com/wgrizolliALS/hw-lib-ophyd).

## Supported Hardware

- **LabJack T8** — Multi-channel analog input, DAC output, DIO, streaming
- **Keithley** — Precision measurement instruments (serial/SCPI)

## Project Structure

```text
hw-lib/
├── src/
│   └── keithley_utils.py           # Keithley serial/SCPI utilities
├── labjack examples/
│   ├── 00a_check_installation.py   # Verify LJM installation
│   ├── 00b_detected_connected_hw.py
│   ├── 00c_close_all_connected_labjacks.py
│   ├── 01a_T8_acquire_standalone.ipynb/.py
│   ├── 01b_T8_acquire_standalone_continuous.ipynb
│   └── 01c_t8_stream.py
└── keithley examples/
    ├── 00a_check_installation.py
    ├── 00b_detect_connected_kley.py
    ├── 00b_keithley_query_terminal.py
    ├── 01a_keithley_acq_waveform_inter_terminal.ipynb/.py
    └── 01b_keithley_acq_waveform_check_jitter.py
```

## Requirements

- Python >= 3.12
- [LabJack LJM library](https://support.labjack.com/docs/ljm-library-overview) installed on the host machine

All Python dependencies are managed via `pyproject.toml`.

## Installation

Install in editable mode from the project root:

```bash
# Core only (scripts and .py examples)
uv pip install -e .

# With Jupyter support (to run .ipynb notebooks, interactive plotting)
uv pip install -e .[jupyter]

# For development (nbstripout, pytest)
uv pip install -e .[dev]

# Full install
uv pip install -e .[jupyter,dev]
```

### Activate nbstripout (recommended)

After installing the `dev` extra, run once inside the repo to strip notebook outputs before every commit:

```bash
nbstripout --install
```
