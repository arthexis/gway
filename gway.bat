@echo off
setlocal

set "REQ_FILE=requirements.txt"
set "REQ_HASH_FILE=requirements.md5"

:: Change to the directory containing this script
cd /d "%~dp0"

:: If .venv doesn't exist, create it and install gway in editable mode
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies...
    python -m pip install --upgrade pip
    call :EnsureRequirements force
    if errorlevel 1 (
        echo Failed to install requirements.>&2
        deactivate
        goto :END
    )
    python -m pip install -e .

    deactivate
)

:: Activate the virtual environment
call .venv\Scripts\activate.bat

call :EnsureRequirements
if errorlevel 1 (
    echo Failed to install requirements.>&2
    goto :DEACTIVATE
)

:: Run the Python module
python -m gway %*

:DEACTIVATE
:: Deactivate the virtual environment
deactivate

:END
endlocal
goto :EOF

:EnsureRequirements
set "REQUIREMENTS_UPDATED=false"
set "CURRENT_REQ_HASH="
if not exist "%REQ_FILE%" (
    if exist "%REQ_HASH_FILE%" del "%REQ_HASH_FILE%"
    exit /b 0
)

for /f "usebackq delims=" %%H in (`python -c "import hashlib, pathlib, sys;print(hashlib.md5(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())" "%REQ_FILE%"`) do set "CURRENT_REQ_HASH=%%H"

if not defined CURRENT_REQ_HASH (
    echo Failed to compute requirements hash.>&2
    exit /b 1
)

set "STORED_REQ_HASH="
if exist "%REQ_HASH_FILE%" (
    set /p "STORED_REQ_HASH="<"%REQ_HASH_FILE%"
)

set "NEED_INSTALL=0"
if /I "%~1"=="force" (
    set "NEED_INSTALL=1"
) else (
    if "%STORED_REQ_HASH%"=="" (
        set "NEED_INSTALL=1"
    ) else (
        if /I not "%CURRENT_REQ_HASH%"=="%STORED_REQ_HASH%" (
            set "NEED_INSTALL=1"
        )
    )
)

if "%NEED_INSTALL%"=="1" (
    echo Installing requirements...
    python -m pip install -r "%REQ_FILE%"
    if errorlevel 1 (
        exit /b 1
    )
    >"%REQ_HASH_FILE%" (echo %CURRENT_REQ_HASH%)
    set "REQUIREMENTS_UPDATED=true"
)

exit /b 0
