@echo off
REM Optional: build TrainPlanningTools.exe yourself on a Windows PC (no admin rights needed).
REM Mirrors the release build (.github\workflows\build-windows.yml): Python 3.14, the same pinned packages
REM (packaging\build-requirements.txt), lint, type-check, tests, build and a smoke test of the exe.
REM One deliberate difference: the release compiles PyInstaller's bootloader from source (fewer false virus
REM warnings), which needs a C compiler; this script uses PyInstaller's ready-made bootloader instead.
REM Requires Python 3.14 installed for the current user (python.org installer, "Install for me only").
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)" || (
    echo Python 3.14 is needed - the release is built with 3.14 and the pinned packages are for it.
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
REM smoke test: the built exe makes a berthing chart (proves the berthing package and berth list are bundled)
python -c "import sys; sys.path.insert(0, 'tests'); import test_berthing as t; tr, dg = t.base_plan(); open('smoke/berth.xml', 'w').write(t.xml(tr, dg)); t.make_chart('smoke/berth_layout.xlsx')" || goto :failed
if exist smoke\berth.xlsx del smoke\berth.xlsx
start /wait "" dist\TrainPlanningTools.exe berthing --xml smoke\berth.xml --layout smoke\berth_layout.xlsx --out smoke --name berth
if not exist smoke\berth.xlsx (
    echo The built exe did not make a berthing chart.
    goto :failed
)
REM smoke test: Section 4 and TPR document comparisons, the Section 4 check, a station book with another operator merged in
python -c "import sys, os; sys.path.insert(0, 'tests'); import test_timetable as t; t.write_rule_docs(os.path.abspath('smoke')); t.write_s4_xml('smoke/s4plan.xml')" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_stationbook as t; t.write_late_xml('smoke/late.xml'); t.write_late_xml('smoke/other.xml', operator='XC')" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_timetable as t; t.write_vpt('smoke/v1.vpt', [t.vpt_1h05()]); t.write_vpt('smoke/v2.vpt', [t.vpt_1h05(HYWRDSH_plat='5')])" || goto :failed
for %%f in (s4cmp tprcmp s4check swb_merged vpt_cmp) do if exist smoke\%%f.xlsx del smoke\%%f.xlsx
if exist "smoke\s4_new - highlighted*.pdf" del "smoke\s4_new - highlighted*.pdf"
start /wait "" dist\TrainPlanningTools.exe timetable --s4 smoke\s4_old.pdf --vs-s4 smoke\s4_new.pdf --highlight-pdfs --out smoke --name s4cmp
start /wait "" dist\TrainPlanningTools.exe timetable --tpr smoke\tpr_old.pdf --vs-tpr smoke\tpr_new.pdf --out smoke --name tprcmp
start /wait "" dist\TrainPlanningTools.exe timetable --s4-check smoke\s4plan.xml --s4 smoke\s4_old.pdf --out smoke --name s4check
start /wait "" dist\TrainPlanningTools.exe stationbook --xml smoke\late.xml --station Alpha --merge-xml smoke\other.xml --out smoke --name swb_merged
start /wait "" dist\TrainPlanningTools.exe timetable --prints smoke\v1.vpt --vs smoke\v2.vpt --out smoke --name vpt_cmp
for %%f in (s4cmp tprcmp s4check swb_merged vpt_cmp) do if not exist smoke\%%f.xlsx (
    echo The built exe did not produce smoke\%%f.xlsx.
    goto :failed
)
if not exist "smoke\s4_new - highlighted.pdf" (
    echo The built exe did not produce the highlighted Section 4 PDFs.
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
