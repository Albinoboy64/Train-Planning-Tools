"""Output audit: every kind of output the app writes, made from synthetic inputs (some holding text that looks like a
formula), checked for what would make the file wrong or unsafe to open:

* the file is a valid workbook (its zip and XML parts read back);
* no cell is a live formula (text starting =, +, - or @ stays text);
* no control characters in any cell;
* links inside the workbook point at sheets that exist;
* no output overwrote another (each run makes a new file).
"""
import os
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def check_workbook(path: str):
    import openpyxl
    assert os.path.getsize(path) > 0, path
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, f"{path}: damaged part"
        for name in z.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                import xml.etree.ElementTree as ET
                ET.fromstring(z.read(name))                     # every XML part parses
    wb = openpyxl.load_workbook(path)
    sheets = set(wb.sheetnames)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                assert c.data_type != "f", f"{path} {ws.title}!{c.coordinate}: live formula {c.value!r}"
                if isinstance(c.value, str):
                    assert not _CONTROL.search(c.value), f"{path} {ws.title}!{c.coordinate}: control character"
                link = c.hyperlink
                if link is not None and link.location:
                    target = link.location.split("!")[0].strip("'")
                    assert target in sheets, f"{path} {ws.title}!{c.coordinate}: link to missing sheet {target}"
    return wb


def test_every_output_is_valid_and_safe(monkeypatch):
    import openpyxl
    import test_berthing as tb
    import test_compare as tc
    import test_stationbook as tsb
    import test_statspack as ts
    import test_timetable as tt
    d = tempfile.mkdtemp()
    monkeypatch.setenv("LOCALAPPDATA", os.path.join(d, "appdata"))
    outputs = []

    # CWN comparison, with formula-like and control-character text in the updated CWN
    from cwn_compare.engine import run as cwn_run
    from cwn_compare.options import Options
    o_p, u_p = os.path.join(d, "orig.xlsx"), os.path.join(d, "upd.xlsx")
    tc.make(o_p, tc.BTN_ORIG, tc.VIC_ORIG)
    btn, vic = tc._upd_rows()
    btn = [list(r) for r in btn]
    btn[0][4] = "=HYPERLINK(\"http://x\")"
    btn[1][4] = "-Brighton via Lewes"
    tc.make(u_p, btn, vic)
    res = cwn_run(Options(original=o_p, updated=u_p, output_dir=d, output_name="audit"))
    outputs += [v for v in res.values() if isinstance(v, str) and v.endswith(".xlsx")]

    # day variants in order
    from cwn_compare.reorder import reorder_cwn
    multi = os.path.join(d, "multi.xlsx")
    tc.make_multi_day(multi)
    outputs.append(reorder_cwn(multi, d)["path"])

    # station book (with another operator merged in)
    from rstools import stationbook as SB
    x1, x2 = os.path.join(d, "sb.xml"), os.path.join(d, "sb2.xml")
    tsb.write_late_xml(x1)
    tsb.write_late_xml(x2, operator="XC")
    outputs.append(SB.make_book(x1, "Alpha", d, operator="GTR(TLGN)", day_types=["SX"], merge_xml=[x2])[0])

    # stats pack, its comparison and unit reports
    from rstools.statspack.engine import build_pack, unit_reports, write_pack
    plan = ts.setup_plan(d)
    outputs += write_pack(build_pack(plan, ts.opts(d, [0, 1]), "test")[0], ts.opts(d, [0, 1], output_name="sp"),
                          plan, "test")
    outputs += unit_reports(plan, ts.opts(d, [0, 1]), ["washes", "depots", "captive"], True)[0]

    # timing tools: documents, prints, lists, timetables
    from rstools.timetable.engine import run as tt_run
    f = tt.write_rule_docs(d)
    outputs.append(tt_run("s4docs", [f["s4_old"]], [f["s4_new"]], d).path)
    outputs.append(tt_run("tprs", [f["tpr_old"]], [f["tpr_new"]], d).path)
    pa, pb = os.path.join(d, "pa.pdf"), os.path.join(d, "pb.pdf")
    tt.write_attune_pdf(pa)
    tt.write_attune_pdf(pb)
    outputs.append(tt_run("prints", [pa], [pb], d, "pr").path)
    outputs.append(tt_run("prints", [pa], [pb], d, "pr", passenger_only=True).path)
    g, n = tt._books(d)
    outputs.append(tt_run("timetables", [g], [n], d).path)

    # Section 4 check (rule set read from a synthetic PDF), with a formula-like remark
    from rstools.timetable.section4 import run_check
    s4 = os.path.join(d, "s4f.pdf")
    tt.write_s4_pdf(s4, [("Alpha and Beta Jn 100.1", "MID WEEK", "0140 T-F to 0350 T-F BLOCKED", "=SUM(A1:A9)")])
    xml = os.path.join(d, "chk.xml")
    with open(xml, "w", encoding="utf-8") as fh:
        fh.write('<diagramExchange xmlns="http://www.tracsis.com/TTVP_Interface" version="1.0" plantype="L" '
                 'startdate="2026-12-13" enddate="2027-05-15"><trainList><train id="1A01XX" daysRun="NNNYYYYNN" '
                 'planType="L"><leg origin="AAA" dep="02:00:00" dest="BBB" arr="02:10:00"/></train></trainList>'
                 '<locationList><location tiploc="AAA" longDesc="Alpha"/><location tiploc="BBB" longDesc="Beta Jn"/>'
                 '</locationList></diagramExchange>')
    s4_out = run_check(xml, [s4], d)[0]
    outputs.append(s4_out)

    # berthing chart comparison
    from rstools.berthing import engine as berth
    old, new = os.path.join(d, "old_chart.xlsx"), os.path.join(d, "new_chart.xlsx")
    tb.make_chart(old)
    tb.make_chart(new)
    wb = openpyxl.load_workbook(new)
    wb["Brighton"]["D2"] = "4 387 0510"
    wb.save(new)
    r = berth.compare_charts(old, new, "FFFF00", d)
    outputs += [r.chart, r.report]

    # Live View export (with confirmations)
    from rstools.live.adapters import compute
    from rstools.live.export import export
    live = compute("s4docs", {"a": [f["s4_old"]], "b": [f["s4_new"]]})
    lx = os.path.join(d, "live.xlsx")
    export(lx, live, live.items, "All", "", {live.items[0].key})
    outputs.append(lx)

    assert len(outputs) == len(set(outputs)), "an output overwrote another"
    for path in outputs:
        assert path.endswith(".xlsx") and os.path.isfile(path), path
        check_workbook(path)
    # the formula-like text survives as text
    clash = openpyxl.load_workbook(s4_out)["Clashes"]
    assert any(c.value == "=SUM(A1:A9)" for row in clash.iter_rows() for c in row)
