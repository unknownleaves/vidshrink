@echo off
title Build VidShrink.exe
cd /d "%~dp0"
echo Installing build tools...
py -3 -m pip install --upgrade pyinstaller -r requirements.txt || python -m pip install --upgrade pyinstaller -r requirements.txt
echo Building VidShrink.exe ...
set ARGS=--noconfirm --onefile --windowed --name VidShrink --icon vidshrink.ico --add-data "vidshrink.ico;." --add-data "icon.png;." vidshrink.py
py -3 -m PyInstaller %ARGS% || python -m PyInstaller %ARGS%
echo.
echo Done! Your app is in the "dist" folder: dist\VidShrink.exe
echo Run "Create Desktop Shortcut.bat" again to point your shortcut at the .exe.
pause
