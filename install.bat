@echo off
setlocal

rem Ensure the script runs from its own directory
cd /d "%~dp0"

rem Create .venv and install package if not present
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing gway in editable mode...
    python -m pip install --upgrade pip
    python -m pip install -e .
    deactivate
)

endlocal
