"""How the Excel outputs are laid out: frozen headings, filters (totals left out), landscape printing with the
headings repeated on every page, the shared heading colour, and real Excel times in stats packs."""
import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_stats_pack_tabs(tmp_path):
    from rstools.statspack import compare, xlsxw
    from rstools.statspack.stats import Clock, Dur, Row, Table
    wb = xlsxw.Workbook()
    t = Table("Diagram Summary", [Row(["A1", Clock(90000), Dur(3600)], "body"),
                                  Row(["A2", Clock(3600), Dur(-60)], "body"),
                                  Row(["Total", None, Dur(7200)], "total")])
    xlsxw.render_table(wb, "Diagram Summary", "Diagram Summary", t)
    xlsxw.render_report(wb, "Report", "Report", ["Unit", "Miles"], [["1", 2], ["Total", 2]], ["body", "total"])
    path = str(tmp_path / "pack.xlsx")
    wb.save(path)
    book = openpyxl.load_workbook(path)
    ws = book["Diagram Summary"]
    assert ws.freeze_panes == "A3" and ws.auto_filter.ref == "A2:C4"           # the total row is not filtered
    assert ws.page_setup.orientation == "landscape" and ws.print_title_rows == "$1:$2"
    assert ws["B3"].number_format == "[h]:mm:ss" and abs(ws["B3"].value.total_seconds() - 90000) < 1
    assert ws["C4"].value == "-0:01:00"                                        # a negative time stays text
    assert book["Report"].auto_filter.ref == "A2:B3"
    read = dict(compare.read_pack(path))["Diagram Summary"]
    assert read.rows[0].cells[1] == 90000 and isinstance(read.rows[0].cells[1], xlsxw.Clock)
    assert isinstance(read.rows[0].cells[2], xlsxw.Dur)


def test_cwn_change_report(tmp_path):
    from cwn_compare.compare import Change
    from cwn_compare.report import write_report
    from rstools.timetable.xlstyle import HEAD_FILL
    changes = [Change("TIME", "VIC", "Victoria", "k", "1A01", "time", "main", old="05.00", new="05.05",
                      description="Time changed from 05.00 to 05.05")]
    path = str(tmp_path / "r.xlsx")
    write_report(path, changes, [{"round": 1, "colour": "FFFF00", "original": "a", "updated": "b"}], {})
    book = openpyxl.load_workbook(path)
    for name in ("All Changes", "Changes by Train", "New and Cancelled Trains"):
        ws = book[name]
        assert ws.freeze_panes == "A2" and ws.auto_filter.ref and ws.page_setup.orientation == "landscape"
        assert ws.print_title_rows == "$1:$1" and not ws.sheet_view.showGridLines
        assert ws["A1"].fill.fgColor.rgb == HEAD_FILL
    assert book["Summary"].page_setup.orientation == "landscape"


def test_shared_result_sheets(tmp_path):
    from rstools.timetable.xlstyle import add_sheet, new_workbook
    wb = new_workbook()
    ws = add_sheet(wb, "Results", ["A", "B"], [[1, 2], [3, 4]], [10, 10], bold_last=True)
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref == "A1:B2" and ws.print_title_rows == "$1:$1"
