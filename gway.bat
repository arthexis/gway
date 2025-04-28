@echo off
setlocal

:: Change to the directory containing this script
cd /d "%~dp0"

:: Activate the virtual environment
call .venv\Scripts\activate.bat

:: Run the Python module
python -m gway %*

:: Deactivate the virtual environment
deactivate

endlocal
