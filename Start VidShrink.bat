@echo off
title VidShrink
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
    echo Python was not found.
    echo Install Python 3 from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
    pause
    exit /b
)
%PY% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo Installing the interface library ^(one time only^)...
    %PY% -m pip install --disable-pip-version-check -r requirements.txt
)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0vidshrink.py" ^& exit /b)
start "" pyw -3 "%~dp0vidshrink.py"
