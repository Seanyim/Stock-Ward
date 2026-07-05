@echo off
REM ============================================================
REM  Stock-Ward v4 launcher (Windows)
REM  Creates/activates a local virtual environment (.venv),
REM  installs/updates dependencies, then starts the server.
REM ============================================================
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYEXE=%VENV_DIR%\Scripts\python.exe"

REM --- 1. Create the venv on first run -----------------------
if not exist "%PYEXE%" (
    echo [Stock-Ward] Creating virtual environment in %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [Stock-Ward] ERROR: could not create venv. Is Python on PATH?
        pause
        exit /b 1
    )
    "%PYEXE%" -m pip install --upgrade pip
    set "FRESH=1"
)

REM --- 2. Install / refresh dependencies ---------------------
REM   Uses a stamp file so deps are only reinstalled when
REM   requirements.txt changes (fast subsequent launches).
set "STAMP=%VENV_DIR%\.req.stamp"
set "NEEDINSTALL="
if defined FRESH set "NEEDINSTALL=1"
if not exist "%STAMP%" set "NEEDINSTALL=1"
if exist "%STAMP%" (
    for /f %%i in ('powershell -NoProfile -Command "(Get-Item requirements.txt).LastWriteTime -gt (Get-Item '%STAMP%').LastWriteTime"') do (
        if /i "%%i"=="True" set "NEEDINSTALL=1"
    )
)
if defined NEEDINSTALL (
    echo [Stock-Ward] Installing dependencies ...
    "%PYEXE%" -m pip install -r requirements.txt
    echo done > "%STAMP%"
)

REM --- 3. Launch ---------------------------------------------
echo [Stock-Ward] Starting server under virtual environment ...
"%PYEXE%" run.py
pause
endlocal
