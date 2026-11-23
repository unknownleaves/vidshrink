@echo off
title VidShrink
cd /d "%~dp0"
where pythonw >/dev/null 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0vidshrink.py"
    exit /b
)
where py >/dev/null 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0vidshrink.py"
    exit /b
)
echo Python was not found.
echo Install Python 3 from https://www.python.org/downloads/  (tick "Add python.exe to PATH")
pause
