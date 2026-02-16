@echo off
REM Build executable for Batch URL Screenshot
REM Output: dist\screencap_url.exe

echo Installing PyInstaller...
pip install pyinstaller

echo.
echo Building executable...
pyinstaller build_exe.spec

echo.
if exist dist\screencap_url.exe (
    echo Build complete: dist\screencap_url.exe
    echo.
    echo To run on another machine:
    echo   1. Copy dist\screencap_url.exe to the target machine
    echo   2. On first run, run: playwright install chromium
    echo      (Or the exe will auto-download Chromium when you capture - needs internet)
    echo   3. Double-click screencap_url.exe and open http://127.0.0.1:5000
) else (
    echo Build failed.
)
