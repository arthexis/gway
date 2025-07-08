@echo off
setlocal

rem Change to the directory containing this script
cd /d "%~dp0"

set "ACTION_LOG=.upgrade_action.log"

set FORCE=0
:parse_args
if "%~1"=="" goto after_args
if "%~1"=="--force" set FORCE=1
if "%~1"=="-h" goto usage
if "%~1"=="--help" goto usage
shift
goto parse_args

:usage
echo Usage: %~nx0 [--force]
echo   --force    Reinstall and test even if no update is detected.
exit /b 0

:after_args
for /f %%H in ('git rev-parse HEAD') do set "OLD_HASH=%%H"

call :log_action "Current hash: %OLD_HASH%"

echo Fetching latest commits...
git fetch --all --prune

echo Resetting to origin/main...
git reset --hard origin/main
git clean -fd

for /f %%H in ('git rev-parse HEAD') do set "NEW_HASH=%%H"

if "%OLD_HASH%"=="%NEW_HASH%" if %FORCE%==0 (
    echo No updates detected. Skipping reinstall.
    goto success
)

if not exist ".venv" (
    echo Error: .venv directory not found.
    call :log_action "ERROR: .venv directory not found!"
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .

call :run_tests
if errorlevel 1 (
    call :log_action "Upgrade failed at commit: %NEW_HASH%"
    exit /b 1
)

:success
echo Upgrade and test completed successfully.
call :log_action "Upgrade success: %NEW_HASH%"
exit /b 0

:log_action
echo %DATE% %TIME% ^| %*>> "%ACTION_LOG%"
exit /b 0

:run_tests
gway test --on-failure abort
exit /b %ERRORLEVEL%
