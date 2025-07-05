@echo off
setlocal

rem Ensure the script runs from its own directory
cd /d "%~dp0"

rem Repair previously installed services
if "%~1"=="--repair" (
    echo Repairing installed gway services...
    for /f "usebackq delims=" %%R in (
        `powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\list_services.ps1"`
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
    echo To repair all existing services, run:
    echo   install.bat --repair
    goto :eof
)

set "RECIPE=%~1"
if not exist "recipes\%RECIPE%.gwr" (
    echo ERROR: Recipe '%RECIPE%' not found at recipes\%RECIPE%.gwr
    exit /b 1
)

for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "$n='%RECIPE%'; $n=$n -replace '[\\/]','-'; $n=$n -replace '[^a-zA-Z0-9_-]','-'; Write-Output $n"`) do set "SAFE_RECIPE=%%S"
set "SERVICE_NAME=gway-%SAFE_RECIPE%"
set "BATPATH=%~dp0gway.bat"

echo Installing Windows service %SERVICE_NAME% for recipe %RECIPE%...
sc.exe create "%SERVICE_NAME%" binPath= "cmd /c \"\"%BATPATH%\" -r %RECIPE%\"" start= auto
sc.exe failure "%SERVICE_NAME%" reset= 0 actions= restart/5000
sc.exe failureflag "%SERVICE_NAME%" 1
sc.exe start "%SERVICE_NAME%"
sc.exe query "%SERVICE_NAME%"

endlocal
