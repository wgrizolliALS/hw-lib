import glob
import os
import sys

if sys.platform != "win32":
    print(
        "This script generates Windows .bat files. To avoid confusion, this script will only run on Windows.\nExiting now!."
    )
    sys.exit(1)

# Get the current directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Find all .py files in the current directory
python_files = glob.glob(os.path.join(current_dir, "*.py"))

# get _current python executable name (e.g., python, python3, etc.)
python_executable = os.path.basename(sys.executable)
python_executable_folder = os.path.dirname(sys.executable)
print(f"\n\nCurrent Python executable: {sys.executable}\n")

if not python_files:
    print("No Python files found in the current directory.")
    sys.exit(0)

# Create a .bat file to run each Python script


tail_script = r"""
set "PY=%EXEC_PATH%\python.exe"
set "PYTHONPATH=%EXEC_PATH%\Lib\site-packages;%PYTHONPATH%"
set "PATH=%EXEC_PATH%\Library\bin;%EXEC_PATH%\Scripts;%PATH%"

echo ######## Running "%SCRIPT%" ########
echo ######## Using "%PY%" ########

"%PY%" "%SCRIPT%"

set "rc=%ERRORLEVEL%"
echo.
echo DONE! Press any key to exit...
echo (It may close terminal window if you ran by double-clicking this .bat file)
pause >nul
echo Exiting now.
exit /b %rc%
"""

for py_file in python_files:
    if os.path.normcase(os.path.abspath(py_file)) == os.path.normcase(os.path.abspath(__file__)):
        continue  # Skip this script itself
    with open(os.path.join(current_dir, f"{os.path.splitext(os.path.basename(py_file))[0]}.bat"), "w") as bat_file:
        # Get the base name of the Python file (without extension)
        base_name = os.path.splitext(os.path.basename(py_file))[0]

        bat_file.write("\n@echo off\n\n")
        bat_file.write(f'set "EXEC_PATH={python_executable_folder}"\n')
        bat_file.write(f'set "SCRIPT={py_file}"\n')
        bat_file.write(tail_script)

        print(f"* Created {base_name}.bat")

print("\nDONE! Check folder  for the .bat files:")
print(f"{current_dir}")

print("\nHOW-TO-USE: In Windows, you can double-click the .bat files to run the corresponding Python scripts.\n\n")
