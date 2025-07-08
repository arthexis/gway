@echo off
setlocal

rem Ensure the script runs from its own directory
cd /d "%~dp0"

rem Parse arguments
set "ACTION=install"
set "RECIPE="
set "FORCE_FLAG="
set "DEBUG_FLAG="
set "USER_FLAG="
set "PASSWORD_FLAG="
:parse_args
if "%~1"=="" goto end_parse_args
if "%~1"=="--remove" (
    set "ACTION=remove"
) else if "%~1"=="--repair" (
    set "ACTION=repair"
) else if "%~1"=="--force" (
    set "FORCE_FLAG=--force"
 ) else if "%~1"=="--debug" (
    set "DEBUG_FLAG=--debug"
 ) else if "%~1"=="--user" (
    if "%~2"=="" (
        echo ERROR: --user requires a value
        exit /b 1
    )
    set "USER_FLAG=--user %~2"
    shift
 ) else if "%~1"=="--password" (
    if "%~2"=="" (
        echo ERROR: --password requires a value
        exit /b 1
    )
    set "PASSWORD_FLAG=--password %~2"
    shift
) else (
    if not defined RECIPE (
        set "RECIPE=%~1"
    ) else (
        echo ERROR: Unexpected argument %1
        exit /b 1
    )
)
shift
goto parse_args
:end_parse_args

if "%ACTION%"=="repair" if not defined RECIPE (
    echo Repairing installed gway services...
    for /f "usebackq delims=" %%R in (
        `python "%~dp0tools\windows_service.py" list-recipes`
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
    deactivate
)

rem No-arg case
if not defined RECIPE (
    echo GWAY has been set up in .venv.
    echo To install a Windows service for a recipe, run:
    echo   install.bat ^<recipe^> [--debug] [--user ^<account^> --password ^<pass^>]
    echo To remove a Windows service, run:
    echo   install.bat ^<recipe^> --remove [--force]
    echo To repair a Windows service, run:
    echo   install.bat ^<recipe^> --repair
    echo To repair all existing services, run:
    echo   install.bat --repair
    goto :eof
)

if not exist "recipes\%RECIPE%.gwr" (
    echo ERROR: Recipe '%RECIPE%' not found at recipes\%RECIPE%.gwr
    exit /b 1
)

for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "$n='%RECIPE%'; $n=$n -replace '[\\/]','-'; $n=$n -replace '[^a-zA-Z0-9_-]','-'; Write-Output $n"`) do set "SAFE_RECIPE=%%S"
set "SERVICE_NAME=gway-%SAFE_RECIPE%"
rem Path to helper script
set "SERVICE_PY=%~dp0tools\windows_service.py"

if "%ACTION%"=="install" (
    echo Installing Windows service %SERVICE_NAME% for recipe %RECIPE%...
    python "%SERVICE_PY%" install --name %SERVICE_NAME% --recipe %RECIPE% %DEBUG_FLAG% %USER_FLAG% %PASSWORD_FLAG%
    python "%SERVICE_PY%" start --name %SERVICE_NAME%
) else if "%ACTION%"=="remove" (
    echo Removing Windows service %SERVICE_NAME% for recipe %RECIPE%...
    python "%SERVICE_PY%" stop --name %SERVICE_NAME%
    python "%SERVICE_PY%" remove --name %SERVICE_NAME% --recipe %RECIPE% %FORCE_FLAG%
) else (
    echo Repairing Windows service %SERVICE_NAME% for recipe %RECIPE%...
    python "%SERVICE_PY%" stop --name %SERVICE_NAME%
    python "%SERVICE_PY%" remove --name %SERVICE_NAME% --recipe %RECIPE% %FORCE_FLAG%
    python "%SERVICE_PY%" install --name %SERVICE_NAME% --recipe %RECIPE% %DEBUG_FLAG% %USER_FLAG% %PASSWORD_FLAG%
    python "%SERVICE_PY%" start --name %SERVICE_NAME%
)

endlocal
