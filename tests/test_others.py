"""Other operators' trains (Attune XML, VPT or Network Rail CIF) on berthing charts, platform workings and CWNs.
Every file here is synthetic."""
import os
import sys

import openpyxl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import others_fixture as F  # noqa: E402
import workings_fixture as wf  # noqa: E402
from rstools import others as O  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    return tmp_path


# ------------------------------------------------------------------ reading
def test_cif_reader_keeps_the_pattern_not_overlays_or_cancellations(home):
    from rstools.stationbook import read_plan
    from rstools.timetable.cif import is_cif
    path = F.southeastern_cif(str(home / "se.cif"))
    with open(path, "a", encoding="latin-1") as fh:        # a cancellation after the trailer is never read
        fh.write("BSNY9999926121327051511111000P" + " " * 49 + "C\n")
    assert is_cif(path) and not is_cif(str(home / "missing.cif"))
    plan = read_plan(path)                                  # the station book's reader takes a CIF too
    assert plan.operator == "SE" and plan.start == "2026-12-13" and plan.end == "2027-05-15"
    assert plan.locations["VICTRIC"] == "London Victoria"
    t = plan.trains["2T80"]
    assert len(t) == 1 and t[0].calls[-1].arr == 23 * 3600 + 50 * 60          # the overlay (23:55) is not kept
    assert t[0].days == {0, 1, 2, 3, 4} and t[0].calls[-1].plat == "3" and t[0].operator == "SE"
    assert plan.trains["5T99"][0].days == {5}


def test_trains_are_linked_by_place():
    from rstools.stationbook import Call, Plan, Train

    def tr(hc, days, frm, dep, to, arr, plat=""):
        return Train(hc, set(days), "L", [Call(frm, None, None, dep, None, plat, True, True),
                                          Call(to, arr, None, None, None, plat, True, True)])
    plan = Plan("x.cif", "", {}, {"2A01": [tr("2A01", range(5), "X", 80000, "STN", 84000, "2")],
                                  "1A02": [tr("1A02", range(5), "STN", 20000, "X", 23000, "2")],
                                  "2A03": [tr("2A03", range(5), "X", 60000, "STN", 61000, "1")],
                                  "2A04": [tr("2A04", range(5), "STN", 62000, "X", 64000, "1")]}, [], "", "XX")
    links = O.link(O.ends([plan], {"STN"}))
    nights = {(lk.arrive.headcode, lk.arrive.day): (lk.depart.headcode, lk.nights) for lk in links}
    assert nights[("2A01", 0)] == ("1A02", 1) and nights[("2A01", 4)] == ("1A02", 3)    # Friday to Monday
    assert nights[("2A03", 2)] == ("2A04", 0)                                           # a turnround
    assert O.day_code({0, 1, 2, 3, 4}, set(range(7))) == "MTWThFO" and O.day_code({6}, {5, 6}) == "SuO"
    assert O.day_code({1, 2, 3, 4}, set(range(5))) == "MX" and O.day_code(set(range(5)), set(range(5))) == ""


def test_a_vpt_is_read_as_other_operators_trains(home):
    from test_timetable import vpt_1h05, write_vpt
    path = str(home / "o.vpt")
    write_vpt(path, [vpt_1h05()])
    plan = O.load([path])[0]
    assert "1H05BS" in plan.trains and O.operator(plan) == "AA"


def test_bad_other_files_give_plain_messages(home):
    with pytest.raises(O.OthersError, match="could not be found"):
        O.load([str(home / "missing.xml")])
    (home / "junk.cif").write_text("HD" + "x" * 78 + "\nZZ\n")
    with pytest.raises(O.OthersError, match="no train schedules"):
        O.load([str(home / "junk.cif")])


# ------------------------------------------------------------------ berthing charts
def _brighton_cif(path):
    """SW's 1X50 arrives at Brighton platform 7 at 23:00 on weekdays and the unit forms 1X51 at 06:00."""
    return F.make_cif(path, [
        F.schedule("Z10001", "1X50", "1111100", "SW", [("HOVE", "", "2250", ""), ("BRGHTN", "2300", "", "7")]),
        F.schedule("Z10002", "1X51", "1111100", "SW", [("BRGHTN", "", "0600", "7"), ("HOVE", "0610", "", "")])])


def test_berthing_chart_shows_other_operators_by_headcode_in_grey(home):
    from test_berthing import base_plan, make_chart, row_of, train, xml
    from rstools.berthing import engine
    trains, diagrams = base_plan()
    (home / "p.xml").write_text(xml(trains, diagrams))
    make_chart(str(home / "chart.xlsx"))
    cif = _brighton_cif(str(home / "sw.cif"))
    bare = xml([train("2Y10", "1", [("HOVE", "23:10:00", "HOVEY36", "23:20:00", "", "S3")]),
                train("2Y11", "2", [("HOVEY36", "06:10:00", "HOVE", "06:20:00", "S3", "")])], [])
    (home / "xx.xml").write_text(bare.replace('plantype="L"', 'plantype="L" operator="XX"'))  # trains, no diagrams
    r = engine.generate([str(home / "p.xml")], str(home / "chart.xlsx"), str(home), "o",
                        others=[cif, str(home / "xx.xml")])
    wb = openpyxl.load_workbook(r.chart)
    ws = wb["Brighton"]
    p7 = row_of(ws, "Plat 7")
    row = next(rr for rr in range(p7, p7 + 4) if ws.cell(rr, 9).value == "1X50 2300")       # Monday finish
    assert ws.cell(row, 10).value == "1X51 0600" and ws.cell(row, 9).font.color.rgb == "FF7F7F7F"
    assert ws.cell(row, 4).value == "1X50 Berth"                                         # Saturday: still there
    hv = wb["Hove Yard"]
    assert any(hv.cell(rr, 9).value == "2Y10 2320" for rr in range(1, 8))
    assert any("Other operator SW" in w for w in r.warnings) and any("Other operator XX" in w for w in r.warnings)
    cover = [c.value for row in wb["Cover"].iter_rows() for c in row if isinstance(c.value, str)]
    assert any("Other operators' units are shown in grey" in t for t in cover)
    # a round of changes: the same other operators on both sides, so nothing of theirs is a change
    rnd = engine.add_round(r.chart, [str(home / "p.xml")], [str(home / "p.xml")], "92D050", str(home), "rnd",
                           others=[cif])
    assert rnd.summary.startswith("0 change")


def test_an_other_operator_xml_with_next_day_workings_uses_them(home):
    from test_berthing import base_plan, make_chart, row_of, xml
    from rstools.berthing import engine
    trains, diagrams = base_plan()
    (home / "p.xml").write_text(xml(trains, diagrams))
    make_chart(str(home / "chart.xlsx"))
    # the same plan again as another operator's: its units come with their unit types, in grey
    (home / "other.xml").write_text(xml(trains, diagrams).replace('plantype="L"', 'plantype="L" operator="ZZ"'))
    r = engine.generate([str(home / "p.xml")], str(home / "chart.xlsx"), str(home), "o",
                        others=[str(home / "other.xml")])
    ws = openpyxl.load_workbook(r.chart)["Brighton"]
    p1 = row_of(ws, "Plat 1")
    cells = [(ws.cell(rr, 9).value, ws.cell(rr, 9).font.color.rgb if ws.cell(rr, 9).font.color else None)
             for rr in range(p1, p1 + 3)]
    assert ("4 387 02+02", "FF7F7F7F") in cells and ("4 387 02+02", "FF00B050") in cells
    assert any("from their next-day workings" in w for w in r.warnings)


def test_a_tlgn_chart_keeps_other_operators_at_its_locations(home):
    from test_berthing import tlgn_xml
    from rstools.berthing import engine
    (home / "tl.xml").write_text(tlgn_xml())
    cif = F.make_cif(str(home / "em.cif"), [
        F.schedule("Z20001", "1E50", "1111100", "EM", [("STPX", "", "2200", ""), ("BEDFDM", "2300", "", "3")]),
        F.schedule("Z20002", "1E51", "1111100", "EM", [("BEDFDM", "", "0600", "3"), ("STPX", "0700", "", "")])])
    r = engine.generate([str(home / "tl.xml")], "", str(home), "tl", operator="TLGN", leave_out=["STPX"],
                        others=[cif])
    ws = openpyxl.load_workbook(r.chart)["Bedford"]
    texts = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert "1E50 2300" in texts and "8 700 23+59 TLK" in texts


# ------------------------------------------------------------------ CWNs and platform workings
def _cells(ws, rows):
    return [[(ws.cell(r, c).value, ws.cell(r, c).font.b, ws.cell(r, c).font.i) for c in range(1, 14)] for r in rows]


def test_other_operators_trains_are_added_to_platform_workings_without_changing_the_rest(home):
    from cwn_compare.model import parse_workbook
    from cwn_compare.other_trains import add_other_trains
    cif = F.southeastern_cif(str(home / "se.cif"))
    src = wf.make(str(home / "w.xlsx"), "victoria")
    before = openpyxl.load_workbook(src)["MO "]
    old_rows = [r for r in range(1, before.max_row + 1) if any(before.cell(r, c).value for c in range(1, 14))]
    r = add_other_trains(src, [cif], str(home))
    assert "(other operators added)" in r.chart and "SE" in r.summary
    ws = openpyxl.load_workbook(r.chart)["MO "]
    rows = {ws.cell(rr, 1).value: rr for rr in range(1, ws.max_row + 1) if ws.cell(rr, 1).value}
    t = rows["1T05"]
    assert [ws.cell(t, c).value for c in (2, 4, 5, 7, 9)] == ["05.40", "3", "Bromley South", "SE", "Berth"]
    assert ws.cell(t, 1).font.i and ws.cell(t, 1).font.color.rgb == "FF7F7F7F"
    assert rows["1W92"] < t < rows["1L04"]                                    # in time order
    t11 = rows["2T11"]
    assert [ws.cell(t11, c).value for c in (2, 8, 9, 12, 13)] == ["18.45", "18.00", "Bromley South", "18.30", "2T10"]
    berth = next(rr for rr in range(1, ws.max_row + 1) if ws.cell(rr, 13).value == "2T80")
    assert ws.cell(berth, 5).value == "Berth 1T05 05.40TO" and ws.cell(berth, 4).value == "3"
    # every original row is still there, unchanged, in the same order
    added = {rr for rr in range(1, ws.max_row + 1) if ws.cell(rr, 1).font.color is not None
             and ws.cell(rr, 1).font.color.rgb == "FF7F7F7F" and ws.cell(rr, 1).font.i}
    kept = [rr for rr in range(1, ws.max_row + 1) if rr not in added and any(ws.cell(rr, c).value
                                                                             for c in range(1, 14))]
    assert _cells(ws, kept) == _cells(before, old_rows)
    # the comparison reads it as workings with the new trains
    model = parse_workbook(openpyxl.load_workbook(r.chart))
    assert any(b.base_id.upper().startswith("1T05") for b in model.sheets["MO"].blocks)
    again = add_other_trains(r.chart, [cif], str(home), "again")
    assert again.summary.startswith("0 row")                                 # nothing added twice


def test_other_operators_trains_are_added_to_a_cwn_with_their_days(home):
    import test_compare as tc
    from cwn_compare.other_trains import add_other_trains
    cif = F.southeastern_cif(str(home / "se.cif"))
    tc.make(str(home / "c.xlsx"), tc.BTN_ORIG, tc.VIC_ORIG)
    wb = openpyxl.load_workbook(str(home / "c.xlsx"))
    wb["VIC"]["A1"] = "London Victoria"
    wb.save(str(home / "c.xlsx"))
    r = add_other_trains(str(home / "c.xlsx"), [cif], str(home), "cwn")
    ws = openpyxl.load_workbook(r.chart)["VIC"]
    rows = {ws.cell(rr, 1).value: rr for rr in range(1, ws.max_row + 1) if ws.cell(rr, 1).value}
    t = rows["1T05"]
    assert [ws.cell(t, c).value for c in (2, 3, 4, 6, 11, 15)] == ["MTWThFO", "05.40", "3", "SE", "Berth", "S"]
    assert rows["5T99"] and ws.cell(rows["5T99"], 2).value == "SO"
    assert any("BTN: its station could not be found" in w for w in r.warnings)
    btn = openpyxl.load_workbook(r.chart)["BTN"]
    assert btn.max_row == openpyxl.load_workbook(str(home / "c.xlsx"))["BTN"].max_row       # left as it was


def test_workings_berthing_arrangements_take_other_operators_units(home):
    from cwn_compare.workings_berthing import add_berthing
    from test_workings import section
    cif = F.southeastern_cif(str(home / "se.cif"))
    src = wf.make(str(home / "w.xlsx"), "victoria")
    plain = add_berthing(src, (), str(home), "plain")
    r = add_berthing(src, (), str(home), "others", others=[cif])
    assert section(r.chart, "MO")["Platform 3"] == "SE for 05 40 TO"
    assert section(r.chart, "FO")["Platform 3"] == "SE for 05 40 MO"                    # Friday night to Monday
    assert {k: v for k, v in section(r.chart, "MO").items() if k != "Platform 3" and k != "Platform 5"} == \
        {k: v for k, v in section(plain.chart, "MO").items()}
    a, b = openpyxl.load_workbook(src)["MO "], openpyxl.load_workbook(r.chart)["MO "]
    assert all(a.cell(rr, c).value == b.cell(rr, c).value for rr in range(1, 23) for c in range(1, 14))


def test_command_lines(home, capsys):
    import TrainPlanningTools as cli
    cif = F.southeastern_cif(str(home / "se.cif"))
    src = wf.make(str(home / "w.xlsx"), "victoria")
    cli.main(["other-trains", "--file", src, "--others", cif, "--out", str(home), "--name", "cli_ot"])
    assert os.path.isfile(str(home / "cli_ot.xlsx"))
    cli.main(["workings-berthing", "--workings", src, "--others", cif, "--out", str(home), "--name", "cli_wb"])
    assert os.path.isfile(str(home / "cli_wb.xlsx"))
    with pytest.raises(SystemExit):
        cli.main(["other-trains", "--file", src])                           # --others is needed
    with pytest.raises(SystemExit):
        cli.main(["berthing", "--compare", "a", "b", "--others", cif])


def test_a_station_book_merges_a_cif(home):
    import tempfile
    import test_stationbook as tsb
    from rstools import stationbook as SB
    d = tempfile.mkdtemp(dir=str(home))
    x = os.path.join(d, "plan.xml")
    tsb.write_late_xml(x)
    cif = F.make_cif(os.path.join(d, "xc.cif"), [
        F.schedule("Q10001", "9Z98", "1000000", "XC", [("AAA", "", "2330", "2"), ("BBB", "2350", "", "")])])
    path, warnings, _s = SB.make_book(x, "Alpha", d, operator="GTR(TLGN)", day_types=["MO"], merge_xml=[cif])
    rows = [str(r[1].value) for r in openpyxl.load_workbook(path).active.iter_rows(min_row=2)]
    assert any(v.startswith("9Z98") and v.endswith("[XC]") for v in rows)
    assert any("VPT or CIF" in w for w in warnings)


def _run_window(tmp_path, monkeypatch, mode, files, toggle=True):
    import time
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cwn_compare import gui
    shown = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *_a, **_k: shown.append("info"))
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *_a, **_k: shown.append("warn"))
    monkeypatch.setattr(gui.App, "open_outputs", lambda self, *_a, **_k: None)
    try:
        app = gui.App()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.mode.set(mode)
        app._mode_changed()
        for var, f in zip(app.berth_vars[mode], files):
            var.set(f)
        app.use_others.set(toggle)
        app.out_dir.set(str(tmp_path))
        app.update()
        app._run()
        end = time.time() + 60
        while time.time() < end and not shown:
            app.update()
            time.sleep(0.05)
        assert shown and shown[0] in ("info", "warn"), (shown, app.log.get("1.0", "end"))
        return app.result["cwn"], str(app.use_others_cb.winfo_manager())
    finally:
        app.destroy()


def test_the_window_adds_other_operators_trains(home, monkeypatch):
    from test_workings import section
    cif = F.southeastern_cif(str(home / "se.cif"))
    src = wf.make(str(home / "w.xlsx"), "victoria")
    out, manager = _run_window(home, monkeypatch, "add_others", [src, cif])
    assert "(other operators added)" in out and manager == ""            # no switch: the files are the task
    ws = openpyxl.load_workbook(out)["MO "]
    assert any(ws.cell(r, 1).value == "1T05" for r in range(1, ws.max_row + 1))
    on, manager = _run_window(home, monkeypatch, "work_berth", [src, "", cif])
    assert manager == "grid" and section(on, "MO")["Platform 3"] == "SE for 05 40 TO"
    off, _m = _run_window(home, monkeypatch, "work_berth", [src, "", cif], toggle=False)
    assert "Platform 3" not in section(off, "MO")                        # switched off: the file is left out
