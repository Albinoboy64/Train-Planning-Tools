@echo off
REM Optional: build TrainPlanningTools.exe yourself on a Windows PC (no admin rights needed).
REM Mirrors the release build (.github\workflows\build-windows.yml): Python 3.14, the same pinned packages
REM (packaging\build-requirements.txt), lint, type-check, tests with coverage, build, smoke tests of the exe and the SBOM.
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
python -m pytest -q tests --cov --cov-report=term || goto :failed
python packaging\make_version_file.py version_info.txt || goto :failed
pyinstaller --noconfirm packaging\TrainPlanningTools.spec || goto :failed
REM smoke test: the built exe compares two small CWNs (as the release build does)
python -c "import sys, os; sys.path.insert(0, 'tests'); import test_compare as t; d = os.path.abspath('smoke'); os.makedirs(d, exist_ok=True); t.make(os.path.join(d, 'a.xlsx'), t.BTN_ORIG, t.VIC_ORIG); b, v = t._upd_rows(); t.make(os.path.join(d, 'b.xlsx'), b, v)" || goto :failed
if exist smoke\smoke.xlsx del smoke\smoke.xlsx
if exist "smoke\smoke - Change Report.xlsx" del "smoke\smoke - Change Report.xlsx"
call :run --original smoke\a.xlsx --updated smoke\b.xlsx --out smoke --name smoke || goto :failed
if not exist smoke\smoke.xlsx (
    echo The built exe did not produce its smoke-test output.
    goto :failed
)
REM smoke test: the built exe makes a berthing chart (proves the berthing package and berth list are bundled)
python -c "import sys; sys.path.insert(0, 'tests'); import test_berthing as t; tr, dg = t.base_plan(); open('smoke/berth.xml', 'w').write(t.xml(tr, dg)); t.make_chart('smoke/berth_layout.xlsx')" || goto :failed
if exist smoke\berth.xlsx del smoke\berth.xlsx
call :run berthing --xml smoke\berth.xml --layout smoke\berth_layout.xlsx --out smoke --name berth || goto :failed
if not exist smoke\berth.xlsx (
    echo The built exe did not make a berthing chart.
    goto :failed
)
REM smoke test: Section 4 and TPR document comparisons, the Section 4 check, a station book with another operator merged in
python -c "import sys, os; sys.path.insert(0, 'tests'); import test_timetable as t; t.write_rule_docs(os.path.abspath('smoke')); t.write_s4_xml('smoke/s4plan.xml')" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_stationbook as t; t.write_late_xml('smoke/late.xml'); t.write_late_xml('smoke/other.xml', operator='XC')" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_timetable as t; t.write_vpt('smoke/v1.vpt', [t.vpt_1h05()]); t.write_vpt('smoke/v2.vpt', [t.vpt_1h05(HYWRDSH_plat='5')])" || goto :failed
for %%f in (s4cmp tprcmp s4check s4check_vpt s4sub swb_merged vpt_cmp) do if exist smoke\%%f.xlsx del smoke\%%f.xlsx
if exist "smoke\s4_new - highlighted*.pdf" del "smoke\s4_new - highlighted*.pdf"
call :run timetable --s4 smoke\s4_old.pdf --vs-s4 smoke\s4_new.pdf --highlight-pdfs --out smoke --name s4cmp || goto :failed
call :run timetable --tpr smoke\tpr_old.pdf --vs-tpr smoke\tpr_new.pdf --out smoke --name tprcmp || goto :failed
call :run timetable --s4-check smoke\s4plan.xml --s4 smoke\s4_old.pdf --out smoke --name s4check || goto :failed
call :run timetable --s4-check smoke\s4plan.xml --s4 smoke\s4_old.pdf --vpt smoke\v1.vpt --other-vpt smoke\v2.vpt --out smoke --name s4check_vpt || goto :failed
call :run section4 --xml smoke\s4plan.xml --pdf smoke\s4_old.pdf --vpt smoke\v1.vpt --out smoke --name s4sub || goto :failed
call :run stationbook --xml smoke\late.xml --station Alpha --merge smoke\other.xml --out smoke --name swb_merged || goto :failed
call :run timetable --prints smoke\v1.vpt --vs smoke\v2.vpt --out smoke --name vpt_cmp || goto :failed
for %%f in (s4cmp tprcmp s4check s4check_vpt s4sub swb_merged vpt_cmp) do if not exist smoke\%%f.xlsx (
    echo The built exe did not produce smoke\%%f.xlsx.
    goto :failed
)
if not exist "smoke\s4_new - highlighted.pdf" (
    echo The built exe did not produce the highlighted Section 4 PDFs.
    goto :failed
)
REM smoke test: every other subcommand and major mode (the same list as the release build in
REM .github\workflows\build-windows.yml): stats packs, unit and capacity reports, station book, timetable and train print checks,
REM batch comparison, day variants in order, the berthing chart modes (and without notes), an SNGX station book with
REM an F3 print merged in, and the Section 4 check with an F3 print for another operator
python -c "import sys; sys.path.insert(0, 'tests'); import test_statspack as t; t.write_xml('smoke/sp.xml'); t.write_docx('smoke/sp.docx', t.plan_lines())" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_stationbook as t; t.write_xml('smoke/swb.xml')" || goto :failed
python -c "import sys, os; sys.path.insert(0, 'tests'); import test_timetable as t; t._books(os.path.abspath('smoke'))" || goto :failed
python -c "from rstools.docexport import Section as S, write_pdf, write_docx; h=['Location','Arr','Dep']; write_pdf('smoke/p1.pdf', 'P', [S('Train 1A00  UID C12340  SX', h, [['Brighton','','0500'],['London Bridge','0553','']])]); write_docx('smoke/p2.docx', 'P', [S('Train 1A00  UID C12340  SX', h, [['Brighton','','0502'],['London Bridge','0555','']])])" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_timetable as t; t.write_attune_pdf('smoke/attune.pdf'); t._gtr_from(t.ATTUNE[:1], 'smoke/tt_check.xlsx')" || goto :failed
python -c "import sys, os; sys.path.insert(0, 'tests'); import test_compare as t; [os.makedirs('smoke/' + d, exist_ok=True) for d in ('bo', 'bu', 'bout')]; b, v = t._upd_rows(); [t.make('smoke/bo/' + n + ' Proof 1.xlsx', t.BTN_ORIG, t.VIC_ORIG) or t.make('smoke/bu/' + n + ' Proof 2.xlsx', b, v) for n in ('BTN', 'VIC')]" || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_compare as t; t.make_multi_day('smoke/multi.xlsx')" || goto :failed
for %%f in (sp seats swb prints prints_pax print_tt reordered berth_default units_cmp units_week wk_berth lists base_list cumulative sp_mo packs cap_group cap_ft berth_round wk_xml berth_tlgn berth_places wk_others wk_berth_others berth_others berth_blank berth_blank_tlgn sp_tt sp_month sp_custom swb_sngx s4check_f3 berth_nonotes sp_cmp reordered_merged berth_blank_xml s4builtin reordered_time cmp_pdf) do if exist smoke\%%f.xlsx del smoke\%%f.xlsx
if exist "smoke\wk_cmp - Change Report.xlsx" del "smoke\wk_cmp - Change Report.xlsx"
if exist "smoke\cumulative - Change Report.xlsx" del "smoke\cumulative - Change Report.xlsx"
for %%f in (sp.pdf units.docx berth_cmp.xlsx) do if exist smoke\%%f del smoke\%%f
if exist "smoke\K_D26 Consolidated TT Comparison.xlsx" del "smoke\K_D26 Consolidated TT Comparison.xlsx"
if exist "smoke\berth_cmp - Change Report.xlsx" del "smoke\berth_cmp - Change Report.xlsx"
if exist smoke\bout\*.xlsx del smoke\bout\*.xlsx
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name sp || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name sp --format pdf || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name units --unit-reports washes,cets,depots,captive,fuel --unit-period days --format docx || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name seats --capacity-corridor "Brighton Main Line (East Croydon - Brighton)" --corridor-direction reverse --between 06:00-09:00 --at "East Croydon" --direction both || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --old-xml smoke\sp.xml --old-trent smoke\sp.docx --days MO,TO --out smoke --name units_cmp --unit-reports washes,depots || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name units_week --unit-reports washes,cets,fuel --possible over || goto :failed
call :run stationbook --xml smoke\swb.xml --station Alpha --out smoke --name swb || goto :failed
call :run timetable --gtr smoke\gtr.xlsx --nr smoke\nr.xlsx --out smoke || goto :failed
call :run timetable --prints smoke\p1.pdf --vs smoke\p2.docx --out smoke --name prints || goto :failed
call :run timetable --prints smoke\p1.pdf --vs smoke\p2.docx --passenger-only --out smoke --name prints_pax || goto :failed
call :run timetable --base-prints smoke\attune.pdf --check smoke\tt_check.xlsx --out smoke --name print_tt || goto :failed
call :run --original-folder smoke\bo --updated smoke\bu --out smoke\bout || goto :failed
call :run reorder smoke\multi.xlsx --out smoke --name reordered || goto :failed
call :run berthing --xml smoke\berth.xml --counts --issue Smoke --out smoke --name berth_default || goto :failed
call :run berthing --compare smoke\berth_layout.xlsx smoke\berth.xlsx --out smoke --name berth_cmp || goto :failed
call :run berthing --blank --leave-out Barnham --issue Smoke --out smoke --name berth_blank || goto :failed
call :run berthing --blank --operator TLGN --add Brighton --timetable "May 2027" --out smoke --name berth_blank_tlgn || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import workings_fixture as w; w.make_smoke('smoke')" || goto :failed
call :run workings-berthing --workings smoke\wk_a.xlsx --out smoke --name wk_berth || goto :failed
call :run --original smoke\wk_a.xlsx --updated smoke\wk_b.xlsx --out smoke --name wk_cmp || goto :failed
python -c "open('smoke/l1.csv','w').write('Headcode,UID,Days,Origin,Origin Dep,Destination,Class\n1A00,C10000,SX,Brighton,0600,Bedford,377\n1A01,C10001,SX,Brighton,0610,Bedford,377\n'); open('smoke/l2.csv','w',encoding='cp1252').write('Headcode,UID,Days,Origin,Origin Dep,Destination,Class\n1A00,C10000,SX,Brighton,0603,Bedford \u00a3,377\n')" || goto :failed
call :run timetable --lists smoke\l1.csv --vs smoke\l2.csv --out smoke --name lists || goto :failed
call :run timetable --base-list smoke\l1.csv --check smoke\tt_check.xlsx --out smoke --name base_list || goto :failed
call :run --previous smoke\smoke.xlsx --updated smoke\b.xlsx --out smoke --name cumulative || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO --out smoke --name sp_mo || goto :failed
call :run statspack --old-pack smoke\sp.xlsx --new-pack smoke\sp_mo.xlsx --out smoke --name packs || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --mileage-period timetable --out smoke --name sp_tt || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --mileage-period month --month 2027-01 --out smoke --name sp_month || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --mileage-period custom --period-from 14/12/2026 --period-to 20/12/2026 --out smoke --name sp_custom || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name cap_group --capacity-group 1A || goto :failed
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --days MO,TO --out smoke --name cap_ft --capacity-from Brighton --capacity-to "East Croydon" || goto :failed
call :run berthing --chart smoke\berth.xlsx --original smoke\berth.xml --updated smoke\berth.xml --out smoke --name berth_round || goto :failed
call :run workings-berthing --workings smoke\wk_a.xlsx --xml smoke\berth.xml --out smoke --name wk_xml || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import test_berthing as t; open('smoke/tlgn.xml', 'w').write(t.tlgn_xml())" || goto :failed
call :run berthing --xml smoke\tlgn.xml --operator TLGN --issue Final --out smoke --name berth_tlgn || goto :failed
call :run berthing --xml smoke\tlgn.xml --leave-out "Hove Yard" --add Bedford --out smoke --name berth_places || goto :failed
python -c "import sys; sys.path.insert(0, 'tests'); import others_fixture as f; f.southeastern_cif('smoke/se.cif')" || goto :failed
call :run other-trains --file smoke\wk_a.xlsx --others smoke\se.cif --out smoke --name wk_others || goto :failed
call :run workings-berthing --workings smoke\wk_a.xlsx --others smoke\se.cif --out smoke --name wk_berth_others || goto :failed
call :run berthing --xml smoke\berth.xml --others smoke\se.cif --out smoke --name berth_others || goto :failed
call :run stationbook --xml smoke\swb.xml --station Alpha --book-operator SNGX --merge smoke\attune.pdf --other-operators SN --out smoke --name swb_sngx || goto :failed
call :run timetable --s4-check smoke\s4plan.xml --s4 smoke\s4_old.pdf --other smoke\attune.pdf --out smoke --name s4check_f3 || goto :failed
call :run berthing --xml smoke\berth.xml --no-notes --out smoke --name berth_nonotes || goto :failed
REM smoke test (3.38.6): plan comparison, merged variants, blank chart from an XML, built-in Section 4 rules, PDF / Word
REM outputs, several station books at once (the frozen exe's helper processes), and a refused option combination
if exist smoke\s4pdf.pdf del smoke\s4pdf.pdf
if exist smoke\s4cmp_docx.docx del smoke\s4cmp_docx.docx
if exist smoke\books rmdir /s /q smoke\books
call :run statspack --xml smoke\sp.xml --trent smoke\sp.docx --old-xml smoke\sp.xml --old-trent smoke\sp.docx --days MO,TO --out smoke --name sp_cmp || goto :failed
call :run reorder smoke\multi.xlsx --merge --out smoke --name reordered_merged || goto :failed
call :run reorder smoke\multi.xlsx --by-time --out smoke --name reordered_time || goto :failed
call :run --original smoke\a.xlsx --updated smoke\b.xlsx --days MO,FO --report-format pdf --out smoke --name cmp_pdf || goto :failed
if not exist "smoke\cmp_pdf - Change Report.pdf" (
    echo The exe did not save a PDF change report.
    goto :failed
)
call :run berthing --blank --xml smoke\berth.xml --out smoke --name berth_blank_xml || goto :failed
call :run section4 --xml smoke\s4plan.xml --out smoke --name s4builtin || goto :failed
call :run section4 --xml smoke\s4plan.xml --pdf smoke\s4_old.pdf --format pdf --out smoke --name s4pdf || goto :failed
call :run timetable --s4 smoke\s4_old.pdf --vs-s4 smoke\s4_new.pdf --format docx --out smoke --name s4cmp_docx || goto :failed
mkdir smoke\books
call :run stationbook --xml smoke\swb.xml --station "Alpha; Beta; Gamma; Alpha [1-2]" --out smoke\books || goto :failed
python -c "import glob; raise SystemExit(0 if len(glob.glob('smoke/books/*.xlsx')) == 4 else 1)" || (
    echo The built exe did not make four station books at once.
    goto :failed
)
start /wait "" dist\TrainPlanningTools.exe --original smoke\a.xlsx --updated smoke\b.xlsx --acwn --highlight-only
if not errorlevel 1 (
    echo The built exe accepted --acwn with --highlight-only.
    goto :failed
)
for %%f in (sp seats swb prints prints_pax print_tt reordered berth_default units_cmp units_week wk_berth lists base_list cumulative sp_mo packs cap_group cap_ft berth_round wk_xml berth_tlgn berth_places wk_others wk_berth_others berth_others berth_blank berth_blank_tlgn sp_tt sp_month sp_custom swb_sngx s4check_f3 berth_nonotes sp_cmp reordered_merged berth_blank_xml s4builtin reordered_time cmp_pdf) do if not exist smoke\%%f.xlsx (
    echo The built exe did not produce smoke\%%f.xlsx.
    goto :failed
)
for %%f in (sp.pdf units.docx s4pdf.pdf s4cmp_docx.docx) do if not exist smoke\%%f (
    echo The built exe did not produce smoke\%%f.
    goto :failed
)
if not exist "smoke\K_D26 Consolidated TT Comparison.xlsx" (
    echo The built exe did not produce the timetable comparison.
    goto :failed
)
if not exist "smoke\berth_cmp - Change Report.xlsx" (
    echo The built exe did not compare two berthing charts.
    goto :failed
)
if not exist "smoke\wk_cmp - Change Report.xlsx" (
    echo The built exe did not compare two platform workings.
    goto :failed
)
python -c "import glob; n = [p for p in glob.glob('smoke/bout/*Proof*.xlsx') if 'Change Report' not in p]; raise SystemExit(0 if len(n) == 2 else 1)" || (
    echo The built exe batch comparison did not produce two CWNs.
    goto :failed
)
REM selftest: reads an Attune print with PDFium, finds the built-in Section 4 rules and berthing layout, opens a window with drag and drop
start /wait "" dist\TrainPlanningTools.exe selftest smoke\attune.pdf
if errorlevel 1 (
    echo The built exe could not read an Attune print, find its built-in rules or berthing layout, or open a window with drag and drop.
    goto :failed
)
REM the software bill of materials (as attached to releases), checked against the pinned runtime packages
python packaging\make_sbom.py dist\TrainPlanningTools.cdx.json || goto :failed
python packaging\check_sbom.py dist\TrainPlanningTools.cdx.json || goto :failed
echo.
echo Built: dist\TrainPlanningTools.exe (SBOM: dist\TrainPlanningTools.cdx.json)
pause
exit /b 0
:failed
echo.
echo The build stopped because a check failed (see above).
pause
exit /b 1

REM one run of the built exe: its exit code must be 0
:run
start /wait "" dist\TrainPlanningTools.exe %*
if errorlevel 1 (
    echo The built exe failed ^(exit code %errorlevel%^): %*
    exit /b 1
)
exit /b 0
