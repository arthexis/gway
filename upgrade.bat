@echo off
setlocal enabledelayedexpansion

echo [1] Checking current commit hash...
for /f %%i in ('git rev-parse HEAD') do set OLD_HASH=%%i

echo [2] Fetching latest commits from Git...
git fetch --all --prune

echo [3] Resetting to origin/main and cleaning up...
git reset --hard origin/main
git clean -fd

for /f %%i in ('git rev-parse HEAD') do set NEW_HASH=%%i

if "!OLD_HASH!"=="!NEW_HASH!" (
    echo No updates detected. Skipping reinstall.
    goto :eof
)

echo [4] Reinstalling package in editable mode...
call .venv\Scripts\activate
pip install -e .

echo [5] Running test command...
gway hello-world

echo Upgrade completed successfully.
echo.
endlocal
