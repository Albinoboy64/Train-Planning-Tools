"""Station Working Book (TRACS-RS layout) from an Attune XML."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rstools import stationbook as SB  # noqa: E402

NS = 'xmlns="http://www.tracsis.com/TTVP_Interface"'
WEEK = "NNYYYYYNN"


def leg(o, dep, d, arr, **kw):
    extra = "".join(f' {k}="{v}"' for k, v in kw.items())
    return f'<leg origin="{o}" dep="{dep}" dest="{d}" arr="{arr}"{extra}/>'


def train(tid, legs, days=WEEK):
    return f'<train id="{tid}" daysRun="{days}" planType="L">' + "".join(legs) + "</train>"


def move(tid, o, dep, d, arr, coupled=()):
    cp = "".join(f'<coupled position="{i + 1}"><diagram id="{n}"/><depot id="XX"/></coupled>'
                 for i, n in enumerate(coupled))
    return (f'<diagMovement><journey origin="{o}" dep="{dep}" dest="{d}" arr="{arr}">'
            f'<activity trainid="{tid}"/>{cp}</journey></diagMovement>')


def diagram(num, fleet, moves, days=WEEK):
    return (f'<unitDiagram id="{num}" daysrun="{days}"><depot id="XX"/><res id="{fleet}"/><details>'
            + "".join(moves) + "</details></unitDiagram>")


def write_xml(path):
    trains = [
        train("5A01XX", [leg("DEP", "05:00:00", "AAA", "05:10:00", arrPlat="1")]),
        train("1A02XX", [leg("AAA", "05:30:00", "BBB", "05:40:00", depPlat="1"),
                         leg("BBB", "05:42:00", "CCC", "05:50:00")]),
        train("2B03XX", [leg("BBB", "05:45:00", "DDD", "06:00:00")]),
        train("1C04XX", [leg("CCC", "06:00:00", "AAA", "06:20:00", arrPlat="2"),
                         leg("AAA", "06:21:00", "BBB", "06:40:00", depPlat="2", depPub="06:21:00")]),
        train("2E05XX", [leg("AAA", "07:00:00", "BBB", "07:20:00", depPlat="3")], days="NNYNNNYNN"),
        train("1F06XX", [leg("AAA", "08:00:00", "DEP", "08:05:00", depPlat="1", arrStopType="P"),
                         leg("DEP", "08:05:00", "BBB", "08:30:00")]),
    ]
    diagrams = [
        diagram("1", "377/4", [move("5A01XX", "DEP", "05:00:00", "AAA", "05:10:00", ("1", "2")),
                               move("1A02XX", "AAA", "05:30:00", "BBB", "05:40:00", ("1", "2")),
                               move("1A02XX", "BBB", "05:42:00", "CCC", "05:50:00")]),
        diagram("2", "377/4", [move("5A01XX", "DEP", "05:00:00", "AAA", "05:10:00", ("1", "2")),
                               move("1A02XX", "AAA", "05:30:00", "BBB", "05:40:00", ("1", "2")),
                               move("2B03XX", "BBB", "05:45:00", "DDD", "06:00:00")]),
        diagram("3", "171/8", [move("1C04XX", "CCC", "06:00:00", "BBB", "06:40:00")]),
        diagram("4", "377/3", [move("2E05XX", "AAA", "07:00:00", "BBB", "07:20:00")]),
    ]
    locs = (("AAA", "Alpha"), ("BBB", "Beta"), ("CCC", "Gamma"), ("DDD", "DELTA TOWN"), ("DEP", "Alpha Depot"))
    xml = (f'<diagramExchange {NS} version="1.0" plantype="L" startdate="2023-12-10"><trainList>' + "".join(trains)
           + "</trainList><locationList>" + "".join(f'<location tiploc="{t}" longDesc="{n}"/>' for t, n in locs)
           + "</locationList><unitDiagramList>" + "".join(diagrams) + "</unitDiagramList></diagramExchange>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)


def test_station_working_book_rows():
    d = tempfile.mkdtemp()
    x = os.path.join(d, "plan.xml")
    write_xml(x)
    plan = SB.read_plan(x)
    b = SB.Builder(plan, {"AAA"}, "Alpha", cars={"377/4": 4, "377/3": 4, "171/8": 3})
    rows = {r.cells[1].split("\n")[0]: r.cells for r in b.build(0)}            # Monday
    nb = SB.NBSP
    # formed from the empty train, two units front first, dividing at Beta
    a, bb, c, dd, e, f, g = rows["1A02XX"]
    assert a == "5A01XX    05+00\nAlpha Depot\n05+10"
    assert bb == "1A02XX\n(377/4)\n(377/4)" and c == "05 30" and dd == "Alpha" and e == "Gamma" and f == "05 30\n(1)"
    assert g == (f"Beta{nb}(0540) The train divides at Beta\nThe front 4 coaches call at: GAMMA{nb}(0550)\n"
                 f"The rear 4 coaches call at: DELTA{nb}TOWN{nb}(0600)")
    # a through train: its own origin and arrival here; calling points after here
    assert rows["1C04XX"][:6] == ["1C04XX    06 00\nGamma\n06 20", "1C04XX\n(171/8)", "06 00", "Gamma", "Beta",
                                  "06 21\n(2)"]
    assert rows["1C04XX"][6] == f"BETA{nb}(0640)"
    # a unit that starts the day in the platform
    assert rows["2E05XX"][0] == "Berth"
    # passes a location (not shown as a stop)
    assert rows["1F06XX"][6] == f"BETA{nb}(0830)"
    # sorted by departure
    assert [r.cells[1].split("\n")[0] for r in b.build(0)] == ["1A02XX", "1C04XX", "2E05XX", "1F06XX"]


def test_station_working_book_file_and_day_notes(monkeypatch):
    import openpyxl
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", d)
    x = os.path.join(d, "plan.xml")
    write_xml(x)
    path, warnings, summary = SB.make_book(x, "Alpha", d, operator="GTR(TLGN)", services="Test services only",
                                           day_types=["SX", "Su"])
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Alpha (TLGN) SX", "Alpha (TLGN) Su"]
    ws = wb["Alpha (TLGN) SX"]
    assert [c.value for c in ws[1]][:6] == SB.HEADINGS[:6]
    assert ws.oddHeader.center.text == "GTR(TLGN) Dec23 Station Working Book - Alpha (Test services only)"
    assert ws.oddFooter.right.text == "&P/&N" and ws.print_title_rows == "$1:$1"
    assert ws["A1"].fill.fgColor.rgb == "FF99CCFF" and ws["A2"].font.i and ws["G2"].alignment.horizontal == "left"
    note = next(r[6].value for r in ws.iter_rows(min_row=2) if str(r[1].value).startswith("2E05XX"))
    assert note == f"BETA{SB.NBSP}(0720)\nRuns Monday and Friday only"   # 2E05XX runs MO and FO only
    assert ws.row_dimensions[2].height == 3 * SB.LINE_HEIGHT
    assert os.path.basename(path) == "GTR(TLGN) Dec23 Station Working Book - Alpha.xlsx"
    assert summary.endswith("for Alpha.") and not warnings          # diagrams for every day it runs


def test_day_phrases_and_platforms():
    assert SB.days_phrase([0]) == "Monday only"
    assert SB.days_phrase([0, 4]) == "Monday and Friday only"
    assert SB.days_phrase([1, 2, 3]) == "Tuesday to Thursday only"
    assert SB.days_phrase([0, 2, 4]) == "Monday, Wednesday and Friday only"
    assert SB.parse_platforms("10-15") == {str(n) for n in range(10, 16)}
    assert SB.parse_platforms("1, 2,4a") == {"1", "2", "4A"} and SB.parse_platforms("") is None


def test_several_station_books_in_one_run(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", d)
    x = os.path.join(d, "plan.xml")
    write_xml(x)
    assert SB.parse_station_list("Alpha; Beta [1-3]\nGamma; ") == [("Alpha", ""), ("Beta", "1-3"), ("Gamma", "")]
    results = SB.make_books(x, [("Alpha", ""), ("Alpha", "3"), ("Nowhere", "")], d, operator="GTR(TLGN)")
    assert [r[0] for r in results] == ["Alpha", "Alpha", "Nowhere"]
    assert results[0][1] and results[1][1] and results[0][1] != results[1][1]     # same station, two books
    assert not results[2][1] and "not a location" in results[2][4]               # the rest are still made


def test_stp_unit_diagram_replaces_ltp():
    """An XML holding the LTP and STP versions of a unit diagram for the same day uses the STP one only (a unit
    is not counted twice)."""
    d = tempfile.mkdtemp()
    x = os.path.join(d, "plan.xml")
    t = train("1A02XX", [leg("AAA", "05:30:00", "BBB", "05:40:00", depPlat="1")])
    ltp = diagram("1", "377/4", [move("1A02XX", "AAA", "05:30:00", "BBB", "05:40:00")]).replace(
        "<unitDiagram ", '<unitDiagram type="L" ')
    stp = ltp.replace('type="L"', 'type="S"')
    with open(x, "w", encoding="utf-8") as fh:
        fh.write(f'<diagramExchange {NS} version="1.0" plantype="S" startdate="2026-12-13"><trainList>{t}'
                 '</trainList><locationList><location tiploc="AAA" longDesc="Alpha"/>'
                 '<location tiploc="BBB" longDesc="Beta"/></locationList>'
                 f'<unitDiagramList>{ltp}{stp}</unitDiagramList></diagramExchange>')
    plan = SB.read_plan(x)
    assert len(SB.day_diagrams(plan.diagrams, 0)) == 1 and SB.day_diagrams(plan.diagrams, 0)[0].plan == "S"
    b = SB.Builder(plan, {"AAA"}, "Alpha", cars={"377/4": 4})
    (row,) = b.build(0)
    assert row.cells[1] == "1A02XX\n(377/4)"                          # one unit, not two


def write_late_xml(path, start="2026-12-13", operator="", tid_prefix="", depot_key="1"):
    """Monday's diagram ends with a train at 00:30 (calendar Tuesday); Tuesday's own diagram starts at 06:00."""
    trains = [train(f"{tid_prefix}2A10XX", [leg("AAA", "23:00:00", "BBB", "23:20:00", depPlat="1")], days="NNYNNNNNN"),
              train(f"{tid_prefix}2A11XX", [leg("AAA", "00:30:00", "BBB", "00:50:00", depPlat="1")], days="NNNYNNNNN"),
              train(f"{tid_prefix}2A12XX", [leg("AAA", "06:00:00", "BBB", "06:20:00", depPlat="1")], days="NNNYNNNNN")]
    diagrams = [diagram(depot_key, "377/4", [move(f"{tid_prefix}2A10XX", "AAA", "23:00:00", "BBB", "23:20:00"),
                                             move(f"{tid_prefix}2A11XX", "AAA", "00:30:00", "BBB", "00:50:00")],
                        days="NNYNNNNNN"),
                diagram(str(int(depot_key) + 1), "377/4",
                        [move(f"{tid_prefix}2A12XX", "AAA", "06:00:00", "BBB", "06:20:00")], days="NNNYNNNNN")]
    op = f' toc="{operator}"' if operator else ""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f'<diagramExchange {NS} version="1.0" plantype="L" startdate="{start}" enddate="2027-05-15"{op}>'
                 "<trainList>" + "".join(trains) + "</trainList><locationList><location tiploc=\"AAA\" "
                 'longDesc="Alpha"/><location tiploc="BBB" longDesc="Beta"/></locationList><unitDiagramList>'
                 + "".join(diagrams) + "</unitDiagramList></diagramExchange>")


def test_stock_day_starts_with_the_diagrams_first_train():
    """A train after midnight on Monday's diagram ends Monday's stock day; Tuesday starts with its first diagram's
    train, not the 00:30."""
    d = tempfile.mkdtemp()
    x = os.path.join(d, "late.xml")
    write_late_xml(x)
    b = SB.Builder(SB.read_plan(x), {"AAA"}, "Alpha", cars={"377/4": 4})
    assert [r.cells[1].split("\n")[0] for r in b.build(0)] == ["2A10XX", "2A11XX"]
    assert [r.cells[1].split("\n")[0] for r in b.build(1)] == ["2A12XX"]


def test_other_operator_xml_merged(monkeypatch):
    import openpyxl
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", d)
    x, other = os.path.join(d, "plan.xml"), os.path.join(d, "other.xml")
    write_late_xml(x)
    write_late_xml(other, operator="XC", tid_prefix="", depot_key="5")      # same train IDs: renamed
    merged = SB.merge_plans(SB.read_plan(x), [SB.read_plan(other)])
    assert "2A10XX/XC" in merged.trains and merged.trains["2A10XX/XC"][0].operator == "XC"
    b = SB.Builder(merged, {"AAA"}, "Alpha", cars={"377/4": 4})
    cells = {r.cells[1].split("\n")[0]: r.cells[1] for r in b.build(0)}
    assert set(cells) == {"2A10XX", "2A11XX", "2A10XX/XC", "2A11XX/XC"} and cells["2A10XX/XC"].endswith("[XC]")
    path, _w, _s = SB.make_book(x, "Alpha", d, operator="GTR(TLGN)", day_types=["MO"], merge_xml=[other])
    rows = [r[1].value for r in openpyxl.load_workbook(path).active.iter_rows(min_row=2)]
    assert any(str(v).endswith("[XC]") for v in rows)
    late = os.path.join(d, "late.xml")
    write_late_xml(late, start="2028-01-01")
    try:
        SB.merge_plans(SB.read_plan(x), [SB.Plan(late, "2028-01-01", {}, {}, [], "2028-05-01")])
    except SB.StationBookError as exc:
        assert "does not overlap" in str(exc)
    else:
        raise AssertionError("dates that do not overlap were merged")


def test_station_names_network_rail_and_attune():
    """Network Rail's station names match Attune's."""
    from rstools.statspack.seats import Stations
    st = Stations({"VICTRIC": "London Victoria (C)", "VICTRIE": "London Victoria", "STLNRWS": "St. Leonards Warrior Sq",
                   "LBGHJN": "Loughborough Jn", "KNGX": "London Kings Cross", "KENOLYM": "Kensington (Olympia)"})
    assert st.find("London Victoria (Central)") == {"VICTRIC"} and st.find("London Victoria (Eastern)") == {"VICTRIE"}
    assert st.find("St Leonards Warrior Square") == {"STLNRWS"} and st.find("Loughborough Junction") == {"LBGHJN"}
    assert st.find("London King’s Cross") == {"KNGX"} and st.find("Kensington Olympia") == {"KENOLYM"}


def test_other_operator_vpt_merged(monkeypatch):
    """Another operator's VPT adds its trains to the book (marked with its operator, stock blank, working times)."""
    import openpyxl
    from test_timetable import write_vpt
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", d)
    x, vpt = os.path.join(d, "plan.xml"), os.path.join(d, "other.vpt")
    write_late_xml(x)
    write_vpt(vpt, [dict(id="9Z99XX", start="20261213", end="20270514", bits=2,
                         points=[dict(tip="AAA", dep=23 * 3600 + 30 * 60, plat="2"),
                                 dict(tip="BBB", arr=23 * 3600 + 50 * 60)])])
    text = open(vpt, encoding="latin-1").read().replace("20270516,20271211", "20261213,20270514", 1)
    open(vpt, "w", encoding="latin-1", newline="").write(text)
    plan = SB.read_plan(vpt)
    assert plan.operator == "AA" and plan.trains["9Z99XX"][0].calls[0].plat == "2"
    path, warnings, _s = SB.make_book(x, "Alpha", d, operator="GTR(TLGN)", day_types=["MO"], merge_xml=[vpt])
    rows = [str(r[1].value) for r in openpyxl.load_workbook(path).active.iter_rows(min_row=2)]
    assert any(v.startswith("9Z99XX") and v.endswith("[AA]") for v in rows)
    assert any("VPT" in w for w in warnings)


def _depots_xml(path):
    """write_xml with diagrams 1-2 at an SNGX depot (SL), 3 at a TLGN depot (HE); 4 stays at another depot."""
    write_xml(path)
    text = open(path, encoding="utf-8").read()
    for num, depot in (("1", "SL"), ("2", "SL"), ("3", "HE")):
        text = text.replace(f'<unitDiagram id="{num}" daysrun="{WEEK}"><depot id="XX"/>',
                            f'<unitDiagram id="{num}" daysrun="{WEEK}"><depot id="{depot}"/>')
    open(path, "w", encoding="utf-8").write(text)


def test_book_operator_chooses_trains_by_depot(monkeypatch):
    """TLGN / SNGX books have only the trains worked by that operator's unit diagrams (by depot), All GTR has them
    all; the heading and sheet names follow the choice, and trains of neither operator are reported."""
    import openpyxl
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", d)
    x = os.path.join(d, "plan.xml")
    _depots_xml(x)
    groups = SB.train_groups(SB.read_plan(x))
    assert groups["1A02XX"] == {"SNGX"} and groups["1C04XX"] == {"TLGN"} and "2E05XX" not in groups

    def heads(book_operator):
        path, warnings, _s = SB.make_book(x, "Alpha", d, day_types=["MO"], book_operator=book_operator)
        wb = openpyxl.load_workbook(path)
        ws = wb.worksheets[0]
        return ([str(r[1].value).split("\n")[0] for r in ws.iter_rows(min_row=2) if r[1].value],
                ws.oddHeader.center.text, ws.title, warnings)

    ids, header, title, warnings = heads("SNGX")
    assert ids == ["1A02XX"] and header.startswith("GTR(SNGX)") and "Southern and Gatwick Express" in header
    assert title == "Alpha (SNGX) MO" and any("left out of the SNGX book" in w and "1F06XX" in w for w in warnings)
    ids, header, title, _w = heads("TLGN")
    assert ids == ["1C04XX"] and header.startswith("GTR(TLGN)") and title == "Alpha (TLGN) MO"
    ids, header, _t, warnings = heads("GTR")
    assert set(ids) == {"1A02XX", "1C04XX", "2E05XX", "1F06XX"} and header.startswith("GTR ")
    assert not any("left out" in w for w in warnings)
    assert SB.book_operator_of("All GTR") == "GTR" and SB.book_operator_of("GTR(SNGX)") == "SNGX"
    assert SB.book_operator_of("Thameslink") == ""
    try:
        SB.make_book(x, "Alpha", d, book_operator="XC")
    except SB.StationBookError as exc:
        assert "TLGN, SNGX or GTR" in str(exc)
    else:
        raise AssertionError("an unknown book operator was accepted")


def test_other_operator_f3_print_merged_and_chosen(monkeypatch):
    """An Attune Single Train Report (F3) print adds another operator's trains (each with its own operator from the
    print); list_operators names them and other_operators leaves the unticked ones out."""
    import openpyxl
    from test_timetable import write_attune_pdf
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", d)
    x, f3, vpt = os.path.join(d, "plan.xml"), os.path.join(d, "south.pdf"), os.path.join(d, "other.vpt")
    _depots_xml(x)
    write_attune_pdf(f3, [dict(id="1Q50BS", days="SX", rows=[
        ("AAA", "Alpha", "", "09.15", "", "09.15", "", "TB", "4"),
        ("BBB", "Beta", "09.30", "", "09.30", "", "", "TF", "1")])])
    plan = SB.read_plan(f3)
    t = plan.trains["1Q50BS"][0]
    assert plan.operator == "SN" and t.operator == "SN" and t.days == {0, 1, 2, 3, 4}
    assert (t.calls[0].loc, t.calls[0].dep, t.calls[0].plat, t.calls[-1].arr) == ("AAA", 33300, "4", 34200)
    assert plan.start == "2027-05-17" and plan.end == "2027-12-10"
    from test_timetable import write_vpt
    write_vpt(vpt, [dict(id="9Z99XX", start="20261213", end="20270514", bits=2,
                         points=[dict(tip="AAA", dep=10 * 3600, plat="2"), dict(tip="BBB", arr=10 * 3600 + 600)])])
    assert SB.list_operators([f3, vpt, os.path.join(d, "missing.xml")]) == ["AA", "SN"]

    def rows(**kw):
        path, warnings, _s = SB.make_book(x, "Alpha", d, day_types=["MO"], book_operator="GTR", merge_xml=[f3, vpt],
                                          **kw)
        return [str(r[1].value) for r in openpyxl.load_workbook(path).active.iter_rows(min_row=2)], warnings

    got, warnings = rows()
    assert any(v.startswith("1Q50BS") and v.endswith("[SN]") for v in got) and any("[AA]" in v for v in got)
    assert any("south.pdf" in w for w in warnings)
    got, _w = rows(other_operators=["AA"])
    assert not any("[SN]" in v for v in got) and any("[AA]" in v for v in got)


def test_stationbook_cli_operator_flags(tmp_path, monkeypatch):
    """--other-operators needs --merge (refused before the XML is read); --book-operator picks the trains."""
    import contextlib
    import io
    import TrainPlanningTools as cli
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def run(*args):
        out, code = io.StringIO(), 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                cli.stationbook_cli(list(args))
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    code, text = run("--xml", str(tmp_path / "missing.xml"), "--station", "Alpha", "--other-operators", "XC")
    assert code == 2 and "--merge" in text
    code, text = run("--xml", "x.xml", "--station", "Alpha", "--book-operator", "XC")
    assert code == 2 and "invalid choice" in text
    x = str(tmp_path / "plan.xml")
    _depots_xml(x)
    code, text = run("--xml", x, "--station", "Alpha", "--sheets", "MO", "--book-operator", "tlgn", "--out",
                     str(tmp_path), "--name", "tl")
    assert code == 0 and "1 departure row on 1 sheet" in text
