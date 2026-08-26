@echo off
rem One-click launcher for Windows: builds a virtual environment on first run,
rem then starts the MThreadDraw desktop app. Double-click it.
setlocal
cd /d "%~dp0"

set "PY=venv\Scripts\python.exe"

if not exist "%PY%" (
    echo Creating a virtual environment in venv\ ...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo Could not create a virtual environment.
        echo Install Python 3.9 or newer from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" during setup.
        pause
        exit /b 1
    )

    echo Installing MThreadDraw and its dependencies. This takes a minute the first time ...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -e ".[gui]"
    if errorlevel 1 (
        echo.
        echo Installation failed - see the output above.
        pause
        exit /b 1
    )
)

rem adb, if this machine has none of its own. Downloaded once, from Google.
where adb >nul 2>&1
if errorlevel 1 (
    if not exist "platform-toolsdb.exe" (
        echo Fetching adb ...
        "%PY%" toolsetch_platform_tools.py
    )
)

"%PY%" -m mthread_draw
if errorlevel 1 (
    echo.
    echo MThreadDraw exited with an error. Check that USB debugging is enabled
    echo on the phone and that the cable carries data.
    pause
)
