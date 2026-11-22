"""Synthetic end-to-end tests (no real CWN data needed).

Run with:  python -m pytest tests   (or simply: python tests/test_compare.py)
"""
import os
import sys
import tempfile

import openpyxl
from openpyxl.styles import Font, PatternFill

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cwn_compare.engine import run  # noqa: E402
from cwn_compare.options import Options  # noqa: E402
from cwn_compare.meta import read_meta_file  # noqa: E402

HEAD = ["ID", "DAYS", "TIME", "PL", "DESTINATION", "UNIT", "AM", "PM", "DIAG", None, "FROM",
        None, "INWARDS", "ID", "LOC"]


def T(id_, time, pl, dest, unit, pm, diag, dep, frm, inw, in_id, loc="S", am=""):
    return [id_, None, time, pl, dest, unit, am, pm, diag, dep, frm, "", inw, in_id, loc]


def U(unit, pm, diag, loc="S"):
    return [None, None, None, None, "", unit, "", pm, diag, "", "", "", "", "", loc]


def N(text, loc="S"):
    return [None, None, None, None, text, None, None, None, None, None, None, None, None, None, loc]


BTN_ORIG = [
    T("1A01BT", "05.23", "7", "Victoria", "(377/4", "XBI", "166)", "04+48", "Lovers Walk Depot", "05+07", "5A01BT"),
    U("(377/4", "XBI", "115)"),
    T("2C02BT", "05.42", "7", "Seaford", "377/3", "BTN", "311", "05+07", "Lovers Walk Depot", "05+27", "5C02BT"),
    T("1N04CT", "05.43", "1", "Southampton", "387/3", "LIT", "6", "", "Berth", "", ""),
    N("(via Littlehampton)"),
    T("2U08BT", "06.56", "7", "Eastbourne", "387/3", "EBOUSID", "23", "06+30", "Lovers Walk Depot", "06+50", "5U07BT"),
    T("1W07BT", "07.09", "6", "Victoria", "387/2", "VIC", "54", "06.00", "Victoria", "06.58", "1W08BT"),
    T("2C08BT", "07.11", "7", "Seaford", "377/3", "BTN", "311", "06.24", "Seaford", "07.00", "2C07BT"),
]
VIC_ORIG = [
    T("1W08BT", "06.00", "14", "Brighton", "387/2", "VIC", "54", "", "Berth", "", ""),
    T("1G06BT", "05.43", "13", "Gatwick Airport", "387/2", "XSL", "65", "03+55", "Stewarts Lane Depot", "04+13",
      "5D97BT"),
]


def make(path, btn, vic, order=("Cover", "BTN", "VIC"), bold_all=False):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name in order:
        ws = wb.create_sheet(name)
        if name == "Cover":
            ws["A1"] = "Test CWN"
            continue
        ws["A1"] = name
        ws.append(HEAD)
        for r in (btn if name == "BTN" else vic):
            ws.append(r)
        if bold_all:
            for row in ws.iter_rows(min_row=3):
                for c in row:
                    c.font = Font(bold=True)
                    c.fill = PatternFill("solid", fgColor="FFF5F5F5")
    wb.save(path)


def _upd_rows():
    btn = [list(r) for r in BTN_ORIG]
    btn[0][2] = "05.25"            # 1A01 retimed
    btn[2][3] = "8"                # 2C02 platform
    btn[5][5] = "377/4"            # 2U08 stock
    btn[6][13] = "1W10BT"          # 1W07 now formed from 1W10
    btn[6][9] = "06.10"
    del btn[7]                     # 2C08 cancelled
    btn.append(T("2C99BT", "08.00", "7", "Seaford", "377/3", "BTN", "311", "", "Berth", "", ""))  # new
    # swap row order of 2C02 and 1N04 block (should NOT be a change)
    btn = [btn[0], btn[1], btn[3], btn[4], btn[2]] + btn[5:]
    return btn, [list(r) for r in VIC_ORIG]


def test_all():
    d = tempfile.mkdtemp()
    o_p, u_p = os.path.join(d, "orig.xlsx"), os.path.join(d, "upd.xlsx")
    make(o_p, BTN_ORIG, VIC_ORIG)
    btn, vic = _upd_rows()
    make(u_p, btn, vic, order=("Cover", "VIC", "BTN"), bold_all=True)   # tab order + formatting only

    opts = Options(original=o_p, updated=u_p, output_dir=d, output_name="out")
    res = run(opts)
    meta = read_meta_file(res["cwn"])
    cats = sorted((c["category"], c["train"]) for c in meta["changes"])
    print(cats)
    assert ("TIME", "1A01BT") in cats
    assert ("PLATFORM", "2C02BT") in cats
    assert ("STOCK", "2U08BT") in cats
    assert ("FORMATION", "1W07BT") in cats
    assert ("CANCELLED", "2C08BT") in cats
    assert ("NEW", "2C99BT") in cats
    assert not any(t == "1N04CT" for _, t in cats), "re-ordered rows must not be changes"
    assert not any(c["sheet"] == "VIC" for c in meta["changes"]), "formatting-only tab must not change"

    wb = openpyxl.load_workbook(res["cwn"], rich_text=True)
    ws = wb["BTN"]
    assert ws.sheet_properties.tabColor.rgb.endswith("FFFF00")
    assert wb["VIC"].sheet_properties.tabColor is None
    vals = [[c.value for c in r] for r in ws.iter_rows(min_row=3)]
    struck = [r for r in ws.iter_rows(min_row=3) if r[0].font.strike]
    assert struck and struck[0][0].value == "2C08BT"
    assert any(isinstance(v, str) and v.startswith("Amended: previously formed from 1W08BT")
               for row in vals for v in row)
    t = ws.cell(row=3, column=3).value
    assert "05.23" in str(t) and "05.25" in str(t)

    # ACWN
    opts.output_type, opts.output_name = "acwn", "acwn"
    res2 = run(opts)
    wb2 = openpyxl.load_workbook(res2["cwn"])
    assert "VIC" not in wb2.sheetnames and "BTN" in wb2.sheetnames
    ids = [r[0].value for r in wb2["BTN"].iter_rows(min_row=3) if r[0].value]
    assert "1N04CT" not in ids and "1A01BT" in ids and "2C08BT" in ids

    # highlight-only and stripped categories
    opts.output_type, opts.output_name = "full", "hl"
    for k in opts.categories:
        opts.categories[k]["show_old"] = False
    opts.categories["PLATFORM"] = {"cwn": False, "show_old": False, "report": False}
    opts.categories["CANCELLED"]["cwn"] = False
    res3 = run(opts)
    ws3 = openpyxl.load_workbook(res3["cwn"], rich_text=True)["BTN"]
    assert not any(r[0].font.strike for r in ws3.iter_rows(min_row=3))
    assert ws3.cell(row=3, column=3).value == "05.25"
    assert ws3.cell(row=3, column=3).fill.fgColor.rgb.endswith("FFFF00")

    # cumulative round 2
    btn2 = [list(r) for r in btn]
    btn2[0][3] = "5"   # 1A01 platform change in round 2
    u2 = os.path.join(d, "upd2.xlsx")
    make(u2, btn2, vic)
    o4 = Options(mode="cumulative", original=res["cwn"], updated=u2, output_dir=d,
                 output_name="cum", colour="92D050")
    res4 = run(o4)
    assert res4["changes"] == 1 and res4["carried"] > 0
    ws4 = openpyxl.load_workbook(res4["cwn"], rich_text=True)["BTN"]
    assert ws4.cell(row=3, column=3).fill.fgColor.rgb.endswith("FFFF00")   # round 1 retime
    assert ws4.cell(row=3, column=4).fill.fgColor.rgb.endswith("92D050")   # round 2 platform
    assert ws4.sheet_properties.tabColor.rgb.endswith("92D050")
    meta4 = read_meta_file(res4["cwn"])
    assert [r["round"] for r in meta4["rounds"]] == [1, 2]
    assert os.path.exists(res4["report"])


def _run_pair(btn_o, btn_u, name, vic_o=None, vic_u=None, **kw):
    d = tempfile.mkdtemp()
    o_p, u_p = os.path.join(d, "o.xlsx"), os.path.join(d, "u.xlsx")
    make(o_p, btn_o, vic_o or VIC_ORIG)
    make(u_p, btn_u, vic_u or VIC_ORIG)
    opts = Options(original=o_p, updated=u_p, output_dir=d, output_name=name, **kw)
    res = run(opts)
    meta = read_meta_file(res["cwn"])
    return res, meta["changes"]


def test_copied_text_never_becomes_a_formula():
    """A CWN cell holding text such as '=cmd|...' stays text in the output, even on rows the writer moves."""
    import zipfile
    evil = "=cmd|' /C calc'!A0"
    o = [list(r) for r in BTN_ORIG]
    o[6][4] = evil                                  # 1W07BT's destination, after the cancelled 2C08BT
    u, _vic = _upd_rows()
    u = [r if r[0] != "1W07BT" else r[:4] + [evil] + r[5:] for r in u]
    d = tempfile.mkdtemp()
    paths = os.path.join(d, "o.xlsx"), os.path.join(d, "u.xlsx")
    for p, rows in zip(paths, (o, u)):
        make(p, rows, VIC_ORIG)
        wb = openpyxl.load_workbook(p)
        for row in wb["BTN"].iter_rows():
            for c in row:
                if c.value == evil:
                    c.data_type = "s"               # text in the CWN, as typed in Excel with a leading '
        wb.save(p)
    res = run(Options(original=paths[0], updated=paths[1], output_dir=d, output_name="formula"))
    with zipfile.ZipFile(res["cwn"]) as z:
        for name in z.namelist():
            if name.startswith("xl/worksheets/sheet"):
                assert b"<f>" not in z.read(name), name
    ws = openpyxl.load_workbook(res["cwn"])["BTN"]
    assert evil in [c.value for row in ws.iter_rows() for c in row]


def test_days_only_and_split_and_diag():
    o = [list(r) for r in BTN_ORIG]
    o[2][1] = "SX"                      # 2C02BT runs SX
    u = [list(r) for r in o]
    u[5][1] = "SO"                      # 2U08BT: days-only change
    u[6][8] = "99"                      # 1W07BT: diagram change only -> ignored
    # 2C02BT split into FSX (identical) and FO (platform differs)
    fsx = list(u[2]); fsx[1] = "FSX"
    fo = list(u[2]); fo[1] = "FO"; fo[3] = "9"
    u = u[:2] + [fsx, fo] + u[3:]
    res, changes = _run_pair(o, u, "split")
    got = sorted((c["category"], c["train"]) for c in changes)
    print(got)
    assert got == [("DAYS", "2U08BT (SO)"), ("PLATFORM", "2C02BT (FO)")], got
    days = [c for c in changes if c["category"] == "DAYS"][0]
    assert days["hide_old"] is True
    ws = openpyxl.load_workbook(res["cwn"], rich_text=True)["BTN"]
    row = next(r for r in ws.iter_rows(min_row=3) if r[0].value == "2U08BT")
    assert row[1].value == "SO" and row[1].fill.fgColor.rgb.endswith("FFFF00")   # highlighted, no old value
    fo_row = next(r for r in ws.iter_rows(min_row=3) if r[0].value == "2C02BT" and r[1].value == "FO")
    assert "9" in str(fo_row[3].value) and fo_row[3].fill.fgColor.rgb.endswith("FFFF00")
    fsx_row = next(r for r in ws.iter_rows(min_row=3) if r[0].value == "2C02BT" and r[1].value == "FSX")
    assert not any(c.fill.fgColor.rgb.endswith("FFFF00") for c in fsx_row)


def test_output_xml_is_clean():
    import zipfile
    u = [list(r) for r in BTN_ORIG]
    u[0][2] = "05.25"
    del u[7]
    res, _ = _run_pair(BTN_ORIG, u, "xml")
    with zipfile.ZipFile(res["cwn"]) as z:
        names = z.namelist()
        sheets = [z.read(n).decode() for n in names if n.startswith("xl/worksheets/")]
        styles = z.read("xl/styles.xml").decode()
        shared = z.read("xl/sharedStrings.xml").decode()
        workbook = z.read("xl/workbook.xml").decode()
    assert "fullCalcOnLoad" not in workbook
    assert "inlineStr" not in "".join(sheets), "text must use the shared-string table"
    xml = "".join(sheets)
    assert 't="inlineStr"/>' not in xml and 't="inlineStr"></c>' not in xml
    # the line break between old and new values must survive (xml:space="preserve")
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    space = "{http://www.w3.org/XML/1998/namespace}space"
    runs = [t for t in ET.fromstring(shared).iter(ns + "t")
            if (t.text or "").replace("\r", "").startswith("05.23\n")]
    assert runs and runs[0].get(space) == "preserve", "struck old time must carry the line break"
    assert "<font><name" not in styles   # font children written in schema order


def test_time_text():
    import datetime
    from cwn_compare.model import time_text
    assert time_text(datetime.time(5, 7), ecs=True) == "05+07"
    assert time_text(datetime.time(5, 7)) == "05.07"
    assert time_text(0.25) == "06.00"
    assert time_text("5.07") == "05.07"
    assert time_text("05+07") == "05+07"


def test_hyperlinks_follow_inserted_rows():
    d = tempfile.mkdtemp()
    o_p, u_p = os.path.join(d, "o.xlsx"), os.path.join(d, "u.xlsx")
    make(o_p, BTN_ORIG, VIC_ORIG)
    u = [list(r) for r in BTN_ORIG]
    del u[3:5]                          # 1N04CT cancelled -> re-inserted above 2U08BT
    make(u_p, u, VIC_ORIG)
    wb = openpyxl.load_workbook(u_p)
    target_row = next(r[0].row for r in wb["BTN"].iter_rows(min_row=3) if r[0].value == "1W07BT")
    wb["VIC"]["A3"].hyperlink = openpyxl.worksheet.hyperlink.Hyperlink(
        ref="A3", location=f"'BTN'!A{target_row}")
    wb.save(u_p)
    res = run(Options(original=o_p, updated=u_p, output_dir=d, output_name="links", keep_links=True))
    out = openpyxl.load_workbook(res["cwn"])
    loc = out["VIC"]["A3"].hyperlink.location
    r = int(loc.split("!A")[1])
    assert out["BTN"][f"A{r}"].value == "1W07BT", loc
    # default: links removed (much faster to open in Excel), text kept
    res = run(Options(original=o_p, updated=u_p, output_dir=d, output_name="nolinks"))
    out = openpyxl.load_workbook(res["cwn"])
    assert out["VIC"]["A3"].hyperlink is None and out["VIC"]["A3"].value == "1W08BT"


def _berth_rows(lines):
    """A berth block: inbound 5H61BT berthing two units with next-day working lines."""
    rows = [[None, None, None, "S1", lines[0][0], "(377/4", "", "", lines[0][1] + ")", "22+50",
             "Littlehampton", "", "23+02", "5H61BT", "S"]]
    for text, diag in lines[1:]:
        rows.append([None, None, None, None, text, "(377/4", "", "", diag + ")", "", "", "", "", "", "S"])
    return rows


def test_next_day_workings_and_day_codes():
    base = [list(r) for r in BTN_ORIG]
    base[2][1] = "ThFO"
    old = base + _berth_rows([("Berth BI150 06+10MO (2)", "146"), ("Berth BI149 06+10MO (1)", "147")])
    # same workings, units swapped between lines, lines re-ordered, day letters re-ordered
    same = [list(r) for r in BTN_ORIG]
    same[2][1] = "FThO"
    same += _berth_rows([("Berth BI149 06+10MO (1)", "146"), ("Berth BI150 06+10MO (2)", "147")])
    _res, changes = _run_pair(old, same, "nw-same")
    assert changes == [], [c["description"] for c in changes]
    # a real next-day working retime is reported
    moved = [list(r) for r in base] + _berth_rows([("Berth BI150 06+16MO (2)", "146"),
                                                  ("Berth BI149 06+10MO (1)", "147")])
    _res, changes = _run_pair(old, moved, "nw-moved")
    assert [(c["category"], c["old"], c["new"]) for c in changes] == [
        ("BERTHING", "Berth BI150 06+10MO (2)", "Berth BI150 06+16MO (2)")], changes


def test_days_variant_merge():
    o = [list(r) for r in BTN_ORIG]
    o[2][1] = "FSX"
    fo = list(o[2]); fo[1] = "FO"
    o = o[:3] + [fo] + o[3:]
    merged = [list(r) for r in BTN_ORIG]
    merged[2][1] = "SX"
    _res, changes = _run_pair(o, merged, "merge-same")      # identical FO merged into SX: no change
    assert changes == [], [c["description"] for c in changes]
    o2 = [list(r) for r in o]
    o2[3][2] = "05.50"                                         # FO variant ran at a different time
    _res, changes = _run_pair(o2, merged, "merge-diff")
    got = [(c["category"], c["train"], c["old"], c["new"]) for c in changes]
    assert got == [("TIME", "2C02BT (SX)", "05.50", "05.42")], got
    assert "FO variant" in changes[0]["description"]


def test_day_variants_reordered():
    """Day variants listed in a different order are matched variant-to-variant (MO with MO)."""
    mo = _berth_rows([("Berth BI150 06+10MO (2)", "146"), ("Berth BI149 06+10MO (1)", "147")])
    so = _berth_rows([("Berth BI150 08+56SO (2)", "146"), ("Berth BI149 08+56SO (1)", "147")])
    t_mx = list(BTN_ORIG[2]); t_mx[1] = "MX"
    t_mo = list(BTN_ORIG[2]); t_mo[1] = "MO"; t_mo[2] = "05.50"
    rest = [list(r) for r in BTN_ORIG[3:]]
    old = [list(r) for r in BTN_ORIG[:2]] + [t_mx, t_mo] + rest + mo + so
    new = [list(r) for r in BTN_ORIG[:2]] + [t_mo, t_mx] + rest + so + mo
    _res, changes = _run_pair(old, new, "variants-reordered")
    assert changes == [], [c["description"] for c in changes]
    # only the next-day day code differs -> not a change
    so_only_day = _berth_rows([("Berth BI150 08+56SuO (2)", "146"), ("Berth BI149 08+56SuO (1)", "147")])
    _res, changes = _run_pair(old, [list(r) for r in BTN_ORIG[:2]] + [t_mx, t_mo] + rest + mo + so_only_day,
                              "day-code-only")
    assert [c for c in changes if c["category"] == "BERTHING"] == [], [c["description"] for c in changes]
    # a real difference in one variant is reported against that variant only
    t_mo2 = list(t_mo); t_mo2[3] = "9"
    _res, changes = _run_pair(old, [list(r) for r in BTN_ORIG[:2]] + [t_mo2, t_mx] + rest + so + mo,
                              "variant-changed")
    assert [(c["category"], c["train"]) for c in changes] == [("PLATFORM", "2C02BT (MO)")], changes


def test_merged_variants_show_old_value_once():
    """Several variants (all platform 7) merged into one entry at platform 6: one change,
    and the old platform appears once in the cell - not once per variant."""
    rest = [list(r) for r in BTN_ORIG[3:]]
    variants = []
    for days in ("MO", "TO", "WO", "ThO"):
        v = list(BTN_ORIG[2]); v[1] = days; v[3] = "7"
        variants.append(v)
    old = [list(r) for r in BTN_ORIG[:2]] + variants + rest
    merged = list(BTN_ORIG[2]); merged[1] = "MTWThO"; merged[3] = "6"
    new = [list(r) for r in BTN_ORIG[:2]] + [merged] + rest
    res, changes = _run_pair(old, new, "merged-variants")
    plat = [c for c in changes if c["category"] == "PLATFORM"]
    assert len(plat) == 1, [c["description"] for c in changes]
    ws = openpyxl.load_workbook(res["cwn"], rich_text=True)["BTN"]
    cell = next(r[3] for r in ws.iter_rows(min_row=3) if r[0].value == "2C02BT")
    assert str(cell.value).replace("\n", "|") == "7|6", repr(str(cell.value))


def test_links_removed_before_formatting():
    """Link styling must not leak into struck-through rows or old/new rich-text values."""
    from openpyxl.styles import Font
    from openpyxl.worksheet.hyperlink import Hyperlink
    from openpyxl.cell.rich_text import CellRichText
    d = tempfile.mkdtemp()
    o_p, u_p = os.path.join(d, "o.xlsx"), os.path.join(d, "u.xlsx")
    make(o_p, BTN_ORIG, VIC_ORIG)
    u = [list(r) for r in BTN_ORIG]
    u[0][4] = "Brighton"                 # 1A01BT destination changed (a linked cell)
    del u[7]                             # 2C08BT cancelled
    make(u_p, u, VIC_ORIG)
    wb = openpyxl.load_workbook(u_p)
    for row in wb["BTN"].iter_rows(min_row=3):
        for c in (row[0], row[4]):       # headcode + destination styled as links
            if c.value:
                c.hyperlink = Hyperlink(ref=c.coordinate, location="'VIC'!A1")
                c.font = Font(name="Courier New", u="single", color="FF0000FF")
    wb.save(u_p)
    res = run(Options(original=o_p, updated=u_p, output_dir=d, output_name="out"))
    ws = openpyxl.load_workbook(res["cwn"], rich_text=True)["BTN"]
    for row in ws.iter_rows(min_row=3):
        for c in row:
            assert not c.font.u, (c.coordinate, c.value)
            if isinstance(c.value, CellRichText):
                assert not any(b.font.u for b in c.value), c.coordinate
    assert any(r[0].font.strike and r[0].value == "2C08BT" for r in ws.iter_rows(min_row=3))


def test_next_working_day_code_with_space():
    from cwn_compare.model import canon_next_working, next_working_days
    assert canon_next_working("Berth BI150 06+16 MO (2)") == canon_next_working("Berth BI150 06+16SO")
    assert canon_next_working("Berth BI150 06+16 Victoria") != canon_next_working("Berth BI150 06+16")
    assert next_working_days(["Berth X 06+16 MO", "SU305 05+32 Su (1)"]) == "MO Su"


def test_ignore_spacing_and_punctuation():
    """A note or destination that differs only in spacing / punctuation is not a change
    (unless exact text is asked for); a real wording change still is."""
    u = [list(r) for r in BTN_ORIG]
    u[4][4] = "( via  Littlehampton. )"          # note: spacing / punctuation only
    u[3][4] = "Southampton  Central"              # real destination change
    u[0][4] = "Victoria."                         # destination: punctuation only
    _res, changes = _run_pair(BTN_ORIG, u, "loose")
    got = sorted((c["category"], c["train"]) for c in changes)
    assert got == [("LOCATION", "1N04CT")], got
    _res, changes = _run_pair(BTN_ORIG, u, "exact", ignore_spacing=False)
    got = sorted((c["category"], c["train"]) for c in changes)
    assert ("NOTES", "1N04CT") in got and ("LOCATION", "1A01BT") in got, got


def test_change_report_as_pdf_and_word():
    u = [list(r) for r in BTN_ORIG]
    u[0][2] = "05.30"                                      # one time change
    for fmt in ("pdf", "docx"):
        res, changes = _run_pair(BTN_ORIG, u, f"doc_{fmt}", report_format=fmt)
        assert res["report"].endswith("." + fmt) and os.path.getsize(res["report"]) > 1000, res
        assert res["cwn"].endswith(".xlsx")


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("all tests passed")


def test_day_filter():
    """Only the trains running on the chosen days are checked and written; days not in the CWN are known."""
    from cwn_compare.days import coverage, code_days, parse_day_list
    from cwn_compare.engine import load_model
    o = [list(r) for r in BTN_ORIG]
    o[2][1] = "FO"                        # 2C02BT runs Fridays only
    o[5][1] = "MO"                        # 2U08BT Mondays only
    u = [list(r) for r in o]
    u[2][3] = "8"                         # Friday train: platform change
    u[5][3] = "9"                         # Monday train: platform change
    u[6][1] = "FX"                        # 1W07BT no longer runs on Fridays
    res, changes = _run_pair(o, u, "fri", days=[4])
    got = sorted((c["category"], c["train"]) for c in changes)
    assert ("PLATFORM", "2C02BT (FO)") in got
    assert not any("2U08BT" in t for _c, t in got)                    # the Monday train is not checked
    assert ("DAYS", "1W07BT") in got and not any(c == "CANCELLED" for c, _t in got)
    wb = openpyxl.load_workbook(res["cwn"])
    ids = [r[0] for r in wb["BTN"].iter_rows(min_row=3, values_only=True) if r[0]]
    assert "2U08BT" not in ids and "2C02BT" in ids                     # output holds Friday trains only
    d = tempfile.mkdtemp()
    make(os.path.join(d, "x.xlsx"), o, VIC_ORIG)
    base, assumed = coverage(load_model(os.path.join(d, "x.xlsx")), os.path.join(d, "x.xlsx"))
    assert base == {0, 1, 2, 3, 4} and assumed                         # weekday codes, no wording
    make(os.path.join(d, "BTN SO.xlsx"), BTN_ORIG, VIC_ORIG)
    assert coverage(load_model(os.path.join(d, "BTN SO.xlsx")), os.path.join(d, "BTN SO.xlsx")) == ({5}, False)
    assert code_days("MX", {0, 1, 2, 3, 4}) == {1, 2, 3, 4} and parse_day_list("FO") == {4}


def test_notes_beside_changes_and_text_only_highlight():
    """Amendment notes sit in a 'Change notes' column beside the change; only cells with text are coloured."""
    btn, vic = _upd_rows()
    res, _changes = _run_pair(BTN_ORIG, btn, "notes", vic_o=VIC_ORIG, vic_u=vic)
    ws = openpyxl.load_workbook(res["cwn"])["BTN"]
    head = [c.value for c in ws[2]]
    col = head.index("Change notes") + 1
    rows = {r[0].value: r for r in ws.iter_rows(min_row=3) if r[0].value}
    assert "previously formed from 1W08BT" in rows["1W07BT"][col - 1].value       # beside the train
    assert all(r[0].value is not None or not any("Amended" in str(c.value or "") for c in r)
               for r in ws.iter_rows(min_row=3))                                  # no note rows underneath
    for train in ("2C99BT", "2C08BT"):                                           # new / re-inserted trains
        for cell in rows[train][:15]:
            solid = cell.fill is not None and cell.fill.fill_type == "solid"
            assert solid == (cell.value not in (None, "")), (train, cell.coordinate)


def test_change_report_layout():
    """One round: no round columns; Details only adds what the other columns don't say; one
    'New and Cancelled Trains' sheet."""
    btn, vic = _upd_rows()
    res, _changes = _run_pair(BTN_ORIG, btn, "rep", vic_o=VIC_ORIG, vic_u=vic)
    wb = openpyxl.load_workbook(res["report"])
    assert wb.sheetnames == ["Summary", "All Changes", "Changes by Train", "New and Cancelled Trains"]
    ws = wb["All Changes"]
    assert [c.value for c in ws[1]] == ["Tab", "Train", "Category", "Field", "Was", "Now", "Details"]
    rows = {(r[1], r[3]): r for r in ws.iter_rows(min_row=2, values_only=True)}
    assert rows[("1A01BT", "Time")][6] in (None, "")                    # 'Time changed from ...' adds nothing
    assert "formed from 1W10BT" in rows[("1W07BT", "Inward headcode")][6]
    nc = [r for r in wb["New and Cancelled Trains"].iter_rows(min_row=2, values_only=True)]
    assert [(r[0], r[1]) for r in nc] == [("Cancelled", "2C08BT"), ("New", "2C99BT")]


def make_multi_day(path):
    """A CWN whose 2C02BT has FO (05.30), TWThO and MO variants listed in that order (also used by the
    Windows build's smoke test)."""
    rows = [list(r) for r in BTN_ORIG]
    fo, tw, mo = list(rows[2]), list(rows[2]), list(rows[2])
    fo[1], fo[2], fo[3] = "FO", "05.30", "9"
    tw[1], tw[3] = "TWThO", "8"
    mo[1], mo[3] = "MO", "7"
    make(path, [rows[0], rows[1], fo, tw, mo, U("377/3", "BTN", "312")] + rows[3:], VIC_ORIG)


def test_reorder_day_variants():
    """Each train's day variants are put in day order (or time order) without changing or losing anything,
    and links from other tabs follow the rows."""
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    src = os.path.join(d, "multi.xlsx")
    make_multi_day(src)
    wb = openpyxl.load_workbook(src)
    from openpyxl.worksheet.hyperlink import Hyperlink
    wb["VIC"]["A3"].hyperlink = Hyperlink(ref="A3", location="'BTN'!A7")   # links to the MO variant's row
    wb.save(src)
    res = reorder_cwn(src, d)
    out = openpyxl.load_workbook(res["path"])
    got = [(r[0], r[1], r[3]) for r in out["BTN"].iter_rows(min_row=3, values_only=True) if r[0] == "2C02BT"]
    assert got == [("2C02BT", "MO", "7"), ("2C02BT", "TWThO", "8"), ("2C02BT", "FO", "9")]
    assert out["BTN"]["F6"].value == "377/3" and out["BTN"]["I6"].value == "312"     # unit row moved with MO
    assert out["VIC"]["A3"].hyperlink.location == "'BTN'!A5"                         # link follows the row
    before = sorted(map(str, openpyxl.load_workbook(src)["BTN"].iter_rows(values_only=True)))
    assert before == sorted(map(str, out["BTN"].iter_rows(values_only=True)))         # nothing changed or lost
    by_time = reorder_cwn(src, d, by_time=True)
    got = [r[1] for r in openpyxl.load_workbook(by_time["path"])["BTN"].iter_rows(min_row=3, values_only=True)
           if r[0] == "2C02BT"]
    assert got == ["FO", "MO", "TWThO"]
    assert res["trains"] == 1 and openpyxl.load_workbook(src)["BTN"]["B5"].value == "FO"   # original untouched


def test_reorder_keeps_reused_headcodes_apart():
    """The same headcode used for two trains on a tab (morning and evening) is two trains: each one's
    variants are ordered among themselves and never swapped with the other train's."""
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    rows = [list(r) for r in BTN_ORIG]
    def v(days, time, unit):
        r = list(rows[2]); r[1], r[2], r[3] = days, time, unit; return r
    btn = [rows[0], rows[1], v("FO", "06.00", "1"), v("MTWThO", "06.05", "2"),
           v("FO", "18.00", "3"), v("MTWThO", "18.10", "4")] + rows[3:]
    src = os.path.join(d, "reused.xlsx")
    make(src, btn, VIC_ORIG)
    out = openpyxl.load_workbook(reorder_cwn(src, d)["path"])
    got = [(r[1], r[2]) for r in out["BTN"].iter_rows(min_row=3, values_only=True) if r[0] == "2C02BT"]
    assert got == [("MTWThO", "06.05"), ("FO", "06.00"), ("MTWThO", "18.10"), ("FO", "18.00")]


def test_reorder_already_in_order_saves_nothing():
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    src = os.path.join(d, "plain.xlsx")
    make(src, BTN_ORIG, VIC_ORIG)
    res = reorder_cwn(src, d)
    assert res["path"] == "" and res["trains"] == 0 and os.listdir(d) == ["plain.xlsx"]


def test_single_day_cwn_against_day_coded_cwn():
    """A CWN with no days column filled in (a single-day CWN) compared with one whose trains carry a day
    code ('WO') is not a days change on every train."""
    o = [list(r) for r in BTN_ORIG]
    for r in o:
        r[1] = ""
    u = [list(r) for r in BTN_ORIG]
    for r in u:
        r[1] = "WO"
    u[0][3] = "9"
    _res, changes = _run_pair(o, u, "single")
    assert {c["category"] for c in changes} == {"PLATFORM"}, changes


def test_next_day_workings_paired_by_unit_position():
    """Changed next-day workings pair with the same unit position, and lines for different positions are an
    addition and a removal - never one unrelated 'changed from' pair."""
    old = [list(r) for r in BTN_ORIG] + _berth_rows([("Berth BI150 06+10MO (2)", "146"),
                                                     ("Berth BI149 06+10MO (1)", "147")])
    both = [list(r) for r in BTN_ORIG] + _berth_rows([("Berth SU305 05+32MO (1)", "147"),
                                                      ("Berth LB12 07+00MO (2)", "146")])
    _res, changes = _run_pair(old, both, "nw-both")
    assert sorted((c["old"], c["new"]) for c in changes) == [
        ("Berth BI149 06+10MO (1)", "Berth SU305 05+32MO (1)"),
        ("Berth BI150 06+10MO (2)", "Berth LB12 07+00MO (2)")], changes
    other = [list(r) for r in BTN_ORIG] + _berth_rows([("Berth BI149 06+10MO (1)", "147"),
                                                       ("Berth XX9 09+00MO (3)", "149")])
    _res, changes = _run_pair(old, other, "nw-other")
    descs = sorted(c["description"] for c in changes if c["category"] == "BERTHING")
    assert len(descs) == 2 and "added - Berth XX9" in descs[0] and "removed - Berth BI150" in descs[1], descs


def _berth_changes(old_lines, new_lines, name):
    old = [list(r) for r in BTN_ORIG] + _berth_rows(old_lines)
    new = [list(r) for r in BTN_ORIG] + _berth_rows(new_lines)
    _res, changes = _run_pair(old, new, name)
    return sorted((c["kind"] if "kind" in c else "", c["old"], c["new"]) for c in changes
                  if c["category"] == "BERTHING")


def test_next_day_leftovers_are_never_guessed():
    """After matching by road and unit position, a leftover pair is joined only when it cannot be a guess."""
    # one unit's stabling moves (same position) while the other unit's working is dropped
    got = _berth_changes([("Berth BI149 06+10MO (1)", "147"), ("Berth BI150 06+10MO (2)", "146")],
                         [("Berth SU305 05+32MO (1)", "147")], "nw-move-drop")
    assert [(o, n) for _k, o, n in got] == [("Berth BI149 06+10MO (1)", "Berth SU305 05+32MO (1)"),
                                            ("Berth BI150 06+10MO (2)", "")], got
    # a positioned line removed and an unrelated line without a position added: two changes, not one
    got = _berth_changes([("Berth BI150 06+10MO (2)", "146"), ("Berth BI149 06+10MO (1)", "147")],
                         [("Berth BI149 06+10MO (1)", "147"), ("Berth XX9 09+00MO", "149")], "nw-mixed")
    assert sorted((o, n) for _k, o, n in got) == [("", "Berth XX9 09+00MO"), ("Berth BI150 06+10MO (2)", "")]
    # two lines without positions both change: which became which is unknown, so removed + added
    got = _berth_changes([("Berth AA1 06+10MO", "146"), ("Berth BB2 07+10MO", "147")],
                         [("Berth CC3 05+00MO", "146"), ("Berth DD4 08+00MO", "147")], "nw-two")
    assert all(not (o and n) for _k, o, n in got) and len(got) == 4, got
    # a single unit's only line changing is still one change
    got = _berth_changes([("Berth AA1 06+10MO", "146")], [("Berth CC3 05+00MO", "146")], "nw-one")
    assert [(o, n) for _k, o, n in got] == [("Berth AA1 06+10MO", "Berth CC3 05+00MO")]


def test_damaged_tab_is_left_out_of_both_sides():
    """A tab that cannot be read in the original CWN (damaged file) is left out of the updated one too, so its
    trains are not reported as changed, and the run says so."""
    import zipfile
    d = tempfile.mkdtemp()
    good, bad = os.path.join(d, "good.xlsx"), os.path.join(d, "bad.xlsx")
    b, v = _upd_rows()
    make(good, b, v)
    with zipfile.ZipFile(good) as zi, zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zo:
        sheets = sorted(n for n in zi.namelist() if n.startswith("xl/worksheets/sheet"))
        for it in zi.infolist():
            data = zi.read(it.filename)
            zo.writestr(it.filename, data[:len(data) // 2] if it.filename == sheets[0] else data)
    logs = []
    res = run(Options(original=bad, updated=good, output_dir=d, output_name="x"), log=logs.append)
    assert read_meta_file(res["cwn"])["changes"] == []
    assert any("left out of the comparison" in m for m in logs)


def test_reorder_first_day_decides():
    """The first day a variant runs decides its place (MWO before ThFO, whatever their times); variants are
    still put in order when they run hours apart or either side of midnight."""
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    rows = [list(r) for r in BTN_ORIG]

    def v(days, time, unit):
        r = list(rows[2]); r[1], r[2], r[3] = days, time, unit; return r
    cases = {
        "far": ([v("ThFO", "05.42", "1"), v("TO", "05.40", "2"), v("MWO", "10.30", "3")], ["MWO", "TO", "ThFO"]),
        "midnight": ([v("ThFO", "23.50", "1"), v("MWO", "00.10", "2")], ["MWO", "ThFO"]),
    }
    for name, (variants, want) in cases.items():
        src = os.path.join(d, name + ".xlsx")
        make(src, [rows[0], rows[1]] + variants + rows[3:], VIC_ORIG)
        out = openpyxl.load_workbook(reorder_cwn(src, d)["path"])
        got = [r[1] for r in out["BTN"].iter_rows(min_row=3, values_only=True) if r[0] == "2C02BT"]
        assert got == want, (name, got)


def test_reorder_merges_variants_the_same_apart_from_days():
    """With merging on, variants of a train that are the same on a tab apart from their days become one with
    both days; its rows replace theirs, the rows below move up and links follow."""
    from openpyxl.worksheet.hyperlink import Hyperlink
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    rows = [list(r) for r in BTN_ORIG]

    def v(days, pl):
        r = list(rows[2]); r[1], r[3] = days, pl; return r
    unit = U("377/3", "BTN", "312")
    btn = [rows[0], rows[1], v("FO", "7"), unit, v("TWThO", "8"), v("MO", "7"), unit] + rows[3:]
    src = os.path.join(d, "merge.xlsx")
    make(src, btn, VIC_ORIG)
    wb = openpyxl.load_workbook(src)
    wb["VIC"]["A3"].hyperlink = Hyperlink(ref="A3", location="'BTN'!A8")        # the MO variant (merged away)
    wb["VIC"]["A4"].hyperlink = Hyperlink(ref="A4", location="'BTN'!A14")       # 2C08BT, below it
    wb.save(src)
    assert openpyxl.load_workbook(src)["BTN"]["A14"].value == "2C08BT"
    plain = reorder_cwn(src, d)
    assert plain["merged"] == 0 and "merged" not in os.path.basename(plain["path"])
    res = reorder_cwn(src, d, merge=True)
    assert res["merged"] == 1 and res["path"].endswith("(variants in day order, merged).xlsx")
    out = openpyxl.load_workbook(res["path"])["BTN"]
    got = [(r[1], r[3]) for r in out.iter_rows(min_row=3, values_only=True) if r[0] == "2C02BT"]
    assert got == [("MFO", "7"), ("TWThO", "8")]
    data = [r for r in out.iter_rows(min_row=3, values_only=True) if any(x not in (None, "") for x in r)]
    assert len(data) == len(btn) - 2                                         # the MO variant's two rows gone
    assert [r[0] for r in data][-1] == "2C08BT" and out["A12"].value == "2C08BT"
    assert all(out.cell(row=r, column=1).value is None for r in (13, 14))   # freed rows at the bottom cleared
    vic = openpyxl.load_workbook(res["path"])["VIC"]
    assert vic["A3"].hyperlink.location == "'BTN'!A5"                        # now the merged MFO row
    assert vic["A4"].hyperlink.location == "'BTN'!A12"                       # moved up two rows


def test_merged_days_code():
    from cwn_compare.reorder import days_code
    wk = set(range(5))
    assert days_code({0, 4}, wk) == "MFO"
    assert days_code({3, 4}, wk) == "ThFO"
    assert days_code(set(range(5)), wk) == ""                                 # every day the CWN covers
    assert days_code({0, 1, 2, 3}, wk) == "FX"
    assert days_code({0, 1, 2, 3}, wk, sx_style=True) == "FSX"                # as the CWN writes it
    assert days_code({0, 1, 2, 3, 4}, set(range(7))) == "SSuX"
    assert days_code({5}, set(range(7))) == "SO"


def test_highlighted_only_output():
    """'Full CWN with new or changed items highlighted only': the updated CWN with what is new or changed
    highlighted - no previous values, change notes or cancelled trains - whatever the per-type settings; the
    change report still lists everything."""
    btn, vic = _upd_rows()
    res, changes = _run_pair(BTN_ORIG, btn, "hl", vic_u=vic, output_type="highlight")
    wb = openpyxl.load_workbook(res["cwn"], rich_text=True)
    ws = wb["BTN"]
    vals = [[c.value for c in r] for r in ws.iter_rows(min_row=1)]
    flat = [str(v) for row in vals for v in row if v is not None]
    assert ws.cell(row=3, column=3).value == "05.25"                       # new time only, not '05.23'
    assert not any(r[0].font.strike for r in ws.iter_rows(min_row=3))
    assert "2C08BT" not in flat                                             # cancelled train not put back
    assert not any("previously" in v or v == "Change notes" for v in flat)
    fill = ws.cell(row=3, column=3).fill
    assert fill.fill_type == "solid" and fill.fgColor.rgb.endswith("FFFF00")      # the change is highlighted
    new = next(r for r in ws.iter_rows(min_row=3) if r[0].value == "2C99BT")
    assert new[0].fill.fill_type == "solid"
    assert {c["category"] for c in changes} >= {"TIME", "CANCELLED", "NEW", "FORMATION"}
    rep = openpyxl.load_workbook(res["report"])
    assert ("Output format", "Full CWN (new and changed items highlighted only)") in [
        tuple(r[:2]) for r in rep["Summary"].iter_rows(values_only=True)]
    nc = [r[:2] for r in rep["New and Cancelled Trains"].iter_rows(min_row=2, values_only=True)]
    assert ("Cancelled", "2C08BT") in nc


def _berths(variants):
    """Berth entries for 1T66HS like a terminus tab: (days, first unit's berth line, second unit's berth line)."""
    out = []
    for days, nw1, nw2 in variants:
        out += [["", days, "", "1", nw1, "(379/0", "", "", "319)", "21.48", "Kings Cross", "", "23.38", "1T66HS",
                 "S"],
                [None, None, None, None, nw2, "(379/0", "", "", "318)", "", "", "", "", "", "S"],
                N("DETACH REQUIRED")]
    return out


def _merged(rules, variants, extra=()):
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    rows = [list(r) for r in BTN_ORIG]
    src = os.path.join(d, "b.xlsx")
    make(src, rows[:2] + _berths(variants) + list(extra) + rows[2:], VIC_ORIG)
    res = reorder_cwn(src, d, merge=True, rules=rules)
    if not res["path"]:
        return res, None
    return res, openpyxl.load_workbook(res["path"], rich_text=True)["BTN"]


def _text(v):
    from openpyxl.cell.rich_text import CellRichText
    if isinstance(v, CellRichText):
        return [(str(b.text), b.font.sz < 10) if hasattr(b, "font") else (str(b), False) for b in v]
    return v


def test_merge_berths_for_the_same_next_working():
    """Variants that berth for the same next working each day merge, the berth lines' day codes combined; a
    berth for another working stays separate; without the option nothing merges."""
    from cwn_compare.reorder import MergeRules
    week = [("MO", "Berth HE317 05.17TO", "Berth HE316 04.49TO"),
            ("TO", "Berth HE317 05.17WO", "Berth HE316 04.49WO"),
            ("WO", "Berth HE317 05.17ThO", "Berth HE316 04.49ThO"),
            ("ThO", "Berth HE317 05.17FO", "Berth HE316 04.49FO"),
            ("FO", "Berth HE317 04.49SO (2)", "Berth HE316 04.49SO (1)")]
    res, _ws = _merged(MergeRules(), week)
    assert res["merged"] == 0
    res, ws = _merged(MergeRules(berths=True), week)
    assert res["merged"] == 3
    got = [(r[1], r[4]) for r in ws.iter_rows(min_row=3, values_only=True) if r[13] == "1T66HS"]
    assert got == [("FX", "Berth HE317 05.17TWThFO"), ("FO", "Berth HE317 04.49SO (2)")]
    assert ws["E6"].value == "Berth HE316 04.49TWThFO" and ws["E7"].value == "DETACH REQUIRED"


def test_merge_berths_with_a_different_next_day_diagram():
    """Berthing for the same next working on a different diagram: merged only with that option, both diagram
    numbers shown with their (next-day) days in small type."""
    from cwn_compare.reorder import MergeRules
    week = [("MO", "Berth HE317 05.17TO", "Berth HE316 04.49TO"),
            ("TO", "Berth HE318 05.17WO", "Berth HE316 04.49WO"),
            ("WO", "Berth HE317 05.17ThO", "Berth HE316 04.49ThO"),
            ("ThO", "Berth HE317 05.17FO", "Berth HE316 04.49FO")]
    res, ws = _merged(MergeRules(berths=True), week)
    got = [(r[1], r[4]) for r in ws.iter_rows(min_row=3, values_only=True) if r[13] == "1T66HS"]
    assert got == [("TFX", "Berth HE317 05.17TThFO"), ("TO", "Berth HE318 05.17WO")]
    res, ws = _merged(MergeRules(berths=True, berth_diagrams=True), week)
    assert res["merged"] == 3
    rows = [r for r in ws.iter_rows(min_row=3) if r[13].value == "1T66HS"]
    assert len(rows) == 1 and rows[0][1].value == "FX"                         # MTWThO in a weekday CWN
    assert rows[0][4].value == "Berth HE317 \u25be 05.17TWThFO"               # the diagram for most days, marked
    assert _dv(ws, rows[0][4].coordinate) == ("Next working varies by day", "TThFO: HE317\nWO: HE318",
                                              '"HE317 (TThFO),HE318 (WO)"')


def test_merge_when_only_diagram_numbers_differ():
    """Variants differing only in their diagram numbers merge with that option: the DIAG cell shows each with
    its days in small type, brackets kept."""
    from cwn_compare.reorder import MergeRules
    rows = [list(r) for r in BTN_ORIG]

    def v(days, diag):
        r = list(rows[2]); r[1], r[8] = days, diag; return r
    extra = [v("MO", "311"), v("TWThO", "319"), v("FO", "312")]
    res, _ws = _merged(MergeRules(berths=True), [], extra)
    assert res["path"] == "" or res["merged"] == 0
    res, ws = _merged(MergeRules(diagrams=True), [], extra)
    assert res["merged"] == 2
    got = [r for r in ws.iter_rows(min_row=3) if r[0].value == "2C02BT"]
    assert len(got) == 2                                                     # the original 2C02BT and the merged one
    merged = next(r for r in got if r[1].value is None and "\u25be" in str(r[8].value))
    assert merged[8].value == "319 \u25be"                                    # TWThO: the most days
    assert merged[8].font.color.rgb == "FF00707A"
    assert _dv(ws, merged[8].coordinate) == ("Diagram varies by day", "MO: 311\nTWThO: 319\nFO: 312",
                                             '"311 (MO),319 (TWThO),312 (FO)"')


def _dv(ws, coord):
    """(title, prompt, list) of the click-to-show box on a cell, or None."""
    for dv in ws.data_validations.dataValidation:
        if coord in dv.sqref:
            assert dv.showInputMessage and not dv.showErrorMessage
            return dv.promptTitle, dv.prompt, dv.formula1
    return None


def test_merge_when_only_am_pm_berths_differ():
    """AM / PM berths say where the unit starts and ends its day, not anything about this location: variants
    differing only there merge with no option ticked; the PM cell shows the berth for most days, marked, and
    lists each day's berth when clicked. The longer DAYS code widens its column."""
    from cwn_compare.reorder import MergeRules
    rows = [list(r) for r in BTN_ORIG]

    def v(days, pm):
        r = list(rows[2]); r[1], r[7] = days, pm; return r
    extra = [v("MO", "THBDTGS"), v("ThO", "EBOUSID")]
    res, ws = _merged(MergeRules(), [], extra)
    assert res["merged"] == 1
    got = [r for r in ws.iter_rows(min_row=3) if r[0].value == "2C02BT" and r[1].value]
    assert len(got) == 1 and got[0][1].value == "MThO" and got[0][7].value == "THBDTGS \u25be"
    assert _dv(ws, got[0][7].coordinate)[1] == "MO: THBDTGS\nThO: EBOUSID"


def test_fit_column_widens_only():
    from cwn_compare.xlsxfix import fit_column
    ws = openpyxl.Workbook().active
    ws.column_dimensions["B"].width = 4
    ws["B2"] = "MTWThO"
    fit_column(ws, 2, [ws["B2"]])
    assert ws.column_dimensions["B"].width > 5
    w = ws.column_dimensions["B"].width
    ws["B3"] = "MO"
    fit_column(ws, 2, [ws["B3"]])
    assert ws.column_dimensions["B"].width == w


def test_variants_with_another_formation_stay_apart_and_say_why():
    from cwn_compare.reorder import MergeRules
    rows = [list(r) for r in BTN_ORIG]

    def v(days):
        r = list(rows[2]); r[1] = days; return r
    extra = [v("MO"), U("(377/3", "BTN", "312)"), v("TO")]
    res, _ws = _merged(MergeRules(diagrams=True), [], extra)
    assert res["merged"] == 0
    assert any("2C02BT (TO) kept apart from 2C02BT (MO)" in a and "2 rows" in a for a in res["apart"])


def test_reorder_comparison_cwn():
    """A comparison CWN made by the app can be put in order: struck-through previous values, highlights and the
    hidden comparison data move with it; a highlighted variant is never merged with one that is not."""
    from cwn_compare.reorder import reorder_cwn
    rows = [list(r) for r in BTN_ORIG]

    def v(days, pl, time="05.42"):
        r = list(rows[2]); r[1], r[2], r[3] = days, time, pl; return r
    old = rows[:2] + [v("FO", "7"), v("MO", "7"), v("TO", "7")] + rows[3:]
    new = rows[:2] + [v("FO", "7"), v("MO", "7", "05.44"), v("TO", "7")] + rows[3:]
    res, _changes = _run_pair(old, new, "cmp-reorder")
    d = os.path.dirname(res["cwn"])
    out = reorder_cwn(res["cwn"], d, merge=True)
    assert out["path"]
    ws = openpyxl.load_workbook(out["path"], rich_text=True)["BTN"]
    got = [(r[1].value, r[2].value) for r in ws.iter_rows(min_row=3) if r[0].value == "2C02BT"]
    assert [g[0] for g in got] == ["MO", "TFO"]                               # MO (changed) first; TO + FO merged
    assert "05.42" in str(got[0][1]) and "05.44" in str(got[0][1])            # old time still struck above new
    assert read_meta_file(out["path"]) is not None


def _sheet_xml(path, title):
    import re
    import zipfile
    with zipfile.ZipFile(path) as z:
        wbx = z.read("xl/workbook.xml").decode()
        rels = z.read("xl/_rels/workbook.xml.rels").decode()
        rid = re.search(rf'<sheet [^>]*name="{title}"[^>]*r:id="(\w+)"', wbx).group(1)
        target = re.search(rf'Id="{rid}"[^>]*Target="([^"]+)"|Target="([^"]+)"[^>]*Id="{rid}"', rels)
        target = target.group(1) or target.group(2)
        return z.read("xl/" + target.lstrip("/").replace("xl/", "")).decode()


def test_no_unused_formatting_in_outputs():
    """A CWN whose formatting runs on to the last column and far below its trains (common in real CWNs): the
    comparison CWN, the change report and the reordered copy carry no formatting past their data."""
    import re
    from openpyxl.styles import Border, Side
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    rows = [list(r) for r in BTN_ORIG]
    btn = rows[:3] + [[*rows[2][:1], "MO", *rows[2][2:]]] + rows[3:]
    btn[2][1] = "FO"
    for name, data in (("o", rows), ("u", btn)):
        make(os.path.join(d, name + ".xlsx"), data, VIC_ORIG)
        wb = openpyxl.load_workbook(os.path.join(d, name + ".xlsx"))
        for ws in wb.worksheets:
            thin = Side(style="thin")
            for r in range(1, 3000, 7):                       # styled empty cells far below and to the right
                ws.cell(row=r, column=200).font = Font(bold=True)
                ws.cell(row=r, column=3).border = Border(top=thin)
            ws.column_dimensions.group("P", "XFD")
            ws.column_dimensions["P"].font = Font(italic=True)
            ws.row_dimensions[2500].font = Font(bold=True)
        wb.save(os.path.join(d, name + ".xlsx"))
    o = Options(original=os.path.join(d, "o.xlsx"), updated=os.path.join(d, "u.xlsx"), output_dir=d,
                output_name="trim")
    res = run(o)
    ro = reorder_cwn(os.path.join(d, "u.xlsx"), d)
    for path in (res["cwn"], res["report"], ro["path"]):
        wb = openpyxl.load_workbook(path)
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                continue
            xml = _sheet_xml(path, ws.title)
            ref = re.search(r'<dimension ref="([^"]+)"', xml).group(1)
            last = max((c.row for row in ws.iter_rows() for c in row if c.value not in (None, "")), default=1)
            assert int(re.sub(r"[A-Z]+", "", ref.split(":")[-1])) <= last + 1, (path, ws.title, ref, last)
            assert "XFD" not in xml and 'max="16384"' not in xml and ' customFormat="1"' not in xml, (path, ws.title)
