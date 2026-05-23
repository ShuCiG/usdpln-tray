@echo off
REM Build a standalone Windows executable using PyInstaller.
REM Output: dist\usdpln-tray\usdpln-tray.exe  (--onedir layout, fast startup).
REM
REM Requires PyInstaller. Install with: pip install pyinstaller

setlocal

echo === Building usdpln-tray.exe ===

python -m PyInstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name usdpln-tray ^
    --add-data "config.example.json;." ^
    --hidden-import chart ^
    tray.py

if errorlevel 1 (
    echo.
    echo Build FAILED. See output above.
    exit /b 1
)

echo.
echo === Build complete ===
echo Executable: dist\usdpln-tray\usdpln-tray.exe
echo.
echo To distribute: zip the entire dist\usdpln-tray\ folder.
echo The .exe needs config.json and rates.db sitting next to it at runtime.
