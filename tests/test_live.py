"""Live View: every comparison laid out train by train, agreeing with the reports."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_live_cwn_matches_report_and_days():
    import test_compare as t
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    t.make(os.path.join(d, "a.xlsx"), t.BTN_ORIG, t.VIC_ORIG)
    b, v = t._upd_rows()
    t.make(os.path.join(d, "b.xlsx"), b, v)
    res = compute("cwn", {"a": [os.path.join(d, "a.xlsx")], "b": [os.path.join(d, "b.xlsx")]})
    by = {i.label: i for i in res.items}
    assert by["1A01BT"].state == "changed" and [r.cells for r in by["1A01BT"].rows if r.state == "changed"] == [
        ["Time", "05.23", "05.25"]]
    assert by["2C99BT"].state == "added" and by["2C08BT"].state == "removed"
    assert by["1G06BT"].state == "same"
    o = [list(r) for r in t.BTN_ORIG]
    o[2][1] = "FO"
    t.make(os.path.join(d, "c.xlsx"), o, t.VIC_ORIG)
    mon = compute("cwn", {"a": [os.path.join(d, "c.xlsx")], "b": [os.path.join(d, "c.xlsx")]}, days=[0])
    assert "2C02BT (FO)" not in {i.label for i in mon.items}           # the Friday train is left out


def test_live_cwn_highlights_extra_lines_as_the_comparison_judges_them():
    """Next-day working lines are compared as a set (order and units swapped between lines are not changes):
    Live View highlights only the line that really differs, never lines that merely moved."""
    import test_compare as t
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    old = [list(r) for r in t.BTN_ORIG] + t._berth_rows([("Berth BI150 06+10MO (2)", "146"),
                                                         ("Berth BI149 06+10MO (1)", "147")])
    moved = [list(r) for r in t.BTN_ORIG] + t._berth_rows([("Berth BI149 06+10MO (1)", "146"),
                                                           ("Berth BI150 06+10MO (2)", "147"),
                                                           ("Berth BI151 07+00MO (3)", "148")])
    t.make(os.path.join(d, "a.xlsx"), old, t.VIC_ORIG)
    t.make(os.path.join(d, "b.xlsx"), moved, t.VIC_ORIG)
    res = compute("cwn", {"a": [os.path.join(d, "a.xlsx")], "b": [os.path.join(d, "b.xlsx")]})
    berth = next(i for i in res.items if i.label.startswith("5H61BT"))
    nw = [r for r in berth.rows if r.cells[0].startswith("Next-day working")]
    assert len(nw) == 3
    assert [r.cells[0] for r in nw if r.state == "changed"] == ["Next-day working 3"], \
        [(r.cells, r.state) for r in nw]
    # only re-ordered (units swapped between the lines): nothing highlighted at all
    same = [list(r) for r in t.BTN_ORIG] + t._berth_rows([("Berth BI149 06+10MO (1)", "146"),
                                                          ("Berth BI150 06+10MO (2)", "147")])
    t.make(os.path.join(d, "c.xlsx"), same, t.VIC_ORIG)
    res = compute("cwn", {"a": [os.path.join(d, "a.xlsx")], "b": [os.path.join(d, "c.xlsx")]})
    berth = next(i for i in res.items if i.label.startswith("5H61BT"))
    assert not [r for r in berth.rows if r.cells[0].startswith("Next-day") and r.state == "changed"]


def test_live_comparison_cwn_without_stored_data_is_explained(monkeypatch):
    from cwn_compare import meta
    from rstools.live import adapters
    monkeypatch.setattr(meta, "is_comparison_output", lambda path: True)
    monkeypatch.setattr(meta, "read_meta_file", lambda path: {"changes": []})
    try:
        adapters.model_of("x.xlsx")
    except ValueError as exc:
        assert "Compare the original CWNs" in str(exc)
    else:
        raise AssertionError("expected a plain error")


def test_live_timetables_and_lists():
    import openpyxl
    import test_timetable as tt
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    g, n = tt._books(d)
    res = compute("timetables", {"a": [g], "b": [n]})
    by = {i.label.split()[0]: i for i in res.items}
    assert by["1A04"].state == "removed" and by["1A01"].state == "same"
    assert by["1A03"].state == "issue"
    assert [r.cells[4] for r in by["1A03"].rows if r.state not in ("same", "muted")] == ["Time mismatch"]
    assert by["1A03"].rows[0].cells[0] == "Days run"                       # the days at the top
    assert res.columns == ["Location", "Arr/Dep", "NR", "GTR", "Result"]
    for v in (1, 2):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Headcode", "UID", "Days", "Origin", "Origin Dep"])
        ws.append(["1A00", "C10000", "SX", "Brighton", "06:00" if v == 1 else "06:05"])
        ws.append(["1A01", "C10001", "SX", "Brighton", "07:00"])
        wb.save(os.path.join(d, f"l{v}.xlsx"))
    lr = compute("lists", {"a": [os.path.join(d, "l1.xlsx")], "b": [os.path.join(d, "l2.xlsx")]})
    assert sorted(i.state for i in lr.items) == ["changed", "same"]


def test_live_prints():
    import test_timetable as tt
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    p = os.path.join(d, "p.pdf")
    tt.write_attune_pdf(p)
    res = compute("prints", {"a": [p], "b": [p]})
    assert {i.state for i in res.items} == {"same"} and len(res.items) == 2       # no false differences


def test_live_export_all_formats():
    import openpyxl
    import test_timetable as tt
    from rstools.live.adapters import compute
    from rstools.live.export import export
    d = tempfile.mkdtemp()
    g, n = tt._books(d)
    res = compute("timetables", {"a": [g], "b": [n]})
    items = [i for i in res.items if i.state != "same"]
    for ext in ("xlsx", "pdf", "docx"):
        path = os.path.join(d, f"export.{ext}")
        export(path, res, items, "Differences only", "")
        assert os.path.getsize(path) > 1000
    wb = openpyxl.load_workbook(os.path.join(d, "export.xlsx"))
    assert wb.sheetnames == ["Comparison Details", "Trains Listed", "Differences in Detail"]
    assert wb["Trains Listed"].max_row == len(items) + 1


def test_live_parallel_reading():
    """Big files are read in helper processes: every Live View reader must work there (a reader defined
    inside a function cannot be sent to a helper - this once broke the CWN Live View)."""
    import test_compare as t
    import test_timetable as tt
    from rstools.live import adapters
    from rstools.timetable import engine
    readers = [adapters.model_of, engine.read_attune_print]
    import pickle
    for r in readers:
        pickle.dumps(r)                                   # module-level: can go to a helper process
    d = tempfile.mkdtemp()
    t.make(os.path.join(d, "a.xlsx"), t.BTN_ORIG, t.VIC_ORIG)
    b, v = t._upd_rows()
    t.make(os.path.join(d, "b.xlsx"), b, v)
    g, n = tt._books(d)
    old, engine.PARALLEL_BYTES = engine.PARALLEL_BYTES, 0          # force the parallel path
    engine._CACHE.clear()
    try:
        cwn = adapters.compute("cwn", {"a": [os.path.join(d, "a.xlsx")], "b": [os.path.join(d, "b.xlsx")]})
        ttr = adapters.compute("timetables", {"a": [g], "b": [n]})
    finally:
        engine.PARALLEL_BYTES = old
    assert any(i.state == "changed" for i in cwn.items) and len(ttr.items) > 0
    assert not engine._sendable(lambda p: p) and engine._sendable(adapters.model_of)


def test_view_toggles_ignore_source_only_and_pair_without_checking():
    from rstools.live.model import ADDED, CHANGED, PAIRED, REMOVED, SAME, LiveItem, LiveResult, LiveRow, view
    items = [LiveItem("1", "g", "1A01", SAME, "No change", [LiveRow(["x", "x"])]),
             LiveItem("2", "g", "1A02", CHANGED, "Time changed", [LiveRow(["0700", "0705"], CHANGED)], ["Time"]),
             LiveItem("3", "g", "1A03", REMOVED, "Missing", [LiveRow(["a", ""], REMOVED)]),
             LiveItem("4", "g", "1A04", ADDED, "Added", [LiveRow(["", "b"], ADDED)])]
    res = LiveResult("t", ["A", "B"], items)
    assert view(res) is res
    assert [i.label for i in view(res, ignore_source_only=True).items] == ["1A01", "1A02", "1A04"]
    paired = view(res, check=False)
    states = {i.label: i.state for i in paired.items}
    assert states == {"1A01": PAIRED, "1A02": PAIRED, "1A03": REMOVED, "1A04": ADDED}   # nothing lost
    changed = next(i for i in paired.items if i.label == "1A02")
    assert changed.notes == [] and all(r.state == SAME for r in changed.rows)
    assert [i.label for i in view(res, True, False).items] == ["1A01", "1A02", "1A04"]


def test_live_f3_prints_side_by_side():
    """Two Attune (F3) prints: laid out like the timetable comparison, with the train details on top and
    the prints' own details (platform, activity codes...) by each call; the report has the same layout."""
    import copy
    import openpyxl
    sys.path.insert(0, os.path.dirname(__file__))
    from test_timetable import ATTUNE, write_attune_pdf
    from rstools.live.adapters import compute
    from rstools.timetable.engine import run
    new = copy.deepcopy(ATTUNE)
    rows = new[0]["rows"]
    rows[2] = ("HYWRDSH", "Haywards Heath", "05a52½", "05p54½", "05.53", "05.54", "2:00", "T", "5")
    rows[3] = ("ECROYDN", "East Croydon", "06a18½", "06.20", "06.19", "06.20", "1:30", "TW", "1")
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.pdf"), os.path.join(d, "b.pdf")
        write_attune_pdf(a)
        write_attune_pdf(b, new)
        res = compute("prints", {"a": [a], "b": [b]})
        assert res.columns[:4] == ["Location", "Arr/Dep", "Original", "Updated"] and "Activity / details" in res.columns
        item = next(i for i in res.items if i.label.startswith("1H05"))
        assert item.state == "changed"
        top = [r.cells[0] for r in item.rows[:4]]
        assert top[:3] == ["Days run", "Train", "UID"] or top[:2] == ["Days run", "Train"]
        assert item.rows[0].cells[2:4] == ["SX", "SX"]
        hh = [r for r in item.rows if r.cells[0] == "Haywards Heath" or (r.cells[0] == "" and r.cells[1] == "Dep"
                                                                          and r.cells[2] == "05p53½")]
        assert hh[0].cells[5] == "4 → 5"                                    # platform on the location's first row
        dep = next(r for r in item.rows if r.cells[2] == "05p53½")
        assert dep.cells[3] == "05p54½" and dep.state == "changed" and "Time changed" in dep.cells[-1]
        ec = next(r for r in item.rows if r.cells[0] == "East Croydon")
        assert ec.cells[7] == "T → TW" and "Activity changed" in ec.cells[-1]
        out = run("prints", [a], [b], d, "f3", "xlsx").path
        ws = openpyxl.load_workbook(out)["Side by Side"]
        cells = [[c for c in r] for r in ws.iter_rows(min_row=2, values_only=True)]
        assert cells[0][0].startswith("1H05BS SX")                           # the train's own heading row
        assert any(r[0] == "Haywards Heath" and r[5] == "4 → 5" for r in cells)


def test_live_cwn_without_location_tabs_names_the_file():
    import openpyxl
    import test_compare as t
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    t.make(os.path.join(d, "a.xlsx"), t.BTN_ORIG, t.VIC_ORIG)
    wb = openpyxl.Workbook()
    wb.active["A1"] = "not a CWN"
    wb.save(os.path.join(d, "cover only.xlsx"))
    try:
        compute("cwn", {"a": [os.path.join(d, "a.xlsx")], "b": [os.path.join(d, "cover only.xlsx")]})
    except ValueError as exc:
        assert "updated CWN, cover only.xlsx" in str(exc)
    else:
        raise AssertionError("a CWN without location tabs was accepted")


def test_live_passenger_times_only():
    """'Passenger times only': passing times (and calls without a public time) leave the prints view and report, so
    a print that does not show the timing points is not flagged; times shown in one timetable only are hidden."""
    import copy
    import openpyxl
    from test_timetable import ATTUNE, _books, write_attune_pdf
    from rstools.live.adapters import compute
    from rstools.timetable.engine import run
    new = copy.deepcopy(ATTUNE)
    new[0]["rows"] = [r for r in new[0]["rows"] if r[0] != "KEYMERJ"]          # no timing point on this print
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.pdf"), os.path.join(d, "b.pdf")
        write_attune_pdf(a)
        write_attune_pdf(b, new)
        full = compute("prints", {"a": [a], "b": [b]})
        pax = compute("prints", {"a": [a], "b": [b]}, passenger_only=True)
        assert next(i for i in full.items if i.label.startswith("1H05")).state == "changed"
        item = next(i for i in pax.items if i.label.startswith("1H05"))
        assert item.state == "same" and not any(r.cells[1] == "Pass" for r in item.rows)
        out = run("prints", [a], [b], d, "pax", "xlsx", passenger_only=True).path
        wb = openpyxl.load_workbook(out)
        assert wb["Summary"]["B5"].value == 0                              # no paired train with changes
        assert "Passenger times only" in wb["Notes"]["A2"].value
        g, n = _books(d)
        tt = compute("timetables", {"a": [g], "b": [n]}, passenger_only=True)
        assert not any("not compared" in r.cells[-1] for i in tt.items for r in i.rows)


def test_live_new_modes():
    """Section 4 and TPR documents, the Section 4 check, berthing charts and unit reports in the Live View, using
    the same engines as their tabs."""
    import test_timetable as tt
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    f = tt.write_rule_docs(d)
    s4 = compute("s4docs", {"a": [f["s4_old"]], "b": [f["s4_new"]]})
    by = {i.label: i for i in s4.items}
    assert by["100.1 MID WEEK"].state == "changed" and by["100.3 SUN/MON"].state == "added"
    assert by["100.2 WEEK END"].state == "removed"
    assert [r.cells[0] for r in by["100.1 MID WEEK"].rows if r.state == "changed"] == ["Windows"]
    tpr = compute("tprs", {"a": [f["tpr_old"]], "b": [f["tpr_new"]]})
    assert {i.label: i.state for i in tpr.items if i.state != "same"}.get("Beta Jn") == "changed"
    x = os.path.join(d, "plan.xml")
    with open(x, "w", encoding="utf-8") as fh:
        fh.write('<diagramExchange xmlns="http://www.tracsis.com/TTVP_Interface" version="1.0" plantype="L" '
                 'startdate="2026-12-13" enddate="2027-05-15"><trainList>'
                 '<train id="1A01XX" daysRun="NNNYYYYNN" planType="L"><leg origin="AAA" dep="02:00:00" dest="BBB" '
                 'arr="02:10:00"/></train></trainList><locationList><location tiploc="AAA" longDesc="Alpha"/>'
                 '<location tiploc="BBB" longDesc="Beta Jn"/></locationList></diagramExchange>')
    chk = compute("s4check", {"xa": [x], "a": [f["s4_old"]]})
    assert any(i.group == "Clashes" and i.label.startswith("1A01XX") for i in chk.items), [i.label for i in chk.items]


def test_live_berthing_and_units(tmp_path, monkeypatch):
    import openpyxl
    import test_berthing as tb
    import test_statspack as ts
    from rstools.live.adapters import compute
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    old, new = str(tmp_path / "old.xlsx"), str(tmp_path / "new.xlsx")
    tb.make_chart(old)
    tb.make_chart(new)
    wb = openpyxl.load_workbook(new)
    wb["Brighton"]["D2"] = "4 387 0510"
    wb.save(new)
    res = compute("berthing", {"a": [old], "b": [new]})
    assert len(res.items) == 1 and res.items[0].group == "Brighton" and res.items[0].state in ("changed", "added")
    lines = (ts.diagram("SX", 7, "MO", "700/0", [ts.move("BRGHTN", "", "1", "", "07.00", "1B03SX", "7(1)", 30.0, 30.0),
                                                  ts.act("EBOUSID", "4", "08+00", "WASH")], 30.0, 0.0)
             + ts.diagram("SX", 8, "TO", "700/0", [ts.move("EBOUSID", "", "1", "", "07+00", "5B04SX", "8(1)", 30.0,
                                                           30.0), ts.act("BRGHTN", "4", "08+00", "STABLD")], 0.0, 30.0))
    a, b = str(tmp_path / "a.docx"), str(tmp_path / "b.docx")
    ts.write_docx(a, lines)
    ts.write_docx(b, [ln.replace("WASH", "CET") for ln in lines])
    units = compute("units", {"ta": [a], "tb": [b]})
    assert any(i.state == "changed" for i in units.items), [(i.group, i.label, i.state) for i in units.items]


def test_live_progress_confirmations(tmp_path, monkeypatch):
    """Confirmations are kept against each train's fingerprint: saved and loaded, and a train that changes after it
    was confirmed loses its tick."""
    from rstools.live import progress as P
    from rstools.live.export import export
    from rstools.live.model import LiveItem, LiveResult, LiveRow
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    a = LiveItem("k1", "G", "1A01", "same", "No change", [LiveRow(["Time", "0500", "0500"])])
    b = LiveItem("k2", "G", "1A02", "changed", "Time changed", [LiveRow(["Time", "0600", "0610"], "changed")])
    files = {"a": [str(tmp_path / "x.xlsx")], "b": [str(tmp_path / "y.xlsx")]}
    confirmed = {"k1": P.fingerprint(a), "k2": P.fingerprint(b)}
    path = P.autosave_path("cwn", files)
    assert P.save(path, "cwn", files, confirmed, {"check": True})
    back = P.load_auto("cwn", files)
    assert back is not None and back["confirmed"] == confirmed and back["mode"] == "cwn"
    b2 = LiveItem("k2", "G", "1A02", "changed", "Time changed", [LiveRow(["Time", "0600", "0615"], "changed")])
    kept, changed = P.reconcile(confirmed, [a, b2])
    assert kept == {"k1": confirmed["k1"]} and changed == {"k2"}
    assert P.comparison_id("cwn", files) != P.comparison_id("prints", files)
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    try:
        P.load(str(bad))
    except ValueError as exc:
        assert "not a Live View progress file" in str(exc)
    else:
        raise AssertionError("an unrelated file was loaded")
    out = str(tmp_path / "e.xlsx")
    export(out, LiveResult("t", ["Field", "Original", "Updated"], [a, b]), [a, b], "All", "", {"k1"})
    import openpyxl
    ws = openpyxl.load_workbook(out)["Trains Listed"]
    assert [ws.cell(r, 6).value for r in (2, 3)] == ["Yes", None]


def test_live_cwn_ignores_spacing_like_the_report():
    """Live CWN compares free text ignoring spacing, as Stock Tools does by default, and shows a changed
    Start/Call/Pass value as a row."""
    import test_compare as t
    from rstools.live.adapters import compute
    d = tempfile.mkdtemp()
    t.make(os.path.join(d, "a.xlsx"), t.BTN_ORIG, t.VIC_ORIG)
    rows = [list(r) for r in t.BTN_ORIG]
    rows[0][4] = "Victoria "                                  # trailing space only
    rows[2][14] = "P"
    t.make(os.path.join(d, "b.xlsx"), rows, t.VIC_ORIG)
    res = compute("cwn", {"a": [os.path.join(d, "a.xlsx")], "b": [os.path.join(d, "b.xlsx")]})
    by = {i.label: i for i in res.items}
    assert by["1A01BT"].state == "same"
    assert any(r.state == "changed" and r.cells[1:] == ["S", "P"] for r in by["2C02BT"].rows), by["2C02BT"].rows
