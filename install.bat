@echo off
setlocal

rem Ensure the script runs from its own directory
cd /d "%~dp0"

rem Repair previously installed services
if "%~1"=="--repair" (
    echo Repairing installed gway services...
    for /f "usebackq delims=" %%R in (
        `python "%~dp0windows_service.py" list-recipes`
    ) do (
        call "%~f0" %%R
    )
    goto :eof
)

rem Create .venv and install package if not present
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing gway in editable mode...
    python -m pip install --upgrade pip
    python -m pip install -e .
    if exist "temp\requirements.txt" (
        echo Installing additional requirements from temp\requirements.txt...
        python -m pip install -r temp\requirements.txt
    )
    deactivate
)

rem No-arg case
if "%~1"=="" (
    echo GWAY has been set up in .venv.
    echo To install a Windows service for a recipe, run:
    echo   install.bat ^<recipe^>
    echo To remove a Windows service, run:
    echo   install.bat --remove ^<recipe^> [--force]
    echo To repair all existing services, run:
    echo   install.bat --repair
    goto :eof
)

set "ACTION=install"
set "RECIPE=%~1"
set "FORCE_FLAG="
if "%~1"=="--remove" (
    set "ACTION=remove"
    set "RECIPE=%~2"
    if "%~3"=="--force" set "FORCE_FLAG=--force"
)
if not exist "recipes\%RECIPE%.gwr" (
    echo ERROR: Recipe '%RECIPE%' not found at recipes\%RECIPE%.gwr
    exit /b 1
)

for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "$n='%RECIPE%'; $n=$n -replace '[\\/]','-'; $n=$n -replace '[^a-zA-Z0-9_-]','-'; Write-Output $n"`) do set "SAFE_RECIPE=%%S"
set "SERVICE_NAME=gway-%SAFE_RECIPE%"
rem Path to helper script
set "SERVICE_PY=%~dp0windows_service.py"

if "%ACTION%"=="install" (
    echo Installing Windows service %SERVICE_NAME% for recipe %RECIPE%...
    python "%SERVICE_PY%" install --name %SERVICE_NAME% --recipe %RECIPE%
) else (
    echo Removing Windows service %SERVICE_NAME% for recipe %RECIPE%...
    python "%SERVICE_PY%" remove --name %SERVICE_NAME% --recipe %RECIPE% %FORCE_FLAG%
)

endlocal
