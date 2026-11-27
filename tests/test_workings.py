"""Platform workings (Victoria, London Bridge, Brighton books): reading, comparing, rounds, Live View and the
automatic berthing arrangements. Every file here is synthetic."""
import os
import sys

import openpyxl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import workings_fixture as wf  # noqa: E402
from cwn_compare import engine, model, workings_berthing as wb  # noqa: E402
from cwn_compare.options import Options  # noqa: E402


def read(path):
    return model.parse_workbook(openpyxl.load_workbook(path))


def section(path, tab="MO"):
    """{label: text} of a tab's Berthing Arrangements section."""
    ws = openpyxl.load_workbook(path)[tab + " "]
    out = {}
    for row in ws.iter_rows(values_only=True):
        cells = [str(v) for v in row if v not in (None, "")]
        if len(cells) == 2 and not cells[0].lower().endswith("arrangements:-") and cells[0] != "Berth":
            out[cells[0]] = cells[1]
    return out


@pytest.mark.parametrize("station,cols", [
    ("victoria", {"line", "in_line", "cars", "dep", "fp"}),
    ("london bridge", {"line", "in_line", "cars", "op", "dep", "fp"}),
    ("brighton", {"cars", "op", "dep", "fp"}),
])
def test_each_station_layout_is_read_by_its_headings(tmp_path, station, cols):
    m = read(wf.make(str(tmp_path / "w.xlsx"), station))
    assert set(m.sheets) == {"SO", "SUO", "MO", "TO", "WO", "THO", "FO"} and not m.warnings
    sm = m.sheets["MO"]
    assert cols <= set(sm.cols) and {"id", "time", "plat", "dest", "unit", "inwards", "in_id"} <= set(sm.cols)
    train = next(b for b in sm.blocks if b.base_id == "1l04")
    assert train.main["plat"] == "15" and [u.cars for u in train.units] == ["4", "4", "4"]
    assert any(b.is_berth for b in sm.blocks)                         # the berth lines are their own blocks


def test_a_cwn_heading_is_not_taken_for_workings():
    assert model.find_header([("ID", "DAYS", "TIME", "PL", "DESTINATION", "UNIT")])[1].keys() >= {"id", "time"}
    assert "cars" not in model.find_header([("ID", "DAYS", "TIME", "PL", "DESTINATION", "UNIT")])[1]


def test_the_berthing_section_is_read_apart_from_the_trains(tmp_path):
    foot = {"MO": [("Platform 14", "8 387 for 05 05 TO"), ("Platform 15", "EMPTY")]}
    m = read(wf.make(str(tmp_path / "w.xlsx"), "victoria", footer=foot))
    sm = m.sheets["MO"]
    assert [(e["label"], e["text"]) for e in sm.footer][1:] == foot["MO"]
    assert not any(b.base_id.startswith("platform") for b in sm.blocks)
    again = model.model_from_dict(model.model_to_dict(m))               # kept in a comparison CWN's stored data
    assert again.sheets["MO"].footer == sm.footer


def compare(tmp_path, station, edit, footer=None, **kw):
    old = wf.make(str(tmp_path / "old.xlsx"), station, footer=footer)
    new = wf.make(str(tmp_path / "new.xlsx"), station, edit=edit, footer=footer if not kw.get("new_footer")
                  else kw["new_footer"])
    opts = Options(original=old, updated=new, output_dir=str(tmp_path), output_name=kw.get("name", "cmp"),
                   colour=kw.get("colour", "FFFF00"), mode=kw.get("mode", "compare"))
    return engine.run(opts, log=lambda _m: None), opts


def changes(res):
    rows = list(openpyxl.load_workbook(res["report"])["All Changes"].iter_rows(values_only=True))[1:]
    return {(r[1], r[3]): (r[4], r[5]) for r in rows}


def test_workings_are_compared_with_lines_cars_operators_and_colours(tmp_path):
    def edit(tab, rows):
        if tab != "MO":
            return None
        for r in rows:
            if r.get("id") == "1W92":
                r["plat"], r["line"] = "13", "DBS"
            if r.get("id") == "1L04":
                r["time"] = "05.52"
            if r.get("id") == "9O25":
                r["op"] = "GTR"
        rows[3]["cars"] = "(5"                                         # a coupled unit of 1L04
    res, _ = compare(tmp_path, "london bridge", edit)
    got = changes(res)
    assert got[("1W92", "Platform")] == ("14", "13") and got[("1W92", "Line")] == ("DBF", "DBS")
    assert got[("1L04", "Time")] == ("05.50", "05.52")
    assert got[("9O25", "Operator")] == ("TLK", "GTR") and got[("1L04", "Number of cars")] == ("(4", "(5")
    out = openpyxl.load_workbook(res["cwn"], rich_text=True)
    ws = out["MO "]
    hit = next(c for row in ws.iter_rows() for c in row if "13" in str(c.value) and c.fill.fgColor.rgb == "FFFFFF00")
    assert hit is not None
    assert "yellow" in out["Cover "]["A5"].value.lower()


def test_berthing_section_changes_are_highlighted_and_reported(tmp_path):
    old = {"MO": [("Platform 14", "8 387 for 05 05 TO"), ("Platform 15", "EMPTY")]}
    new = {"MO": [("Platform 14", "8 387 for 05 06 TO"), ("Platform 15", "EMPTY")]}
    res, _ = compare(tmp_path, "victoria", lambda *_a: None, footer=old, new_footer=new)
    assert changes(res)[("Monday berthing: Platform 14", "Berthing arrangements")] == (
        "8 387 for 05 05 TO", "8 387 for 05 06 TO")
    ws = openpyxl.load_workbook(res["cwn"], rich_text=True)["MO "]
    cell = next(c for row in ws.iter_rows() for c in row if "05 06" in str(c.value))
    assert cell.fill.fgColor.rgb == "FFFFFF00" and "05 05" in str(cell.value)    # old text struck through above
    assert next(c for row in ws.iter_rows() for c in row if c.value == "EMPTY").fill.fill_type is None


def test_a_new_round_keeps_earlier_colours_and_berthing_lines(tmp_path):
    foot = lambda t: {"MO": [("Platform 14", t), ("Platform 15", "EMPTY")]}      # noqa: E731
    base = wf.make(str(tmp_path / "p1.xlsx"), "brighton", footer=foot("8 387 for 05 05 TO"))
    p2 = wf.make(str(tmp_path / "p2.xlsx"), "brighton", footer=foot("8 387 for 05 06 TO"))
    r1 = engine.run(Options(original=base, updated=p2, output_dir=str(tmp_path), output_name="r1"),
                    log=lambda _m: None)

    def edit(tab, rows):
        for r in rows if tab == "TO" else []:
            if r.get("id") == "1L04":
                r["time"] = "05.55"
    p3 = wf.make(str(tmp_path / "p3.xlsx"), "brighton", edit=edit, footer=foot("8 387 for 05 06 TO"))
    r2 = engine.run(Options(original=r1["cwn"], updated=p3, mode="cumulative", colour="92D050",
                            output_dir=str(tmp_path), output_name="r2"), log=lambda _m: None)
    assert r2["changes"] == 1 and r2["carried"] == 1
    wsm = openpyxl.load_workbook(r2["cwn"], rich_text=True)
    assert next(c for row in wsm["MO "].iter_rows() for c in row if "05 06" in str(c.value)).fill.fgColor.rgb \
        == "FFFFFF00"
    assert next(c for row in wsm["TO "].iter_rows() for c in row if "05.55" in str(c.value)).fill.fgColor.rgb \
        == "FF92D050"
    assert "yellow" in wsm["Cover "]["A5"].value.lower() and "green" in wsm["Cover "]["A5"].value.lower()


def test_acwn_keeps_the_berthing_section_of_a_changed_tab(tmp_path):
    foot = lambda t: {"MO": [("Platform 14", t)], "TO": [("Platform 14", "EMPTY")]}   # noqa: E731
    old = wf.make(str(tmp_path / "a.xlsx"), "victoria", footer=foot("8 387 for 05 05 TO"))
    new = wf.make(str(tmp_path / "b.xlsx"), "victoria", footer=foot("8 387 for 05 06 TO"))
    res = engine.run(Options(original=old, updated=new, output_type="acwn", output_dir=str(tmp_path),
                             output_name="acwn"), log=lambda _m: None)
    wbk = openpyxl.load_workbook(res["cwn"])
    assert "MO " in wbk.sheetnames and "TO " not in wbk.sheetnames
    assert "05 06 TO" in section(res["cwn"])["Platform 14"]


def test_day_filter_and_batch_names_follow_the_day_tabs(tmp_path):
    from cwn_compare import batch, days
    m = read(wf.make(str(tmp_path / "w.xlsx"), "victoria"))
    cover, guessed = days.coverage(m)
    assert cover == set(range(7)) and not guessed
    only = days.filter_model(m, {0}, cover)
    assert list(only.sheets) == ["MO"] and only.sheets["MO"].footer == m.sheets["MO"].footer
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for folder, n in ((a, 1), (b, 2)):
        for st in ("Victoria", "Brighton"):
            wf.make(str(folder / f"{st}_May_26_Final_Supp_{n}.xlsx"), st.lower())
    pairs, left_a, left_b = batch.pair_files(str(a), str(b))
    assert len(pairs) == 2 and not left_a and not left_b
    assert all(os.path.basename(o).split("_")[0] == os.path.basename(u).split("_")[0] for o, u in pairs)


def test_live_view_lists_trains_and_the_berthing_lines(tmp_path):
    from rstools.live import adapters
    foot = lambda t: {"MO": [("Platform 14", t)]}                                 # noqa: E731
    old = wf.make(str(tmp_path / "a.xlsx"), "victoria", footer=foot("8 387 for 05 05 TO"))

    def edit(tab, rows):
        for r in rows if tab == "MO" else []:
            if r.get("id") == "1W92":
                r["plat"] = "13"
    new = wf.make(str(tmp_path / "b.xlsx"), "victoria", edit=edit, footer=foot("8 387 for 05 06 TO"))
    res = adapters.cwn(old, new, None, lambda _m: None)
    from rstools.live.model import CHANGED
    train = next(i for i in res.items if i.label.startswith("1W92") and i.group.strip() == "MO")
    assert train.state == CHANGED and "Platform" in train.status
    foot_item = next(i for i in res.items if "Berthing Arrangements" in i.label and i.group.strip() == "MO")
    assert foot_item.state == CHANGED
    assert foot_item.rows[0].cells[0] == "Platform 14" and "05 06" in foot_item.rows[0].cells[2]


# --------------------------------------------------------------------------- berthing arrangements
def generate(tmp_path, station, tabs=None, xml=(), footer=None):
    src = wf.make(str(tmp_path / "w.xlsx"), station, footer=footer)
    notes = []
    res = wb.add_berthing(src, xml, str(tmp_path), "", notes.append)
    return src, res, notes


def test_platforms_are_added_up_and_checked_against_the_next_day(tmp_path):
    src, res, notes = generate(tmp_path, "victoria")
    got = section(res.chart, "MO")
    assert got["Platform 14"] == "8 387 for 05 05 TO"                  # two units of 4
    assert got["Platform 15"] == "12 377 for 05 50 TO"                 # 15 and 15F, three units
    assert got["Platform 16"] == "4 377 for RP 06 20 TO"               # leaves as the rear portion
    assert got["Platform 9"] == "EMPTY" and got["Platform 19"] == "EMPTY"
    assert section(res.chart, "SO")["Platform 14"] == "8 387 for 05 05 SUN"      # Victoria writes Sunday as SUN
    assert not [n for n in notes if "platform" in n.lower() and n.startswith("CHECK")]


def test_sidings_come_from_the_trains_that_take_the_units_out(tmp_path):
    src, res, notes = generate(tmp_path, "victoria")
    got = section(res.chart, "MO")
    assert got["NO 1 CARRIAGE SIDING"] == "8 377 for 05+28 TO" and got["NO 2 CARRIAGE SIDING"] == "EMPTY"
    assert got["BATTERSEA PIER NO 1 SIDING"] == "EMPTY"
    assert any("check the road" in n for n in notes)                    # no XML: the road is a guess
    assert section(res.chart, "SO")["NO 1 CARRIAGE SIDING"] == "8 377 for 05+28 SUN"


def test_the_road_comes_from_an_attune_xml(tmp_path):
    from test_berthing import diagram, train, xml
    trains = [train("5V74", "1", [("VICT", "23:30:00", "VICTCS", "23:50:00", "10", "S2")]),
              train("1C04", "2", [("VICTCS", "05:28:00", "VICT", "05:32:00", "S2", "19")])]
    diagrams = [diagram(1, "377/4", [("VICT", "23:30:00", "VICTCS", "23:50:00", "5V74", "1", [])], "BI60 05+28"),
                diagram(60, "377/4", [("VICTCS", "05:28:00", "VICT", "05:32:00", "1C04", "2", [])], "Stabld")]
    (tmp_path / "plan.xml").write_text(xml(trains, diagrams))
    src, res, notes = generate(tmp_path, "victoria", xml=[str(tmp_path / "plan.xml")])
    got = section(res.chart, "MO")
    assert got["NO 2 CARRIAGE SIDING"] == "8 377 for 05+28 TO" and got["NO 1 CARRIAGE SIDING"] == "EMPTY"


def test_each_stations_own_wording(tmp_path):
    _src, lb, _n = generate(tmp_path, "london bridge")
    assert section(lb.chart, "SO")["Platform 10"] == "8 700 TLK for 09 10 SuO"      # TLK shown, Sunday as SuO
    sub = tmp_path / "b"
    sub.mkdir()
    _src, br, _n = generate(sub, "brighton")
    assert section(br.chart, "MO")["Platform 10"] == "8 700 for 09 10 TO"             # Brighton does not say TLK
    assert {"Wall Sdg Rec", "Wall Sdg 2"} <= set(section(br.chart, "MO"))


def test_a_hand_made_section_is_replaced_and_the_differences_logged(tmp_path):
    foot = {"MO": [("Platform 14", "8 387 for 05 07 TO"), ("Platform 15", "12 377 for 05 50 TO"),
                   ("Platform 16", "4 377 for RP 06 20 TO")]}
    src, res, notes = generate(tmp_path, "victoria", footer=foot)
    assert any(n.startswith("DIFFERENT") and "Platform 14" in n and "05 07" in n for n in notes)
    assert not any("Platform 15" in n and n.startswith("DIFFERENT") for n in notes)
    assert "05 05" in section(res.chart, "MO")["Platform 14"]
    assert "05 07" in section(src, "MO")["Platform 14"]                  # the original is untouched


def test_a_unit_berthed_for_longer_is_added_from_the_next_tab(tmp_path):
    def edit(tab, rows):                          # Friday's tab forgets the berth lines of platform 16
        return [r for r in rows if not (tab == "FO" and str(r.get("dest", "")).startswith("Berth BI160"))]
    src = wf.make(str(tmp_path / "w.xlsx"), "victoria", edit=edit)
    notes = []
    res = wb.add_berthing(src, (), str(tmp_path), "", notes.append)
    assert section(res.chart, "FO")["Platform 16"] == "4 377 for RP 06 20 SO"
    assert any(n.startswith("NOTE") and "added from" in n for n in notes)


def test_output_names_never_overwrite_and_bad_input_is_explained(tmp_path):
    src = wf.make(str(tmp_path / "w.xlsx"), "victoria")
    one = wb.add_berthing(src, (), str(tmp_path))
    two = wb.add_berthing(src, (), str(tmp_path))
    assert one.chart != two.chart and os.path.isfile(one.chart) and os.path.isfile(two.chart)
    with pytest.raises(wb.WorkingsError, match="could not be found"):
        wb.add_berthing(str(tmp_path / "missing.xlsx"))
    other = tmp_path / "other.xlsx"
    openpyxl.Workbook().save(str(other))
    with pytest.raises(wb.WorkingsError, match="No platform workings day tabs"):
        wb.add_berthing(str(other), (), str(tmp_path))


def test_command_line(tmp_path, capsys):
    import TrainPlanningTools as cli
    src = wf.make(str(tmp_path / "w.xlsx"), "brighton")
    cli.main(["workings-berthing", "--workings", src, "--out", str(tmp_path), "--name", "done"])
    out = capsys.readouterr().out
    assert "Saved:" in out and os.path.isfile(tmp_path / "done.xlsx")
    with pytest.raises(SystemExit) as bad:
        cli.main(["workings-berthing", "--workings", str(tmp_path / "nope.xlsx")])
    assert bad.value.code == 2 and "could not be found" in capsys.readouterr().err
    other = tmp_path / "other.xlsx"
    openpyxl.Workbook().save(str(other))
    with pytest.raises(SystemExit) as bad:
        cli.main(["workings-berthing", "--workings", str(other), "--out", str(tmp_path)])
    assert bad.value.code == 1 and "ERROR:" in capsys.readouterr().out


def test_the_window_runs_the_berthing_task(tmp_path, monkeypatch):
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
        return                                          # no display
    try:
        assert ("work_berth", "Add berthing arrangements to platform workings") in gui.STOCK_TASKS
        src = wf.make(str(tmp_path / "w.xlsx"), "brighton")
        app.mode.set("work_berth")
        app._mode_changed()
        app.update()
        assert str(app.berth_counts_cb.winfo_manager()) == "" and app.run_btn.cget("text") == \
            "Add berthing arrangements"
        app.berth_vars["work_berth"][0].set(src)
        app.out_dir.set(str(tmp_path))
        app._run()
        end = time.time() + 60
        while time.time() < end and not shown:
            app.update()
            time.sleep(0.05)
        assert shown == ["info"], (shown, app.log.get("1.0", "end"), app.status.cget("text"))
        assert os.path.isfile(app.result["cwn"]) and "berthing added" in app.result["cwn"]
        assert section(app.result["cwn"], "MO")["Platform 5"] != "" and shown[0] in ("info", "warn")
    finally:
        app.destroy()


def test_a_longer_section_never_overwrites_what_follows_it(tmp_path):
    src = wf.make(str(tmp_path / "w.xlsx"), "victoria")                 # no section yet: one is added
    book = openpyxl.load_workbook(src)
    ws = book["MO "]
    last = max(r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value)
    ws.cell(row=last + 8, column=1, value="Signed: the planner")      # a note where the new section goes
    book.save(src)
    res = wb.add_berthing(src, (), str(tmp_path))
    out = openpyxl.load_workbook(res.chart)["MO "]
    assert any(out.cell(row=r, column=1).value == "Signed: the planner" for r in range(1, out.max_row + 1))
    assert "05 05" in section(res.chart, "MO")["Platform 14"]


def test_a_class_with_a_sub_class_still_finds_its_road(tmp_path):
    roads = {(0, 1, "377", (5 * 60 + 28) % 1440, 0): 1}
    lay = wb.LAYOUTS["victoria"]
    sid = lay.sidings[0]
    unit = wb.Unit(8, "377/4", "", "05+28", 1, 5 * 60 + 28, False, "train")
    got = dict(wb._assign_roads(0, sid, [unit], roads, lay, lambda _m: None))
    assert got[sid.roads[1][0]].startswith("8 377")
