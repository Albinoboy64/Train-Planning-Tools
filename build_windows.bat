@echo off
REM Optional: build TrainPlanningTools.exe yourself on a Windows PC (no admin rights needed).
REM Mirrors the release build (.github\workflows\build-windows.yml): Python 3.12, the same pinned packages
REM (packaging\build-requirements.txt), lint, type-check, tests, build and a smoke test of the exe.
REM One deliberate difference: the release compiles PyInstaller's bootloader from source (fewer false virus
REM warnings), which needs a C compiler; this script uses PyInstaller's ready-made bootloader instead.
REM Requires Python 3.12 installed for the current user (python.org installer, "Install for me only").
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" || (
    echo Python 3.12 is needed - the release is built with 3.12 and the pinned packages are for it.
    goto :failed
)
REM a clean environment each time, so nothing left from an earlier build changes this one
python -m venv --clear .venv || goto :failed
call .venv\Scripts\activate.bat
python -m pip install pip==26.3 || goto :failed
pip install --no-deps -r packaging\build-requirements.txt || goto :failed
pip check || goto :failed
ruff check . || goto :failed
mypy || goto :failed
python -m pytest -q tests || goto :failed
python packaging\make_version_file.py version_info.txt || goto :failed
pyinstaller --noconfirm packaging\TrainPlanningTools.spec || goto :failed
REM smoke test: the built exe compares two small CWNs (as the release build does)
python -c "import sys, os; sys.path.insert(0, 'tests'); import test_compare as t; d = os.path.abspath('smoke'); os.makedirs(d, exist_ok=True); t.make(os.path.join(d, 'a.xlsx'), t.BTN_ORIG, t.VIC_ORIG); b, v = t._upd_rows(); t.make(os.path.join(d, 'b.xlsx'), b, v)" || goto :failed
if exist smoke\smoke.xlsx del smoke\smoke.xlsx
start /wait "" dist\TrainPlanningTools.exe --original smoke\a.xlsx --updated smoke\b.xlsx --out smoke --name smoke
if not exist smoke\smoke.xlsx (
    echo The built exe did not produce its smoke-test output.
    goto :failed
)
echo.
echo Built: dist\TrainPlanningTools.exe
pause
exit /b 0
:failed
echo.
echo The build stopped because a check failed (see above).
pause
exit /b 1
