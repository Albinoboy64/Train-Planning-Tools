@echo off
REM Optional: build TrainPlanningTools.exe yourself on a Windows PC (no admin rights needed).
REM Requires Python 3.12 installed for the current user (python.org installer, "Install for me only").
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller pytest pillow ruff==0.17.6 mypy==2.4.1
ruff check . || goto :failed
mypy || goto :failed
python -m pytest -q tests || goto :failed
python packaging\make_version_file.py version_info.txt
pyinstaller --noconfirm packaging\TrainPlanningTools.spec || goto :failed
echo.
echo Built: dist\TrainPlanningTools.exe
pause
exit /b 0
:failed
echo.
echo The build stopped because a check failed (see above).
pause
exit /b 1
