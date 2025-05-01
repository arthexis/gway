@echo off
setlocal enabledelayedexpansion
echo [1] Stashing local changes (if any)...

REM Check if inside a Git repo
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo Not a git repository.
    exit /b 1
)

git stash save "Auto-stash before upgrade"

echo [2] Pulling latest code from Git...
git pull

echo [3] Reinstalling package in editable mode...
call .venv\Scripts\activate
pip install -e .

echo [4] Ensuring scripts are executable (Windows: no chmod needed)...

echo [5] Running test command...
gway hello-world

echo Upgrade completed successfully.
echo
endlocal
