@echo off
rem ---------------------------------------------------------------------------
rem  ALSHAN POS SYSTEM - development launcher
rem  Requires Python 3.11+ with PySide6 installed (pip install -r requirements.txt)
rem  Shop owners should use the installed program instead of this file.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this computer.
    echo Install Python 3.11 or newer and then run: pip install -r requirements.txt
    pause
    exit /b 1
)

start "" pythonw "%~dp0run.py"
endlocal
