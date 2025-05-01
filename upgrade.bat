@echo off
setlocal enabledelayedexpansion
echo [1] Stashing local changes (if any)...

REM Check if inside a Git repo
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo Not a git repository.
    exit /b 1
)

git stash save "Auto-stash before upgrade" >nul 2>&1

echo [2] Pulling latest code from Git...
for /f "delims=" %%i in ('git pull') do (
    set "GIT_OUTPUT=%%i"
)

echo !GIT_OUTPUT!
if "!GIT_OUTPUT!"=="Already up to date." (
    echo No updates pulled. Restoring stash (if any) and exiting...
    git stash pop >nul 2>&1
    exit /b 0
)

echo [3] Reinstalling package in editable mode...
call .venv\Scripts\activate
pip install -e .

echo [4] Ensuring scripts are executable (Windows: no chmod needed)...

echo [5] Running test command...
gway hello-world

echo Upgrade completed successfully.
echo.
endlocal
