@echo off
setlocal

:: Change to the directory containing this script
cd /d "%~dp0"

:: If .venv doesn't exist, create it and install gway in editable mode
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing gway in editable mode...
    python -m pip install --upgrade pip
    python -m pip install -e .

    deactivate
)

:: Activate the virtual environment
call .venv\Scripts\activate.bat

:: Run the Python module
python -m gway %*

:: Deactivate the virtual environment
deactivate

endlocal
