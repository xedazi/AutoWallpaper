@echo off
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed --name AutoWallpaper app.py
echo.
echo Build finished. EXE is in dist\AutoWallpaper.exe
pause
