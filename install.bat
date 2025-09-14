@echo off
setlocal

rem Ensure the script runs from its own directory
cd /d "%~dp0"

rem Default to installing the gway command
set INSTALL_BIN=1
for %%I in (%*) do (
    if "%%I"=="--no-bin" set INSTALL_BIN=0
    if "%%I"=="--bin" set INSTALL_BIN=1
)

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

if "%INSTALL_BIN%"=="1" (
    echo Installing gway.bat to %SystemRoot%\gway.bat...
    copy /Y "%~dp0gway.bat" "%SystemRoot%\gway.bat" >nul
)

endlocal
