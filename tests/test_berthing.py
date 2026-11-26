"""Berthing charts from synthetic Attune XML and a synthetic chart (no real plan data needed)."""
import os
import sys

import openpyxl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rstools.berthing import engine  # noqa: E402
from rstools.berthing.compare import canonical  # noqa: E402
from rstools.berthing.stays import build  # noqa: E402
from rstools.berthing.xmlread import BerthingError, read_xml  # noqa: E402

ALL = "NNYYYYYYY"            # Attune daysRun: 2nd character Sunday, then Monday..Saturday
WEEKDAYS = "NNYYYYYNN"


def train(tid, key, legs, days=ALL, plan="L"):
    body = "".join(f'<leg origin="{o}" dep="{d}" dest="{t}" arr="{a}" depPlat="{dp}" arrPlat="{ap}"/>'
                   for o, d, t, a, dp, ap in legs)
    return f'<train id="{tid}" trainKey="{key}" daysRun="{days}" planType="{plan}">{body}</train>'


def diagram(num, fleet, moves, note, days=ALL, plan="L", depot="BI"):
    """moves: (origin, dep, dest, arr, headcode, trainKey, [coupled diagram numbers front first])"""
    body = ""
    for i, (o, d, t, a, hc, key, coupled) in enumerate(moves, 1):
        cp = "".join(f'<coupled position="{p}"><diagram id="{n}"/><depot id="{depot}"/></coupled>'
                     for p, n in enumerate(coupled, 1))
        body += (f'<diagMovement legno="{i}"><journey origin="{o}" dep="{d}" dest="{t}" arr="{a}">'
                 f'<activity trainid="{hc}" trainKey="{key}"></activity>{cp}</journey></diagMovement>')
    loc = moves[-1][2] if moves else "BRGHTN"
    body += f'<diagStatic legno="99" loc="{loc}" time="00:00:00"><activity id=" "><text>{note}</text></activity>' \
            '</diagStatic>'
    return (f'<unitDiagram id="{num}" type="{plan}" daysrun="{days}"><depot id="{depot}"/><res id="{fleet}"/>'
            f'<details>{body}</details></unitDiagram>')


def xml(trains, diagrams, start="2026-12-13", end="2027-05-15"):
    return (f'<diagramExchange plantype="L" startdate="{start}" enddate="{end}" '
            'xmlns="http://www.tracsis.com/TTVP_Interface">'
            f'<trainList>{"".join(trains)}</trainList><locationList>'
            '<location tiploc="BRGHTN" longDesc="Brighton"/>'
            '<location tiploc="HOVEY36" longDesc="Hove Yard Sidings 3-6"/>'
            f'</locationList><diagramList><unitDiagramList>{"".join(diagrams)}</unitDiagramList></diagramList>'
            '</diagramExchange>')


def base_plan(arrive="02:02:00", plan="L"):
    """BI1 (387/3) berths at Brighton P1 every night, leaving 05:00; BI2 (387/2) + BI3 (377/4) coupled into
    Hove Yard S3; BI4 (377/4) berths at Brighton P7 and leaves as the rear portion of BI5, which moves in."""
    trains = [train("5H73BV", "1", [("HOVE", "01:50:00", "BRGHTN", arrive, "", "1")], plan=plan),
              train("2S02BS", "2", [("BRGHTN", "05:00:00", "HOVE", "05:05:00", "1", "")]),
              train("5S39BR", "3", [("BRGHTN", "23:30:00", "HOVEY36", "23:35:00", "4", "S3")]),
              train("5S40BR", "4", [("HOVEY36", "05:23:00", "BRGHTN", "05:30:00", "S3", "4")]),
              train("1U73BS", "5", [("VIC", "23:00:00", "BRGHTN", "00:30:00", "", "7")]),
              train("5U01BS", "6", [("LOVRSWS", "05:00:00", "BRGHTN", "05:10:00", "", "7")]),
              train("1U04BS", "7", [("BRGHTN", "05:22:00", "VIC", "06:30:00", "7", "")]),
              train("5X99BS", "8", [("HOVE", "02:00:00", "BRGHTN", "02:20:00", "", "2")])]
    diagrams = [diagram(1, "387/3", [("HOVE", "01:50:00", "BRGHTN", arrive, "5H73BV", "1", [])], "BI10 05:00",
                        plan=plan),
                diagram(10, "387/3", [("BRGHTN", "05:00:00", "HOVE", "05:05:00", "2S02BS", "2", [])], "Stabld"),
                diagram(2, "387/2", [("BRGHTN", "23:30:00", "HOVEY36", "23:35:00", "5S39BR", "3", [2, 3])],
                        "BI20 05+23 (F)"),
                diagram(20, "387/2", [("HOVEY36", "05:23:00", "BRGHTN", "05:30:00", "5S40BR", "4", [20, 30])],
                        "Stabld"),
                diagram(3, "377/4", [("BRGHTN", "23:30:00", "HOVEY36", "23:35:00", "5S39BR", "3", [2, 3])],
                        "BI30 05+23 (R)"),
                diagram(30, "377/4", [("HOVEY36", "05:23:00", "BRGHTN", "05:30:00", "5S40BR", "4", [20, 30])],
                        "Stabld"),
                diagram(4, "377/4", [("VIC", "23:00:00", "BRGHTN", "00:30:00", "1U73BS", "5", [])], "BI40 05:22 (R)"),
                diagram(40, "377/4", [("BRGHTN", "05:22:00", "VIC", "06:30:00", "1U04BS", "7", [5, 40])], "Stabld"),
                diagram(5, "377/4", [("LOVRSWS", "05:00:00", "BRGHTN", "05:10:00", "5U01BS", "6", []),
                                     ("BRGHTN", "05:22:00", "VIC", "06:30:00", "1U04BS", "7", [5, 40])], "Stabld"),
                diagram(6, "377/4", [("HOVE", "02:00:00", "BRGHTN", "02:20:00", "5X99BS", "8", [])], "Stabld")]
    return trains, diagrams


def make_chart(path, extra_sheet=None, rdh_name="Hove Yard"):
    """A chart laid out like SNGX's, with the old counting rows and formulas, notes and a spelling slip."""
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover"
    for r, text in enumerate(["Southern/Gatwick Express", "Berthing Chart", "Proof 1", "13/12/26 - 15/05/27",
                              "Updates Highlighted in Yellow", "Issued 20/07/2026"], 1):
        cover.cell(r, 1, text)
        cover.merge_cells(start_row=r, start_column=1, end_row=r, end_column=15)
    cover.cell(9, 2, "377/3")
    cover.cell(9, 3, "1s a 3 car unit")
    heads = ["Siding", "Capacity", "FRI FINISH", "SAT START", "SAT FINISH", "SUN START", "SUN FINISH", "MON START",
             "MON FINISH", "TUE START", "TUE FINISH", "WED START", "WED FINISH", "THUR START", "THUR FINISH",
             "FRI START", "FRI FINISH", "SAT START"]
    ws = wb.create_sheet("Brighton")
    ws.append(heads)
    ws["A2"], ws["B2"], ws["A3"] = "Plat 1", 12, "NO ATTATCH"
    ws["C2"] = "4 387 0000"                                  # old units: replaced by the XML's
    ws["A5"] = "Start1"
    ws["A6"] = "*4 387*"
    ws["C6"] = "=COUNTIF(C$1:C$5,$A6)"
    ws["A7"] = "Finish1"
    ws["A8"], ws["B8"] = "Plat 7", 12
    ws["D10"] = "OUT OF USE UNTIL FUTHER NOTICE"
    hv = wb.create_sheet(rdh_name)
    hv.append(heads)
    hv["A2"], hv["B2"] = "Siding 3", 12
    hv["C2"] = "(4 377) 23+00"
    hv["C2"].fill = openpyxl.styles.PatternFill("solid", fgColor="FFFFFF00")
    if extra_sheet:
        ex = wb.create_sheet(extra_sheet)
        ex.append(heads)
        ex["A2"] = "Plat 1"
    wb.save(path)


def row_of(ws, label, col=1):
    """The row whose column `col` holds `label` (rows move when a sheet's locations have their banner rows)."""
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, col).value == label)


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    trains, diagrams = base_plan()
    (tmp_path / "plan.xml").write_text(xml(trains, diagrams))
    make_chart(str(tmp_path / "chart.xlsx"))
    return tmp_path


def test_stays_follow_next_day_workings(data):
    b = build([read_xml(str(data / "plan.xml"))])
    s = {(x.unit, x.first_night): x for x in b.stays}
    p1 = s[("BI1", 0)]                                       # Monday night at Brighton P1
    assert (p1.loc, p1.plat, p1.arrive.ecs, p1.depart.time // 60, p1.depart.ecs) == ("BRGHTN", "1", True, 300, False)
    front, rear = s[("BI2", 0)], s[("BI3", 0)]
    assert front.arrive.coupled == rear.arrive.coupled == ["BI2", "BI3"] and front.plat == "S3"
    assert s[("BI4", 0)].depart.rp and not front.depart.rp   # BI5 moves in and BI4 leaves as its rear portion
    assert front.depart.coupled == ["BI20", "BI30"]


def test_berth_days_and_stp(tmp_path):
    """A note skipping days gives 'Berth' days; an STP diagram replaces the LTP one and is marked."""
    trains, diagrams = base_plan()
    diagrams[0] = diagram(1, "387/3", [("HOVE", "01:50:00", "BRGHTN", "02:02:00", "5H73BV", "1", [])], "BI10 05:00WO",
                          days="NNYNNNNNN")                 # Monday's unit next works on Wednesday
    (tmp_path / "ltp.xml").write_text(xml(trains, diagrams))
    stp_trains = [train("5H73BV", "1", [("HOVE", "01:50:00", "BRGHTN", "03:15:00", "", "1")], plan="S")]
    stp_diagrams = [diagram(1, "387/3", [("HOVE", "01:50:00", "BRGHTN", "03:15:00", "5H73BV", "1", [])],
                            "BI10 05:00", days="NNNNNYNNN", plan="S")]                      # Thursday, STP
    (tmp_path / "stp.xml").write_text(xml(stp_trains, stp_diagrams))
    b = build([read_xml(str(tmp_path / "ltp.xml"), 0), read_xml(str(tmp_path / "stp.xml"), 1)], mark_stp=True)
    mon = next(x for x in b.stays if x.unit == "BI1" and x.first_night == 0)
    assert mon.nights == 2 and mon.depart.day == 2           # Monday night, berthed Tuesday, away Wednesday
    thu = next(x for x in b.stays if x.unit == "BI1" and x.first_night == 3)
    assert thu.arrive.time // 60 == 3 * 60 + 15 and thu.arrive.stp


def test_generate_chart(data):
    r = engine.generate([str(data / "plan.xml")], str(data / "chart.xlsx"), str(data), "", "Proof 2")
    wb = openpyxl.load_workbook(r.chart)
    ws = wb["Brighton"]
    assert [c.value for c in ws[1]][:3] == ["Siding", "Capacity", "FRI FINISH"]
    p1 = row_of(ws, "Plat 1")
    assert ws.cell(p1, 2).value in (12, "12")
    assert ws.cell(p1, 9).value == "4 387 02+02" and ws.cell(p1, 10).value == "4 387 0500"    # Mon finish / Tue start
    assert ws.cell(p1, 9).font.color.rgb == "FF00B050"                                    # 387/3: green
    assert ws.cell(p1 + 1, 1).value == "NO ATTACH"                                        # spelling slip fixed
    assert not any(isinstance(c.value, str) and (c.value.startswith("=") or "COUNTIF" in c.value or
                                                 c.value in ("Start1", "Finish1", "*4 387*"))
                   for row in ws.iter_rows() for c in row)                                 # old counts gone
    texts = [c.value for row in ws.iter_rows() for c in row if c.value]
    assert "OUT OF USE UNTIL FURTHER NOTICE" in texts                                     # notes kept
    assert any(isinstance(t, str) and t.endswith("RP05:22".replace(":", "")) for t in texts)  # BI4 'RP0522'
    assert "4 387 0000" not in texts                                                       # old units replaced
    hv = wb["Hove Yard"]
    col = [hv.cell(r, 9).value for r in range(2, 4)]                                       # Monday finish
    assert col == ["(4 387) 23+35", "(4 377)"] and hv["I2"].font.color.rgb == "FFFF0000"   # coupled, 387/2 red
    assert hv["C2"].fill.fill_type is None                                                 # a new chart starts clean
    assert any("Other - BRGHTN platform/road 2" in str(c.value) for c in ws["A"])          # P2 not on the sheet
    assert wb["Cover"]["A3"].value == "Proof 2" and wb["Cover"]["C9"].value == "is a 3 car unit"


def test_stp_chart_marks_stp_trains(data):
    stp_trains = [train("5H73BV", "1", [("HOVE", "01:50:00", "BRGHTN", "03:15:00", "", "1")], plan="S")]
    stp_diagrams = [diagram(1, "387/3", [("HOVE", "01:50:00", "BRGHTN", "03:15:00", "5H73BV", "1", [])],
                            "BI10 05:00", days="NNNNNYNNN", plan="S")]
    (data / "stp.xml").write_text(xml(stp_trains, stp_diagrams))
    r = engine.generate([str(data / "plan.xml"), str(data / "stp.xml")], str(data / "chart.xlsx"), str(data))
    ws = openpyxl.load_workbook(r.chart)["Brighton"]
    p1 = row_of(ws, "Plat 1")
    thu = ws.cell(p1, 15)                                                                 # Thursday finish
    assert thu.value == "4 387 03+15" and thu.font.b and thu.fill.fgColor.rgb == "FFE4DFEC"
    assert not ws.cell(p1, 13).font.b                                                      # Wednesday: LTP
    assert "STP" in r.chart


def test_add_round_highlights_only_changes(data):
    first = engine.generate([str(data / "plan.xml")], str(data / "chart.xlsx"), str(data))
    trains, diagrams = base_plan(arrive="02:10:00")
    (data / "plan2.xml").write_text(xml(trains, diagrams))
    # an earlier round's colour on a cell that does not change this time is kept
    wb = openpyxl.load_workbook(first.chart)
    sheet = wb["Brighton"]
    sheet.cell(row_of(sheet, "Plat 1"), 10).fill = openpyxl.styles.PatternFill("solid", fgColor="FF00B0F0")
    wb.save(first.chart)
    r = engine.add_round(first.chart, [str(data / "plan.xml")], [str(data / "plan2.xml")], "92D050", str(data),
                         "", "Proof 3")
    ws = openpyxl.load_workbook(r.chart)["Brighton"]
    p1, p7 = row_of(ws, "Plat 1"), row_of(ws, "Plat 7")
    assert ws.cell(p1, 9).value == "4 387 02+10"
    assert ws.cell(p1, 9).fill.fgColor.rgb == "FF92D050"                                    # changed: new colour
    assert ws.cell(p1, 10).fill.fgColor.rgb == "FF00B0F0"                                   # earlier round kept
    assert ws.cell(p7, 3).fill.fill_type is None                                           # unchanged: no fill
    rep = openpyxl.load_workbook(r.report)["Changes"]
    rows = [[c.value for c in row] for row in rep.iter_rows(min_row=2) if row[0].value]
    assert rows and all(row[:2] == ["Brighton", "Plat 1"] and row[5] == "4 387 02+10" for row in rows)
    assert openpyxl.load_workbook(r.chart)["Cover"]["A5"].value == "Updates Highlighted in light green"


def test_compare_charts(data):
    make_chart(str(data / "old.xlsx"), extra_sheet="Barnham", rdh_name="Hove Yard Sdgs")
    wb = openpyxl.load_workbook(data / "old.xlsx")
    wb["Brighton"]["C2"] = "4 387  00 00"                    # the same unit and time with spacing slips
    wb["Brighton"]["D2"] = "4 387 0500"
    wb.save(data / "old.xlsx")
    make_chart(str(data / "new.xlsx"), rdh_name="Hove Yard Sdg")
    wb = openpyxl.load_workbook(data / "new.xlsx")
    wb["Brighton"]["D2"] = "4 387 0510"
    wb.save(data / "new.xlsx")
    r = engine.compare_charts(str(data / "old.xlsx"), str(data / "new.xlsx"), "FFC000", str(data))
    rows = [[c.value for c in row] for row in openpyxl.load_workbook(r.report)["Changes"].iter_rows(min_row=2)
            if row[0].value]
    assert ["Brighton", "Plat 1", "SAT START", "Changed", "4 387 0500", "4 387 0510"] in rows
    assert ["Barnham", "(whole sheet)", None, "Removed", "Sheet not in the newer chart", None] in rows
    assert len(rows) == 2                                    # spacing and the renamed sheet are not changes
    ws = openpyxl.load_workbook(r.chart)["Brighton"]
    p1 = row_of(ws, "Plat 1")
    assert ws.cell(p1, 4).fill.fgColor.rgb == "FFFFC000" and ws.cell(p1, 3).fill.fill_type is None


def test_canonical_text():
    assert canonical("(4 387) 00 45") == canonical("(4 387) 0045")
    assert canonical("L(4 387) Berth") == canonical("(4 387) berth")
    assert canonical("12700 0228TLK") == canonical("12 700 0228 TLK")
    assert canonical("4 377 RP 0600") == canonical("4 377 RP0600")
    assert canonical("4 387 0500") != canonical("4 387 0510")


def test_bad_inputs_give_plain_messages(data):
    (data / "bad.xml").write_text("<oops>")
    (data / "other.xml").write_text("<root/>")
    (data / "nodiag.xml").write_text(xml([], []))
    _trains, diagrams = base_plan()
    (data / "notrains.xml").write_text(xml([], diagrams))
    for name, says in (("bad.xml", "could not be read"), ("other.xml", "not an Attune"),
                       ("nodiag.xml", "no unit diag"), ("notrains.xml", "has no trains")):
        with pytest.raises(BerthingError, match=says):
            read_xml(str(data / name))
    wb = openpyxl.Workbook()
    wb.active["A1"] = "not a chart"
    wb.save(data / "plain.xlsx")
    with pytest.raises(BerthingError, match="No berthing chart sheets"):
        engine.generate([str(data / "plan.xml")], str(data / "plain.xlsx"), str(data))
    with pytest.raises(BerthingError, match="could not be found"):
        engine.generate([str(data / "missing.xml")], str(data / "chart.xlsx"), str(data))
    with pytest.raises(BerthingError, match="same file"):
        engine.compare_charts(str(data / "chart.xlsx"), str(data / "chart.xlsx"), "FFFF00", str(data))


def _fill(cell):
    return cell.fill.fgColor.rgb[-6:] if cell.fill is not None and cell.fill.fill_type == "solid" else ""


def test_maint_units_are_left_off_the_chart(tmp_path, monkeypatch):
    """MAINT moves are not berthed, and a location that only has MAINT units does not get an 'Other' block."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    trains, diagrams = base_plan()
    trains.append(train("5M01XX", "20", [("HOVE", "01:00:00", "BRGHTN", "01:10:00", "", "9")]))
    diagrams.append(diagram(50, "MAINT", [("HOVE", "01:00:00", "BRGHTN", "01:10:00", "5M01XX", "20", [])],
                            "MAINT 04+45"))
    (tmp_path / "plan.xml").write_text(xml(trains, diagrams))
    make_chart(str(tmp_path / "chart.xlsx"))
    assert any(s.fleet.upper() == "MAINT" for s in build([read_xml(str(tmp_path / "plan.xml"))]).stays)
    res = engine.generate([str(tmp_path / "plan.xml")], str(tmp_path / "chart.xlsx"), str(tmp_path), "maint", "P")
    ws = openpyxl.load_workbook(res.chart)["Brighton"]
    text = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert not any(t.startswith("Other - BRGHTN platform/road 9") for t in text)    # only MAINT berths there
    assert not any("MAINT" in t.upper() for t in text)


def test_original_style_formatting_sections_and_counts(data):
    """Siding names and capacities on light blue, notes in red bold, every berth's box the same height, a coloured
    line between siding locations (from the old Start/Finish counting rows) and, as an option, unit counts per
    location with the cars red where they are over its capacity."""
    from rstools.berthing.layout import read_chart
    from rstools.berthing.mapping import load
    from rstools.berthing.writer import NOTE_COLOUR, OVER_FILL, SIDING_FILL, SECTION_LINE
    lay = read_chart(str(data / "chart.xlsx"), load())
    bri = next(s for s in lay.sheets if s.name == "Brighton")
    assert [(b.label, b.section) for b in bri.blocks] == [("Plat 1", 0), ("Plat 7", 1)]   # split by the old counts
    wb = openpyxl.load_workbook(str(data / "chart.xlsx"))
    wb["Brighton"]["B8"] = 2                                 # Plat 7 holds 2 cars: BI4's 4 cars are too many
    wb.save(str(data / "chart2.xlsx"))
    plain = engine.generate([str(data / "plan.xml")], str(data / "chart2.xlsx"), str(data), "plain", "Proof 2")
    counted = engine.generate([str(data / "plan.xml")], str(data / "chart2.xlsx"), str(data), "counts", "Proof 2",
                              counts=True)
    ws = openpyxl.load_workbook(plain.chart)["Brighton"]
    labels = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value}
    p1, p7 = labels["Plat 1"], labels["Plat 7"]
    assert _fill(ws.cell(p1, 1)) == _fill(ws.cell(p1, 2)) == SIDING_FILL and ws.cell(p1, 1).font.b
    note = ws.cell(labels["NO ATTACH"], 1)
    assert note.font.b and note.font.color.rgb[-6:] == NOTE_COLOUR and _fill(note) == SIDING_FILL
    assert ws.cell(p7 - 2, 1).border.bottom.color.rgb[-6:] == SECTION_LINE      # line under the first location
    assert ws.cell(p7 - 1, 1).value == "Location \u2013 Plat 7"
    assert ws.cell(p1 - 1, 1).value == "Location \u2013 Plat 1"
    assert _fill(ws.cell(p7 - 1, 1)) == SECTION_LINE and ws.cell(p7 - 1, 1).font.b      # a banner above each location
    other = labels[next(k for k in labels if str(k).startswith("Other -"))]
    in_box = [r for r in range(p7, other) if ws.cell(r, 3).value == "OUT OF USE UNTIL FURTHER NOTICE"]
    assert in_box and any(str(rng).startswith(f"C{in_box[0]}:R") for rng in ws.merged_cells.ranges)
    assert ws.cell(in_box[0], 3).font.b and ws.cell(in_box[0], 3).font.color.rgb[-6:] == NOTE_COLOUR
    assert not any(ws.cell(r, 1).value == "OUT OF USE UNTIL FURTHER NOTICE" for r in range(1, ws.max_row + 1))
    assert not any(str(v).startswith("Location") and "Other" in str(v) for v in labels)    # 'Other' is its own name
    assert p7 - 1 - p1 == other - p7                          # every box the same height (a banner lies between)
    assert len({ws.column_dimensions[c].width for c in "CDEFGHIJKLMNOPQR"}) == 1
    assert not any(str(v).startswith("Unit counts") for v in labels)            # counts only when asked for
    ws = openpyxl.load_workbook(counted.chart)["Brighton"]
    rows = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value}
    heads = [k for k in rows if str(k).startswith("Unit counts")]
    assert heads == ["Unit counts – Plat 1", "Unit counts – Plat 7", "Unit counts – Other - BRGHTN platform/road 2"] \
        or heads[:2] == ["Unit counts – Plat 1", "Unit counts – Plat 7"]
    cars7 = [r for r in range(rows["Unit counts – Plat 7"], ws.max_row + 1) if ws.cell(r, 1).value == "Cars"][0]
    assert ws.cell(cars7, 2).value == "of 2"
    mon_finish = 9                                            # column I
    assert ws.cell(cars7, mon_finish).value == 4 and _fill(ws.cell(cars7, mon_finish)) == OVER_FILL
    unit_row = [r for r in range(rows["Unit counts – Plat 7"], cars7) if ws.cell(r, 1).value == "4 377"][0]
    assert ws.cell(unit_row, mon_finish).value == 1
    for path in (plain.chart, counted.chart):                # charts made by the app read back the same
        again = next(s for s in read_chart(path, load()).sheets if s.name == "Brighton")
        assert [(b.label, b.section) for b in again.blocks][:2] == [("Plat 1", 0), ("Plat 7", 1)]
        assert not any(b.label in ("4 377", "Cars") or b.label.startswith(("Unit counts", "Location"))
                       for b in again.blocks)
    round_ = engine.add_round(counted.chart, [str(data / "plan.xml")], [str(data / "plan.xml")], "92D050",
                              str(data), "round", counts=True)
    assert round_.summary.startswith("0 change")


def test_built_in_default_layout(data, monkeypatch):
    """With no chart chosen, the chart is made in the app's built-in layout (no trains stored in it); the layout
    file can be remade from a chart and reads back the same."""
    import gzip
    import json
    from rstools.berthing import layout as L
    info = L.default_info()
    assert info and info["sheets"] >= 20 and info["source"].lower().endswith(".xlsx")
    data_ = json.load(gzip.open(L.DEFAULT_FILE, "rt", encoding="utf-8"))
    blocks = [b for sh in data_["sheets"] for b in sh.get("blocks", [])]
    assert blocks and not any("units" in b or "cells" in b for b in blocks)              # no trains stored
    r = engine.generate([str(data / "plan.xml")], "", str(data), "default", "Proof 3")
    wb = openpyxl.load_workbook(r.chart)
    assert "Brighton" in wb.sheetnames and "Three Bridges" in wb.sheetnames
    assert any("built-in layout" in str(c.value) for c in wb["Notes"]["A"])
    tb = next(s for s in L.load_default().sheets if s.name == "Three Bridges")
    assert [b.label for b in tb.blocks][-5:] == [f"Tilgate No {n}" for n in range(1, 6)]
    out = data / "layout.json.gz"
    made = L.save_default(str(data / "chart.xlsx"), str(out))
    assert made["sheets"] == 2
    monkeypatch.setattr(L, "DEFAULT_FILE", str(out))
    L._default_cache.clear()
    try:
        again = L.load_default()
        first = L.read_chart(str(data / "chart.xlsx"), None)
        assert [s.name for s in again.sheets] == [s.name for s in first.sheets]
        assert [[(b.label, b.capacity, b.section) for b in s.blocks] for s in again.sheets] == \
            [[(b.label, b.capacity, b.section) for b in s.blocks] for s in first.sheets]
        assert all(not b.units for s in again.sheets for b in s.blocks)
    finally:
        L._default_cache.clear()


# --------------------------------------------------------------------------- departures on Friday night, label widths
def _stay(first_night, nights, depart=True):
    """A stay that arrives at 23+30 on `first_night` and leaves at 0500 `nights` nights later."""
    from rstools.berthing.stays import End, Stay
    arrive = End(first_night, 23 * 3600 + 30 * 60, "5A01XX", "1", True, False, (0, "1"), [])
    leave = End((first_night + nights) % 7, 5 * 3600, "2B02XX", "1", False, False, (0, "2"), []) if depart else None
    return Stay("BI1", "387/3", "BRGHTN", "1", first_night, nights, arrive, leave)


def _written(first_night, nights, depart=True):
    """The 16 cells of the stay's row as the chart writer fills them (index = column, 0 = FRI FINISH)."""
    from rstools.berthing.chart import Placed, Units, _write_stay
    from rstools.berthing.layout import Block
    blk = Block("Plat 1")
    p = Placed(_stay(first_night, nights, depart), 0, 0)
    _write_stay(blk, p, Units(), [p])
    return blk.units[0]


def _where(row, text):
    return [i for i, cell in enumerate(row) if cell is not None and text in cell.text]


def test_a_stay_ending_on_friday_night_leaves_once_not_in_both_friday_pairs():
    """Friday night is shown twice (columns 0-1 and 14-15). A stay that began before Saturday and leaves after
    Friday night shows its departure only at the end of the week, not also in the week-opening SAT START."""
    thursday = _written(3, 2)                              # Thursday night, then Friday night: leaves Saturday
    assert _where(thursday, "0500") == [15] and thursday[1] is None
    assert _where(thursday, "23+30") == [12]               # arrival intact (Thursday FINISH)
    assert thursday[13].text.endswith("Berth") and thursday[14].text.endswith("Berth")
    saturday = _written(5, 7)                              # a whole week: Saturday night to Friday night
    assert _where(saturday, "0500") == [15] and saturday[1] is None
    tuesday_start = _written(1, 4)                         # Tuesday to Friday night
    assert _where(tuesday_start, "0500") == [15]


def test_departures_elsewhere_are_unchanged():
    """Only the doubled Friday departure moved: a stay that starts on Friday still shows in both Friday pairs, and
    stays that end on any other night write one departure as before."""
    friday = _written(4, 1)
    assert _where(friday, "23+30") == [0, 14] and _where(friday, "0500") == [1, 15]
    weekend = _written(4, 3)                               # Friday, Saturday, Sunday night
    assert _where(weekend, "23+30") == [0, 14] and _where(weekend, "0500") == [5]
    assert _where(_written(1, 2), "0500") == [11]          # Tuesday night, then Wednesday night
    one = _written(3, 1)                                   # a single Thursday night
    assert _where(one, "23+30") == [12] and _where(one, "0500") == [13]
    assert _where(one, "Berth") == [] and one[0] is None and one[14] is None
    unknown = _written(3, 2, depart=False)                 # the XML does not say what it works next
    assert _where(unknown, "0500") == [] and unknown[1] is None and unknown[15] is None


def _old_width(labels, capacity=()):
    """Column A's width as it was calculated before the 'Other - ' / counts labels were handled."""
    a = max([len(x) for x in labels] + [0])
    b = max([len(x) for x in capacity] + [0])
    return max(14.0, min(a * 1.15 + 3, 30.0)), max(10.0, min(b * 1.15 + 3, 18.0))


def _layout(blocks, sections=()):
    from rstools.berthing.layout import GridSheet, Layout
    return Layout("", sheets=[GridSheet("Sheet", blocks=list(blocks), sections=list(sections))])


def test_siding_widths_are_unchanged_without_other_or_counts_labels():
    from rstools.berthing.layout import Block
    from rstools.berthing.writer import _siding_widths
    for labels in (["Plat 1"], ["Plat 1", "Up Horsham Siding"], ["A very long ordinary label that is clipped here"],
                   ["x" * 70]):
        layout = _layout([Block(label, "12") for label in labels])
        assert _siding_widths(layout) == _old_width(labels, ["12"] * len(labels)), labels
        # with counts on, the plain 'Unit counts' heading (no location named) must fit too; nothing else changes
        assert _siding_widths(layout, counts=True)[0] == max(_siding_widths(layout)[0], len("Unit counts") * 1.15 + 3)
        assert _siding_widths(layout, counts=True)[1] == _siding_widths(layout)[1]


def test_other_labels_and_counts_headings_are_not_clipped_beside_column_b():
    from rstools.berthing.layout import COUNTS_HEAD, Block
    from rstools.berthing.writer import WIDE_LABEL_CAP, _siding_widths
    other = "Other - HORSHAM platform/road 2 (no platform)"
    layout = _layout([Block("Plat 1", "12"), Block(other, "")])
    a, b = _siding_widths(layout)
    assert a >= len(other) * 1.15 + 3 > 30 and a == min(len(other) * 1.15 + 3, WIDE_LABEL_CAP)
    assert b == _old_width(["Plat 1"], ["12"])[1]                                  # column B as before
    far = _layout([Block("Other - " + "X" * 80)])
    assert _siding_widths(far)[0] == WIDE_LABEL_CAP                               # never wider than the cap
    heading = f"{COUNTS_HEAD} – Three Bridges Up Siding North and Tilgate"
    sections = ["Three Bridges Up Siding North and Tilgate"]
    plain = _layout([Block("Plat 1", "12")], sections)
    assert _siding_widths(plain)[0] == _old_width(["Plat 1"])[0]                 # counts off: heading ignored
    assert _siding_widths(plain, counts=True)[0] == min(len(heading) * 1.15 + 3, WIDE_LABEL_CAP)
    assert _siding_widths(plain, counts=True)[0] >= len(heading) * 1.15 + 3


def test_chart_column_a_fits_the_counts_heading_and_other_label(tmp_path):
    from rstools.berthing import writer
    from rstools.berthing.layout import COUNTS_HEAD, Block
    other = "Other - HORSHAM platform/road 2 (no platform)"
    name = "Three Bridges Up Siding North and Tilgate"
    layout = _layout([Block("Plat 1", "12", section=0), Block(other, "", section=0)], [name])
    narrow, wide = str(tmp_path / "narrow.xlsx"), str(tmp_path / "wide.xlsx")
    writer.write(layout, narrow)
    writer.write(layout, wide, counts=True)
    plain_a = openpyxl.load_workbook(narrow)["Sheet"].column_dimensions["A"].width
    counts_a = openpyxl.load_workbook(wide)["Sheet"].column_dimensions["A"].width
    heading = f"{COUNTS_HEAD} – {name}"
    assert plain_a >= len(other) * 1.15 + 3                    # the 'Other - ' label always fits now
    assert counts_a >= len(heading) * 1.15 + 3 and counts_a >= plain_a


# --------------------------------------------------------------------------- a banner above each siding location
def _banners(ws):
    return [(r, ws.cell(r, 1).value) for r in range(1, ws.max_row + 1)
            if str(ws.cell(r, 1).value or "").startswith("Location \u2013 ")]


def test_each_location_on_a_multi_location_sheet_has_a_banner(data):
    r = engine.generate([str(data / "plan.xml")], str(data / "chart.xlsx"), str(data), "banners", "Proof 2")
    wb = openpyxl.load_workbook(r.chart)
    brighton = wb["Brighton"]
    banners = _banners(brighton)
    assert [text for _r, text in banners] == ["Location \u2013 Plat 1", "Location \u2013 Plat 7"]   # not for 'Other -'
    first = banners[0][0]
    assert any(str(rng) == f"A{first}:R{first}" for rng in brighton.merged_cells.ranges)           # across the sheet
    assert brighton.row_dimensions[first].height > 15 and brighton.cell(first, 1).font.color.rgb[-6:] == "FFFFFF"
    assert _banners(wb["Hove Yard"]) == []                    # one location: the sheet looks as it did
    assert wb["Hove Yard"]["A2"].value == "Siding 3"


def test_banners_on_the_built_in_layout_read_back_the_same(data):
    from rstools.berthing import layout as L
    from rstools.berthing.mapping import load
    first = engine.generate([str(data / "plan.xml")], "", str(data), "one", "Proof 1")
    wb = openpyxl.load_workbook(first.chart)
    three = wb["Three Bridges"]
    assert [text for _r, text in _banners(three)] == [
        "Location \u2013 Back Road", "Location \u2013 Up Horsham Sdg", "Location \u2013 Up Siding North",
        "Location \u2013 Tilgate"]
    built = {s.name: s for s in L.load_default().sheets}
    again = {s.name: s for s in L.read_chart(first.chart, load()).sheets}
    for name in ("Brighton", "Three Bridges"):
        assert again[name].sections == built[name].sections                   # names survive the round trip
        assert [(b.label, b.section) for b in again[name].blocks] == [(b.label, b.section) for b in built[name].blocks]
        assert again[name].lead == built[name].lead                           # a banner is never kept as a note
    multi = [sh for sh in built.values() if len(getattr(sh, "sections", [])) > 1]
    assert sum(len(_banners(ws)) for ws in wb.worksheets) == sum(len(sh.sections) for sh in multi) >= 20


def test_rounds_and_comparisons_ignore_the_banners(data):
    first = engine.generate([str(data / "plan.xml")], str(data / "chart.xlsx"), str(data), "r1", "Proof 1")
    second = engine.add_round(first.chart, [str(data / "plan.xml")], [str(data / "plan.xml")], "92D050", str(data),
                              "r2")
    third = engine.add_round(second.chart, [str(data / "plan.xml")], [str(data / "plan.xml")], "92D050", str(data),
                             "r3", counts=True)
    sheets = [openpyxl.load_workbook(p.chart)["Brighton"] for p in (first, second, third)]
    assert [len(_banners(ws)) for ws in sheets] == [2, 2, 2]                 # no banner lost or doubled
    assert sheets[0].max_row == sheets[1].max_row                             # nothing grew round to round
    notes = [ws.cell(r, 1).value for ws in sheets[:2] for r in range(1, ws.max_row + 1)]
    assert "Plat 1" in notes and not any(str(n).startswith("Location") and "NO ATTACH" in str(n) for n in notes)
    assert second.summary.startswith("0 change") and third.summary.startswith("0 change")
    cmp = engine.compare_charts(first.chart, second.chart, "FFC000", str(data), "same")
    assert cmp.summary.startswith("0 difference")


def test_changes_name_the_siding_location(data):
    from rstools.berthing.compare import diff
    from rstools.berthing.layout import read_chart
    from rstools.berthing.mapping import load
    old, new = str(data / "old.xlsx"), str(data / "new.xlsx")
    make_chart(old)
    make_chart(new)
    wb = openpyxl.load_workbook(new)
    wb["Brighton"]["D2"] = "4 387 0510"                       # Plat 1, the first location
    wb["Brighton"]["D8"] = "4 377 0600"                       # Plat 7, the second
    wb["Hove Yard"]["D2"] = "(4 377) 0300"                    # a sheet with one location
    wb.save(new)
    changes, _marked = diff(read_chart(old, load()), read_chart(new, load()))
    got = {(c.sheet, c.berth): (c.section, c.rank) for c in changes}
    assert got[("Brighton", "Plat 1")] == ("Plat 1", 0) and got[("Brighton", "Plat 7")] == ("Plat 7", 1)
    assert got[("Hove Yard", "Siding 3")] == ("", 0)
