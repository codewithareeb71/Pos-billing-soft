@echo off
rem ===========================================================================
rem  ALSHAN POS SYSTEM - Windows build script
rem
rem  Produces:
rem    dist\ALSHAN_POS_SYSTEM\ALSHAN_POS_SYSTEM.exe   (portable folder)
rem    build\Setup_ALSHAN_POS_SYSTEM_v1.0.0.exe      (installer, if ISCC.exe is present)
rem
rem  Requirements:  Python 3.11+, pip install -r requirements.txt pyinstaller
rem ===========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

echo [1/5] Checking dependencies...
python -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 goto :failed

echo [2/5] Generating the application icon...
python assets\generate_icon.py
if errorlevel 1 goto :failed

echo [3/5] Running tests before packaging...
python tests\smoke_test.py
if errorlevel 1 goto :failed
set QT_QPA_PLATFORM=offscreen
python tests\ui_smoke_test.py
if errorlevel 1 goto :failed

echo [4/5] Building the application with PyInstaller...
rem The page modules are loaded at runtime with importlib.import_module(),
rem which PyInstaller cannot detect on its own - without the list below the
rem packaged app shows "This module could not be opened" on every screen.
rem Enumerating the folder means any future page is picked up automatically.
set "PAGES="
for %%f in ("app\ui\pages\*.py") do (
    if /i not "%%~nf"=="__init__" set "PAGES=!PAGES! --hidden-import app.ui.pages.%%~nf"
)
rem --specpath build\ makes PyInstaller resolve relative paths from the spec
rem folder, so icon and paths are passed as absolute values here.
python -m PyInstaller --noconfirm --clean --windowed ^
  --name ALSHAN_POS_SYSTEM ^
  --icon "%CD%\assets\alshan_pos.ico" ^
  --distpath "%CD%\dist" ^
  --workpath "%CD%\build\work" ^
  --specpath "%CD%\build" ^
  --paths "%CD%" ^
  --hidden-import barcode ^
  --hidden-import barcode.writer ^
  --hidden-import app.services ^
  --hidden-import app.ui.pages ^
  !PAGES! ^
  run.py
if errorlevel 1 goto :failed

if not exist "dist\ALSHAN_POS_SYSTEM\ALSHAN_POS_SYSTEM.exe" goto :failed

echo [5/5] Building the installer with Inno Setup (optional)...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo        Inno Setup was not found - the portable folder in dist\ is ready.
    echo        Install Inno Setup 6 to also produce the installer.
) else (
    %ISCC% /Q "build\alshan_pos.iss"
    if errorlevel 1 goto :failed
)

echo.
echo BUILD COMPLETE
echo   Application : dist\ALSHAN_POS_SYSTEM\ALSHAN_POS_SYSTEM.exe
echo   Installer   : build\Setup_ALSHAN_POS_SYSTEM_v1.0.0.exe
pause
exit /b 0

:failed
echo.
echo BUILD FAILED - see the messages above.
pause
exit /b 1
