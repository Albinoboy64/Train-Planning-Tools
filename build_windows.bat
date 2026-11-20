@echo off
REM Optional: build RollingStockTools.exe yourself on a Windows PC (no admin rights needed).
REM Requires Python 3.10+ installed for the current user (python.org installer, "Install for me only").
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
python packaging\make_version_file.py version_info.txt
pyinstaller --noconfirm packaging\RollingStockTools.spec
echo.
echo Built: dist\RollingStockTools.exe
pause
