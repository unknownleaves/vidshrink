@echo off
title Build VidShrink.exe
cd /d "%~dp0"
echo Installing PyInstaller...
py -3 -m pip install --upgrade pyinstaller || python -m pip install --upgrade pyinstaller
echo Building VidShrink.exe ...
set ARGS=--noconfirm --onefile --windowed --name VidShrink --icon vidshrink.ico --add-data "vidshrink.ico;." vidshrink.py
py -3 -m PyInstaller %ARGS% || python -m PyInstaller %ARGS%
echo.
echo Done! Your app is in the "dist" folder: dist\VidShrink.exe
echo Run "Create Desktop Shortcut.bat" again to point your shortcut at the .exe.
pause
