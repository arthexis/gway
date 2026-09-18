@echo off
setlocal

rem Change to the directory containing this script
cd /d "%~dp0"

set "ACTION_LOG=.upgrade_action.log"

set "FORCE=0"
set "LATEST=0"
set "REQUEST_FULL_TEST=0"
set "REQUEST_SKIP_TEST=0"
set "TEST_MODE=smoke"

:parse_args
if "%~1"=="" goto after_args
if /i "%~1"=="--force" set "FORCE=1"
if /i "%~1"=="--latest" set "LATEST=1"
if /i "%~1"=="--test" set "REQUEST_FULL_TEST=1"
if /i "%~1"=="--no-test" set "REQUEST_SKIP_TEST=1"
if "%~1"=="-h" goto usage
if "%~1"=="--help" goto usage
shift
goto parse_args

:usage
echo Usage: %~nx0 [--force] [--latest] [--test] [--no-test]
echo   --force     Reinstall even if no update is detected.
echo   --latest    Always reinstall, skipping the PyPI version check.
echo   --test      Run the full test suite after upgrading.
echo   --no-test   Skip all tests (including the smoke test).
exit /b 0

:after_args
if %REQUEST_FULL_TEST%==1 if %REQUEST_SKIP_TEST%==1 (
    echo Error: --test and --no-test cannot be used together.
    exit /b 1
)
if %REQUEST_FULL_TEST%==1 (
    set "TEST_MODE=full"
) else if %REQUEST_SKIP_TEST%==1 (
    set "TEST_MODE=skip"
)

for /f %%H in ('git rev-parse HEAD') do set "OLD_HASH=%%H"

call :log_action "Current hash: %OLD_HASH%"

echo Fetching latest commits...
git fetch --all --prune

echo Resetting to origin/main...
git reset --hard origin/main
git clean -fd

for /f %%H in ('git rev-parse HEAD') do set "NEW_HASH=%%H"

if "%OLD_HASH%"=="%NEW_HASH%" if %FORCE%==0 if %LATEST%==0 (
    echo No updates detected. Skipping reinstall (use --force or --latest to override).
    call :log_action "No updates: %NEW_HASH%"
    goto skip_upgrade
)

if not exist ".venv" (
    echo Error: .venv directory not found.
    call :log_action "ERROR: .venv directory not found!"
    exit /b 1
)

call .venv\Scripts\activate.bat

if %LATEST%==0 if %FORCE%==0 (
    call :check_versions
    if errorlevel 2 goto skip_upgrade
)

echo Upgrading pip inside the virtual environment...
python -m pip install --upgrade pip
if errorlevel 1 call :log_action "pip upgrade failed"

python -m pip install -e .
if errorlevel 1 (
    echo Warning: package installation failed, continuing.
    call :log_action "pip install failed"
)

call :run_tests
if errorlevel 1 (
    call :log_action "Upgrade failed at commit: %NEW_HASH%"
    exit /b 1
)

if "%TEST_MODE%"=="full" (
    echo Upgrade and full test suite completed successfully.
    call :log_action "Upgrade success (full test): %NEW_HASH%"
) else if "%TEST_MODE%"=="smoke" (
    echo Upgrade and smoke test completed successfully.
    call :log_action "Upgrade success (smoke): %NEW_HASH%"
) else (
    echo Upgrade completed successfully.
    call :log_action "Upgrade success (no test): %NEW_HASH%"
)
exit /b 0

:skip_upgrade
echo Upgrade script completed.
exit /b 0

:log_action
echo %DATE% %TIME% ^| %*>> "%ACTION_LOG%"
exit /b 0

:check_versions
set "CURRENT_VERSION="
set "PYPI_VERSION="
set "VERSION_FILE=%TEMP%\gway_upgrade_version.txt"
python -c "import sys; script = '''import sys
try:
    from importlib import metadata
except ImportError:
    import importlib_metadata as metadata
try:
    print(metadata.version('gway'), end='')
except metadata.PackageNotFoundError:
    pass
except Exception as exc:
    print(f'ERROR:{exc}', file=sys.stderr)
    sys.exit(1)
'''; exec(script)" > "%VERSION_FILE%" 2>nul
set "VERSION_STATUS=%ERRORLEVEL%"
if "%VERSION_STATUS%"=="0" (
    set /p CURRENT_VERSION=<"%VERSION_FILE%"
    if defined CURRENT_VERSION (
        echo Current version: %CURRENT_VERSION%
    ) else (
        echo Installed version not found; proceeding with upgrade.
    )
) else (
    echo Warning: failed to determine installed gway version. Continuing.
    call :log_action "Version check failed: installed"
    set "CURRENT_VERSION="
)
del "%VERSION_FILE%" 2>nul

set "PYPI_FILE=%TEMP%\gway_upgrade_pypi.txt"
python -c "import sys; script = '''import json
import sys
import urllib.error
import urllib.request
try:
    with urllib.request.urlopen('https://pypi.org/pypi/gway/json', timeout=10) as resp:
        data = json.load(resp)
    print(data['info']['version'], end='')
except Exception as exc:
    print(f'ERROR:{exc}', file=sys.stderr)
    sys.exit(1)
'''; exec(script)" > "%PYPI_FILE%" 2>nul
set "PYPI_STATUS=%ERRORLEVEL%"
if "%PYPI_STATUS%"=="0" (
    set /p PYPI_VERSION=<"%PYPI_FILE%"
    if defined PYPI_VERSION (
        echo PyPI version: %PYPI_VERSION%
        if defined CURRENT_VERSION if "%CURRENT_VERSION%"=="%PYPI_VERSION%" (
            echo Installed version matches PyPI. Skipping upgrade (use --latest to override).
            call :log_action "No new PyPI version: %CURRENT_VERSION%"
            del "%PYPI_FILE%" 2>nul
            exit /b 2
        )
    ) else (
        echo Warning: PyPI version response was empty. Continuing with upgrade.
        call :log_action "Version check failed: PyPI empty"
    )
) else (
    echo Warning: failed to fetch PyPI version. Continuing with upgrade.
    call :log_action "Version check failed: PyPI"
)
del "%PYPI_FILE%" 2>nul
exit /b 0

:run_tests
if "%TEST_MODE%"=="skip" (
    echo Skipping tests (--no-test)
    exit /b 0
)
if "%TEST_MODE%"=="full" (
    echo Running full test suite...
    gway test --on-failure abort
    exit /b %ERRORLEVEL%
)
echo Running smoke tests...
gway test --filter smoke --on-failure abort
exit /b %ERRORLEVEL%

