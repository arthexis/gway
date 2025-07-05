@echo off
setlocal

rem Change to the directory containing this script
cd /d "%~dp0"

set "SNAPSHOT_FILE=.upgrade_snapshot"
set "ACTION_LOG=.upgrade_action.log"

set FORCE=0
set AUTO=0
:parse_args
if "%~1"=="" goto after_args
if "%~1"=="--force" set FORCE=1
if "%~1"=="--auto" set AUTO=1
if "%~1"=="-h" goto usage
if "%~1"=="--help" goto usage
shift
goto parse_args

:usage
echo Usage: %~nx0 [--force] [--auto]
echo   --force    Reinstall and test even if no update is detected.
echo   --auto     Revert to previous version automatically if upgrade fails.
exit /b 0

:after_args
call :take_snapshot

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
    if %AUTO%==1 goto success
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .

call :run_tests
if errorlevel 1 (
    call :log_action "Upgrade failed at commit: %NEW_HASH%"
    if %AUTO%==1 (
        call :restore_snapshot
        goto success
    ) else (
        set /p ANSWER=Do you want to revert to the previous version? [Y/n] 
        if /I not "%ANSWER%"=="N" if /I not "%ANSWER%"=="n" (
            call :restore_snapshot
        ) else (
            call :log_action "User chose NOT to revert after failed upgrade."
        )
        exit /b 3
    )
)

:success
echo Upgrade and test completed successfully.
call :log_action "Upgrade success: %NEW_HASH%"
exit /b 0

:take_snapshot
for /f %%H in ('git rev-parse HEAD') do set "HASH=%%H"
echo %HASH% > "%SNAPSHOT_FILE%"
call :log_action "Snapshot taken: %HASH%"
exit /b 0

:restore_snapshot
if not exist "%SNAPSHOT_FILE%" (
    echo No snapshot found! Cannot revert.
    call :log_action "No snapshot found: revert skipped."
    exit /b 1
)
set /p HASH=<"%SNAPSHOT_FILE%"
echo Reverting to previous commit: %HASH%
git reset --hard %HASH%
git clean -fd
if exist ".venv" (
    call .venv\Scripts\activate.bat
    python -m pip install -e .
)
call :log_action "Reverted to: %HASH%"
exit /b 0

:log_action
echo %DATE% %TIME% ^| %*>> "%ACTION_LOG%"
exit /b 0

:run_tests
gway test --on-failure abort
exit /b %ERRORLEVEL%
