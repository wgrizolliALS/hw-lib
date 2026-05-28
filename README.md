# hw-lib

Standalone hardware acquisition library for LabJack T8 and Keithley instruments. No framework dependencies — works without Ophyd or Bluesky.

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

## Installation using 'uv'

***Requirements***: make sure you have [`git`](https://git-scm.com/install/) and [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed on your system.

### 1. `git clone` repository

```bash
git clone https://github.com/wgrizolliALS/standalone-hw-lib.git
cd standalone-hw-lib
```

### 2. Core installation with `uv`

This will install the core library and its dependencies.

```bash
# Core only (scripts and .py examples)
uv sync
```

### 3. Optional but Recommended

To run the Jupyter notebooks and use interactive plotting, install the `jupyter` extra.

```bash
# With Jupyter support (to run .ipynb notebooks, interactive plotting)
uv sync --extra jupyter
```

### 4. Optional for development

For development purposes, including running tests and using `nbstripout` to clean notebook outputs, install the `dev` extra.

```bash
# For development (nbstripout, pytest)
uv sync --extra dev
nbstripout --install  # Activate nbstripout: Run once to set up nbstripout for this repo
```

### 5. All-in-one installation

```bash
# Full install
uv sync --extra jupyter --extra dev
nbstripout --install # Activate nbstripout: Run once to set up nbstripout for this repo
```

### 6. Activate the environment

After installation, activate the environment to use the installed packages and run the examples.

```bash
# Activate the environment (Linux/Mac)
source .venv/bin/activate
# Activate the environment (Windows)
.venv\Scripts\activate
```

### 7. Verify installation

To verify that the installation was successful, you can run the following command to check that the `hw-lib` package is installed and accessible:

```bash
uv run python -c "import keithley_utils; print('hw-lib installed successfully!')"
```

Or run one of the example scripts to check that the hardware can be accessed:

```bash
uv run python "labjack examples/00a_check_installation.py"
```

## Usage

After installation, you can run the example scripts and notebooks located in the `labjack examples/` and `keithley examples/` directories. These examples demonstrate how to acquire data from LabJack T8 and Keithley instruments using the standalone hardware library.

***ATTENTION***: Make sure your LabJack T8 or Keithley instruments are properly connected and configured before running the examples.

***Note***: Examples were developed and tested using VS Code with the Python extension. You can run the `.py` scripts directly from the command line or use the Jupyter notebooks for an interactive experience.
