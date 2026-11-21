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


def test_station_names_network_rail_and_attune():
    """Network Rail's station names match Attune's."""
    from rstools.statspack.seats import Stations
    st = Stations({"VICTRIC": "London Victoria (C)", "VICTRIE": "London Victoria", "STLNRWS": "St. Leonards Warrior Sq",
                   "LBGHJN": "Loughborough Jn", "KNGX": "London Kings Cross", "KENOLYM": "Kensington (Olympia)"})
    assert st.find("London Victoria (Central)") == {"VICTRIC"} and st.find("London Victoria (Eastern)") == {"VICTRIE"}
    assert st.find("St Leonards Warrior Square") == {"STLNRWS"} and st.find("Loughborough Junction") == {"LBGHJN"}
    assert st.find("London King’s Cross") == {"KNGX"} and st.find("Kensington Olympia") == {"KENOLYM"}
