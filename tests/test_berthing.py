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
    assert ws["A2"].value == "Plat 1" and ws["B2"].value == 12 or ws["B2"].value == "12"
    assert ws["I2"].value == "4 387 02+02" and ws["J2"].value == "4 387 0500"            # Mon finish / Tue start
    assert ws["I2"].font.color.rgb == "FF00B050"                                          # 387/3: green
    assert ws["A3"].value == "NO ATTACH"                                                  # spelling slip fixed
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
    thu = ws["O2"]                                                                        # Thursday finish
    assert thu.value == "4 387 03+15" and thu.font.b and thu.fill.fgColor.rgb == "FFE4DFEC"
    assert not ws["M2"].font.b                                                             # Wednesday: LTP
    assert "STP" in r.chart


def test_add_round_highlights_only_changes(data):
    first = engine.generate([str(data / "plan.xml")], str(data / "chart.xlsx"), str(data))
    trains, diagrams = base_plan(arrive="02:10:00")
    (data / "plan2.xml").write_text(xml(trains, diagrams))
    # an earlier round's colour on a cell that does not change this time is kept
    wb = openpyxl.load_workbook(first.chart)
    wb["Brighton"]["J2"].fill = openpyxl.styles.PatternFill("solid", fgColor="FF00B0F0")
    wb.save(first.chart)
    r = engine.add_round(first.chart, [str(data / "plan.xml")], [str(data / "plan2.xml")], "92D050", str(data),
                         "", "Proof 3")
    ws = openpyxl.load_workbook(r.chart)["Brighton"]
    assert ws["I2"].value == "4 387 02+10" and ws["I2"].fill.fgColor.rgb == "FF92D050"     # changed: new colour
    assert ws["J2"].fill.fgColor.rgb == "FF00B0F0"                                          # earlier round kept
    assert ws["C8"].fill.fill_type is None                                                 # unchanged: no fill
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
    assert ws["D2"].fill.fgColor.rgb == "FFFFC000" and ws["C2"].fill.fill_type is None


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
    assert ws.cell(p7 - 1, 1).border.bottom.color.rgb[-6:] == SECTION_LINE      # line under the first location
    other = labels[next(k for k in labels if str(k).startswith("Other -"))]
    in_box = [r for r in range(p7, other) if ws.cell(r, 3).value == "OUT OF USE UNTIL FURTHER NOTICE"]
    assert in_box and any(str(rng).startswith(f"C{in_box[0]}:R") for rng in ws.merged_cells.ranges)
    assert ws.cell(in_box[0], 3).font.b and ws.cell(in_box[0], 3).font.color.rgb[-6:] == NOTE_COLOUR
    assert not any(ws.cell(r, 1).value == "OUT OF USE UNTIL FURTHER NOTICE" for r in range(1, ws.max_row + 1))
    assert p7 - p1 == other - p7                              # every box on the sheet the same height
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
        assert not any(b.label in ("4 377", "Cars") or b.label.startswith("Unit counts") for b in again.blocks)
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
