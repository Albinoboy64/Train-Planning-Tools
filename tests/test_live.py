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
