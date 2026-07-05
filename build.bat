@echo off
REM ============================================================
REM  Build Stock-Ward into a standalone Windows app (PyInstaller)
REM  Output: dist\Stock-Ward\Stock-Ward.exe  (ship the whole folder)
REM ============================================================
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYEXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [build] Creating virtual environment ...
    python -m venv "%VENV_DIR%"
    "%PYEXE%" -m pip install --upgrade pip
)

echo [build] Installing dependencies + PyInstaller ...
"%PYEXE%" -m pip install -r requirements.txt
"%PYEXE%" -m pip install pyinstaller

echo [build] Cleaning previous build ...
if exist build rmdir /s /q build
if exist dist\Stock-Ward rmdir /s /q dist\Stock-Ward

echo [build] Packaging ...
"%PYEXE%" -m PyInstaller --noconfirm --clean stockward.spec

echo.
echo [build] DONE.  Your app is in:  dist\Stock-Ward\
echo         Run it by double-clicking:  dist\Stock-Ward\Stock-Ward.exe
echo         (Copy the whole "Stock-Ward" folder to share it.)
echo.
pause
endlocal
