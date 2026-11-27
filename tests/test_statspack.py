"""Synthetic Stats Pack tests (no real plan data needed).

Builds a tiny TRENT VehicleLayout29 print (.docx) and Attune XML, then runs every Stats Pack mode.
Run with:  python -m pytest tests
"""
import json
import os
import sys
import tempfile
import zipfile

import pytest
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rstools.statspack.compare import compare_pack_files, read_pack  # noqa: E402
from rstools.statspack.engine import (PackOptions, PlanInputs, compare_plans, build_pack,  # noqa: E402
                                      StatsPackError, day_availability, load_plan, write_pack)
from rstools.statspack.trent import TrentFormatError, parse_vehicle_layout  # noqa: E402

HEADER = "     {dep} {num:<4}{days:<7}LTP    FROM - 13/12/2026   UNTIL - 15/05/2027" + " " * 32 + "FLEET   :{fleet}"
COLS = "              AP  DP Arr    Dep                    Route                                         Mileage"


def move(loc, ap, dp, arr, dep, head, route, cum, miles):
    return f"     {loc:<8}{ap:>3} {dp:>3} {arr:<5}  {dep:<5}  {head:<6}{'':21}{route:<36}{cum:>7.2f} {miles:>6.2f}"


def act(loc, ap, arr, what):
    return f"     {loc:<8}{ap:>3}     {arr:<5}{'':18}{what}"


def diagram(dep, num, days, fleet, rows, loaded, empty):
    return ([HEADER.format(dep=dep, num=num, days=days, fleet=fleet), "", "", COLS, ""] + rows +
            ["", "", f"   Mileage:  (Loaded)  {loaded:.2f}   (Empty)   {empty:.2f}   (Total)  {loaded + empty:.2f}",
             "", ""])


def plan_lines(extra_miles=0.0):
    a = diagram("BI", 1, "MO", "377/4", [
        move("BRHM", "", "1", "", "05+00", "5A01BI", "1(1)", 10.0, 10.0),
        move("HYWRDSH", "2", "2", "05+30", "05.40", "1A02BI", "1(1)", 50.0 + extra_miles, 40.0 + extra_miles),
        act("VICTRIC", "15", "06.40", "STABLD"),
    ], 40.0 + extra_miles, 10.0)
    b = diagram("HE", 7, "MO", "700/0", [
        move("VICTRIC", "", "9", "", "07.00", "1B03SX", "7(1)", 30.0, 30.0),
        act("BRGHTN", "4", "08.00", "STABLD"),
    ], 30.0, 0.0)
    c = diagram("BI", 1, "TO", "377/4", [
        move("BRHM", "", "1", "", "05+00", "5A01BI", "1(1)", 10.0, 10.0),
        move("HYWRDSH", "2", "2", "05+30", "05.40", "1A02BI", "1(1)", 50.0, 40.0),
        act("VICTRIC", "15", "06.40", "STABLD"),
    ], 40.0, 10.0)
    return a + b + c


def write_docx(path, lines):
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(t)}</w:t></w:r></w:p>' if t else "<w:p/>"
                   for t in lines)
    doc = ('<?xml version="1.0" encoding="utf-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", doc)


def write_xml(path):
    def train(tid, mask, legs):
        return (f'<train id="{tid}" trainKey="1" validFrom="2026-12-14" validUntil="2027-05-14" daysRun="{mask}" '
                f'planType="L">' + "".join(legs) + "</train>")
    xml = ('<diagramExchange version="1.0" plantype="L" xmlns="http://www.tracsis.com/TTVP_Interface"><trainList>'
           + train("5A01BI", "NNYYNNNNN", ['<leg origin="BRHM" dep="05:00:00" dest="HYWRDSH" arr="05:30:00"/>'])
           + train("1A02BI", "NNYYNNNNN", ['<leg origin="HYWRDSH" dep="05:40:00" dest="GTWK" arr="05:50:00"/>',
                                           '<leg origin="GTWK" dep="05:52:00" dest="ECROYDN" arr="06:10:00" '
                                           'arrStopType="P"/>',
                                           '<leg origin="ECROYDN" dep="06:10:00" dest="VICTRIC" arr="06:40:00" '
                                           'depStopType="P"/>'])
           + train("1B03SX", "NNYNNNNNN", ['<leg origin="VICTRIC" dep="07:00:00" dest="BRGHTN" arr="08:00:00"/>'])
           + '</trainList><locationList>'
           + "".join(f'<location tiploc="{t}" longDesc="{d}"/>' for t, d in
                     (("BRHM", "Bognor Regis"), ("HYWRDSH", "Haywards Heath"), ("GTWK", "Gatwick Airport"),
                      ("ECROYDN", "East Croydon"), ("VICTRIC", "London Victoria"), ("BRGHTN", "Brighton")))
           + '</locationList></diagramExchange>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)


def setup_plan(folder, name="a", extra_miles=0.0):
    x, d = os.path.join(folder, f"{name}.xml"), os.path.join(folder, f"{name}.docx")
    write_xml(x)
    write_docx(d, plan_lines(extra_miles))
    return load_plan(PlanInputs(x, d))


def opts(folder, days, **kw):
    return PackOptions(days=days, operators={"SNGX", "TLGN"}, fleets=None, output_dir=folder, **kw)


def tab(path, name):
    return dict(read_pack(path))[name]


def test_parse_trent():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.docx")
        write_docx(p, plan_lines())
        data = parse_vehicle_layout(p)
        assert len(data.diagrams) == 3
        assert data.days() == {0, 1}
        assert data.fleets() == {"377/4", "700/0"}


def test_rejects_other_layout():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.docx")
        write_docx(p, ["DIAGRAM : 1   BI   MO", "some other print"])
        try:
            parse_vehicle_layout(p)
        except TrentFormatError as exc:
            assert "VehicleLayout29" in str(exc)
        else:
            raise AssertionError("other TRENT layouts must be rejected")


def test_single_day_pack():
    with tempfile.TemporaryDirectory() as d:
        plan = setup_plan(d)
        o = opts(d, [0], output_name="mo")
        per_day, warnings = build_pack(plan, o, "test")
        paths = write_pack(per_day, o, plan, "test")
        assert [os.path.basename(p) for p in paths] == ["mo.xlsx"]
        miles = tab(paths[0], "Service Miles")
        heads = [r.cells[0] for r in miles.rows if r.kind == "body"]
        assert sorted(heads) == ["1A02BI", "1B03SX", "5A01BI"]
        unit = {r.cells[0]: r.cells for r in tab(paths[0], "Mileage by Unit").rows}
        assert unit["377/4"][1:4] == [10, 40, 50]           # empty, in service, total
        assert unit["700/0"][3] == 30
        # operator split: TLGN only keeps the HE depot diagram
        o2 = PackOptions(days=[0], operators={"TLGN"}, fleets=None, output_dir=d, output_name="tl")
        per_day, _w = build_pack(plan, o2, "test")
        unit = {r.cells[0] for r in per_day[0][1][5].rows if r.kind == "body"}
        assert unit == {"700/0"}


def test_fleet_missing_from_the_table_is_reported_once():
    """A fleet with no car count (e.g. a 'MAINT' diagram) makes the vehicle totals unknown (???, as TRACS-RS);
    the run says which fleet and why, once for the whole pack rather than day by day."""
    with tempfile.TemporaryDirectory() as d:
        x, p = os.path.join(d, "a.xml"), os.path.join(d, "a.docx")
        write_xml(x)
        write_docx(p, [line.replace(":700/0", ":MAINT") for line in plan_lines()])
        plan = load_plan(PlanInputs(x, p))
        per_day, warnings = build_pack(plan, opts(d, [0, 1]), "test")
        unit = {r.cells[0]: r.cells for t in per_day[0][1] if t.name == "Vehicle Mileage by Service Code"
                for r in t.rows}
        assert unit["MAINT"][1:] == [None, None, None] and unit["377/4"][3] == 50 * 4
        said = [w for w in warnings if "MAINT" in w]
        assert len(said) == 1 and "fleet table" in said[0] and "???" in said[0]
        plain = build_pack(setup_plan(d, "b"), opts(d, [0, 1]), "test")[1]
        assert not [w for w in plain if "fleet table" in w]


def test_xml_reader_edge_cases():
    """A public time printed before midnight for a working time just after it keeps its own clock time
    (23:59; public times are only shown, never added up); a location without a code is not stored under
    ''; washes and notes inside a <coupled> element (another diagram's) are not counted for this diagram."""
    from rstools.statspack.attune import parse_attune_xml
    xml = ('<diagramExchange version="1.0" plantype="L" xmlns="http://www.tracsis.com/TTVP_Interface"><trainList>'
           '<train id="5A01BI" daysRun="NNYNNNNNN" planType="L">'
           '<leg origin="BRHM" dep="00:00:30" depPub="23:59:00" dest="HYWRDSH" arr="00:30:00" arrPub="00:30:00"/>'
           '<leg origin="HYWRDSH" dep="00:40:00" dest="BRGHTN" arr="01:00:00"/></train></trainList>'
           '<locationList><location tiploc="BRHM" longDesc="Barnham"/><location longDesc="No code"/></locationList>'
           '<unitDiagramList><unitDiagram id="1" type="L" daysrun="NNYNNNNNN"><depot id="BI"/><details>'
           '<diagMovement legno="1"><journey origin="BRHM" dep="00:00:30" dest="BRGHTN" arr="01:00:00">'
           '<coupled position="2"><diagram id="9"/><depot id="SU"/><activity id="WASH"/><text>other</text></coupled>'
           '</journey></diagMovement><diagStatic legno="2"><activity id="WASH"/><text>own note</text></diagStatic>'
           '</details></unitDiagram></unitDiagramList></diagramExchange>')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.xml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(xml)
        data = parse_attune_xml(p)
    leg = data.trains["5A01BI"][0].legs[0]
    assert leg.dep == 30 and leg.dep_pub == 23 * 3600 + 59 * 60   # shown as 23:59, never a negative time
    assert data.trains["5A01BI"][0].legs[1].dep == 40 * 60
    assert "" not in data.locations and data.locations["BRHM"] == "Barnham"
    unit = data.unit_diagrams[0]
    assert unit.depot == "BI" and unit.activities == {"WASH": 1} and unit.notes == ["own note"]


def test_merged_and_split_week():
    with tempfile.TemporaryDirectory() as d:
        plan = setup_plan(d)
        assert day_availability(plan, [0, 1, 2]) == ["Wednesday (WO) is not in the TRENT print or the XML."]
        o = opts(d, [0, 1], output_name="wk")
        per_day, _w = build_pack(plan, o, "test")
        merged = write_pack(per_day, o, plan, "test")
        names = [n for n, _t in read_pack(merged[0])]
        assert "Mileage by Unit" in names and "MO Mileage by Unit" in names and "TO Mileage by Unit" in names
        unit = {r.cells[0]: r.cells for r in tab(merged[0], "Mileage by Unit").rows}
        assert unit["377/4"][3] == 100                      # MO + TO
        o.output = "days"
        split = write_pack(per_day, o, plan, "test")
        assert sorted(os.path.basename(p) for p in split) == ["wk MO.xlsx", "wk TO.xlsx"]
        o.output = "totals"
        totals = write_pack(per_day, o, plan, "test")
        names = [n for n, _t in read_pack(totals[0])]
        assert "Mileage by Unit" in names and not any(n.startswith(("MO ", "TO ")) for n in names)


def test_compare_plans_and_packs():
    with tempfile.TemporaryDirectory() as d:
        old, new = setup_plan(d, "old"), setup_plan(d, "new", extra_miles=5.0)
        paths, _w, n = compare_plans(old, new, opts(d, [0], output_name="cmp"), "test")
        assert n > 0
        diffs = tab_rows(paths[0], "Differences")
        assert any(r[0] == "Mileage by Unit" and r[1] == "377/4" and r[5] == "+5" for r in diffs)
        # same plan twice -> no differences
        _p, _w, n = compare_plans(old, old, opts(d, [0], output_name="same"), "test")
        assert n == 0
        # pack-file comparison
        a = write_pack(build_pack(old, opts(d, [0]), "test")[0], opts(d, [0], output_name="pa"), old, "test")[0]
        b = write_pack(build_pack(new, opts(d, [0]), "test")[0], opts(d, [0], output_name="pb"), new, "test")[0]
        out = os.path.join(d, "packs.xlsx")
        assert compare_pack_files(a, b, out) > 0
        assert compare_pack_files(a, a, os.path.join(d, "same2.xlsx")) == 0


def test_bad_files_and_mileage_check():
    from rstools.statspack.engine import StatsPackError
    with tempfile.TemporaryDirectory() as d:
        plan = setup_plan(d)
        assert not plan.warnings
        bad_xml = os.path.join(d, "bad.xml")
        with open(bad_xml, "w") as fh:
            fh.write('<diagramExchange xmlns="http://www.tracsis.com/TTVP_Interface"><trainList><train id="1A01"')
        for xml, docx in ((bad_xml, plan.trent.path), (plan.attune.path, bad_xml)):
            try:
                load_plan(PlanInputs(xml, docx))
            except StatsPackError:
                pass
            else:
                raise AssertionError("unreadable files must give a clear error")
        broken = os.path.join(d, "broken.docx")
        with zipfile.ZipFile(broken, "w") as z:
            z.writestr("word/document.xml", "<w:document")
        try:
            parse_vehicle_layout(broken)
        except TrentFormatError:
            pass
        else:
            raise AssertionError("a damaged .docx must give a clear error")
        # a print whose rows don't add up to the printed total is flagged
        lines = plan_lines()
        lines = [ln.replace("(Total)  50.00", "(Total)  80.00") for ln in lines]
        short = os.path.join(d, "short.docx")
        write_docx(short, lines)
        assert any("do not add up" in w for w in parse_vehicle_layout(short).warnings)


def test_coupled_across_depots():
    """TRENT gives coupled units by diagram number only; the partner may be at another depot."""
    from rstools.statspack.fleet import FleetTable
    from rstools.statspack.model import build_day
    from rstools.statspack.stats import build_tables
    lines = (diagram("BI", 1, "MO", "377/4", [
                 move("BRHM", "", "1", "", "05+00", "5A01BI", "1(1)", 10.0, 10.0),
                 move("HYWRDSH", "2", "2", "05+30", "05.40", "1A02BI", "1(1)\\312(2)", 50.0, 40.0),
                 act("VICTRIC", "15", "06.40", "STABLD")], 40.0, 10.0)
             + diagram("SU", 312, "MO", "377/3", [
                 move("HYWRDSH", "", "2", "", "05.40", "1A02BI", "1(1)\\312(2)", 40.0, 40.0),
                 act("VICTRIC", "15", "06.40", "STABLD")], 40.0, 0.0))
    with tempfile.TemporaryDirectory() as d:
        x, p = os.path.join(d, "a.xml"), os.path.join(d, "a.docx")
        write_xml(x)
        write_docx(p, lines)
        plan = load_plan(PlanInputs(x, p))
        model = build_day(plan.trent, plan.attune, FleetTable.load(), 0, {"SNGX", "TLGN"})
        part = next(pt for t in model.trains if t.headcode == "1A02BI" for pt in t.parts)
        assert part.formation == ("BI1", "SU312")
        forms = {r.cells[0] for r in next(t for t in build_tables(model, {}) if t.name == "Mileage by Formation").rows}
        assert "377/3+377/4" in forms and not any("?" in f for f in forms)


def test_comparison_options():
    from rstools.statspack.compare import CompareOptions
    with tempfile.TemporaryDirectory() as d:
        old, new = setup_plan(d, "old"), setup_plan(d, "new", extra_miles=5.0)
        o = opts(d, [0], output_name="trim", compare=CompareOptions(changed_tabs_only=True, changed_rows_only=True))
        path = compare_plans(old, new, o, "test")[0][0]
        rows = tab_rows(path, "Differences")
        summary = {r[0]: r for r in rows if r[0] and r[0].startswith("Unit miles")}
        assert summary["Unit miles - total"][3] == "+5", summary
        names = [n for n, _t in read_pack(path)]
        assert "Mileage by Unit" in names and "Vehicle Counts at Stops" not in names    # unchanged tab left out
        unit = tab(path, "Mileage by Unit")
        assert [r.cells[0] for r in unit.rows] == ["377/4", "Total"]                  # unchanged 700/0 row hidden


def test_mileage_flags_and_names():
    from rstools.naming import today
    from rstools.statspack.compare import CompareOptions
    with tempfile.TemporaryDirectory() as d:
        old = setup_plan(d, "old")
        for extra, expect in ((5.0, False), (15.0, True)):
            new = setup_plan(d, f"new{int(extra)}", extra_miles=extra)
            path = compare_plans(old, new, opts(d, [0], compare=CompareOptions(flag_miles=10)), "test")[0][0]
            rows = tab_rows(path, "Differences")
            head = next(r for r in rows if r[0] and str(r[0]).startswith("Mileage increases over 10 miles"))
            flagged = int(str(head[0]).rsplit(":", 1)[1])
            assert (flagged > 0) == expect, (extra, flagged)
        # default names
        packs = write_pack(build_pack(old, opts(d, [0]), "test")[0], opts(d, [0]), old, "test")
        assert os.path.basename(packs[0]) == "Stats pack for DEC26 MO.xlsx", packs
        both = write_pack(build_pack(old, opts(d, [0, 1]), "test")[0], opts(d, [0, 1]), old, "test")
        assert os.path.basename(both[0]) == "Stats pack for DEC26.xlsx", both
        cmp = compare_plans(old, new, opts(d, [0]), "test")[0][0]
        assert os.path.basename(cmp).startswith("old vs new15 MO"), cmp     # '(2)' if the name is taken
        from rstools.naming import compare_name
        assert compare_name("C:/x/DEC26 CWN Proof 1.xlsx", "DEC26 CWN Proof 2 (1).xlsx") == \
            f"{today()} DEC26 Proof 1 vs Proof 2"


def test_unit_reports():
    """Units followed with an XML next-day working (BI1 -> BI2) and by inference (SX7 -> SX8);
    washes / CETs counted, depot returns classified, the captive unit found."""
    from rstools.statspack.units import Depots, captive_reports, depot_reports, follow_units, wash_cet_reports
    lines = (diagram("BI", 1, "MO", "377/4", [
                 move("LOVRSWS", "", "1", "", "05+00", "5A01BI", "1(1)", 10.0, 10.0),
                 act("BRGHTN", "4", "05.30", "WASH"),
                 move("BRGHTN", "", "4", "", "05.40", "1A02BI", "1(1)", 50.0, 40.0),
                 act("HOVEY36", "1", "06+40", "STABLD")], 40.0, 10.0)
             + diagram("BI", 2, "TO", "377/4", [
                 move("HOVEY36", "", "1", "", "05+00", "5A03BI", "2(1)", 10.0, 10.0),
                 act("LOVRSWS", "2", "05+30", "CET")], 0.0, 10.0)
             + diagram("SX", 7, "MO", "700/0", [
                 move("BRGHTN", "", "1", "", "07.00", "1B03SX", "7(1)", 30.0, 30.0),
                 act("EBOUSID", "4", "08+00", "STABLD")], 30.0, 0.0)
             + diagram("SX", 8, "TO", "700/0", [
                 move("EBOUSID", "", "1", "", "07+00", "5B04SX", "8(1)", 30.0, 30.0),
                 act("BRGHTN", "4", "08+00", "STABLD")], 0.0, 30.0))
    xml = ('<diagramExchange plantype="L" xmlns="http://www.tracsis.com/TTVP_Interface"><trainList>'
           '<train id="5A01BI" daysRun="NNYNNNNNN" planType="L"><leg origin="LOVRSWS" dep="05:00:00" dest="BRGHTN" '
           'arr="05:30:00"/></train></trainList><locationList>'
           '<location tiploc="LOVRSWS" longDesc="Lovers Walk T&amp;R.S.M.D"/>'
           '<location tiploc="BRGHTN" longDesc="Brighton"/>'
           '<location tiploc="HOVEY36" longDesc="Hove Yard Sidings 3-6"/><location tiploc="EBOUSID" '
           'longDesc="Eastbourne Sidings"/></locationList><diagramList>'
           '<unitDiagram id="1" daysrun="NNYNNNNNN"><depot id="BI"/><details><diagStatic legno="9" loc="HOVEY36">'
           '<activity id=" "><text>BI2 05+00TO (F)</text></activity></diagStatic></details></unitDiagram>'
           '<unitDiagram id="2" daysrun="NNNYNNNNN"><depot id="BI"/><details><diagStatic legno="9" loc="LOVRSWS">'
           '<activity id=" "><text>Stabld</text></activity></diagStatic></details></unitDiagram>'
           '</diagramList></diagramExchange>')
    with tempfile.TemporaryDirectory() as d:
        x, p = os.path.join(d, "u.xml"), os.path.join(d, "u.docx")
        with open(x, "w", encoding="utf-8") as fh:
            fh.write(xml)
        write_docx(p, lines)
        plan = load_plan(PlanInputs(x, p))
        depots = Depots.load(plan.attune.locations, os.path.join(d, "none.csv"))
        units, per_day, warnings = follow_units(plan.trent, plan.attune, [0, 1], depots)
        chains = {u.diagrams[0].key: ([x.key for x in u.diagrams], u.links, u.washes, u.cets) for u in units}
        assert chains["BI1"] == (["BI1", "BI2"], ["XML"], 1, 1), chains
        assert chains["SX7"] == (["SX7", "SX8"], ["inferred"], 0, 0), chains
        washes = wash_cet_reports(units, per_day, True)[0]
        assert [r[3] for r in washes.rows] == [1, 0]                       # washes per unit
        moves = {(r[0], r[1]): r[3] for r in depot_reports(per_day, depots, plan.attune.locations)[0].rows}
        assert moves[("MO", "BI1")] == "Leaves depot" and moves[("TO", "BI2")] == "Back to depot"
        assert moves[("MO", "SX7")] == "Away from depot"
        captive = captive_reports(units, per_day, depots, plan.attune.locations, True, [0, 1])[0]
        assert [(r[0], r[3]) for r in captive.rows] == [("MO SX7", "Yes")], captive.rows
        assert depots.depot_of("LOVRSWS") == "Lovers Walk" and depots.depot_of("EBOUSID") == ""
        # every format writes
        from rstools.statspack.engine import unit_reports
        for fmt in ("xlsx", "pdf", "docx"):
            path = unit_reports(plan, opts(d, [0, 1], fmt=fmt), ["washes", "depots", "captive"], True)[0][0]
            assert path.endswith("." + fmt) and os.path.getsize(path) > 1000


def test_no_inference_at_lovers_walk_stewarts_lane_selhurst():
    """A unit stabling at Lovers Walk, Stewarts Lane or Selhurst ends its cycle there (never inferred onwards);
    elsewhere a matching next-day start is still inferred."""
    from rstools.statspack.units import Depots, ends_cycle, follow_units
    lines = []
    for n, loc in ((1, "STWTTMD"), (3, "SLHRSTD"), (5, "LOVRSWS"), (7, "EBOUSID")):
        lines += diagram("SX", n, "MO", "700/0", [
            move("BRGHTN", "", "1", "", "07.00", f"1B0{n}SX", f"{n}(1)", 30.0, 30.0),
            act(loc, "4", "08+00", "STABLD")], 30.0, 0.0)
        lines += diagram("SX", n + 1, "TO", "700/0", [
            move(loc, "", "1", "", "07+00", f"5B0{n}SX", f"{n + 1}(1)", 30.0, 30.0),
            act("BRGHTN", "4", "08+00", "STABLD")], 0.0, 30.0)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "u.docx")
        write_docx(p, lines)
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        depots = Depots.load({}, os.path.join(d, "none.csv"))
        units, _per_day, _w = follow_units(plan.trent, None, [0, 1], depots)
        chains = {u.diagrams[0].key: [x.key for x in u.diagrams] for u in units}
        assert chains["SX1"] == ["SX1"] and chains["SX3"] == ["SX3"] and chains["SX5"] == ["SX5"], chains
        assert chains["SX7"] == ["SX7", "SX8"], chains
    assert ends_cycle("STWTBS", None) and not ends_cycle("SELHRST", None)       # the station is not the depot


def test_operators():
    from rstools.statspack.model import operator_of
    assert [operator_of(d) for d in ("BI", "SU", "SL", "HE", "TB")] == ["SNGX"] * 3 + ["TLGN"] * 2
    assert operator_of("XX", "TLGN") == "TLGN"       # unknown depot: by the stock's operator
    assert operator_of("XX") == "Other"


def test_fleet_table_upgrade():
    import csv
    from rstools.statspack import fleet
    with tempfile.TemporaryDirectory() as d:
        old = os.path.join(d, "TrainPlanningTools", "fleet.csv")
        os.makedirs(os.path.dirname(old))
        with open(old, "w", newline="", encoding="cp1252") as fh:     # an old-layout table, re-saved by Excel
            fh.write("Class Name,Power Type,Vehicles per Unit,Units Available,Unit Length (metres)\n"
                     "377/4,EMU,4,130,80.77\n717/0,Unknown,6,21,\nMy class \xa3,EMU,4,1,\n")
        env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            table = fleet.FleetTable.load()
        finally:
            if env is None:
                del os.environ["LOCALAPPDATA"]
            else:
                os.environ["LOCALAPPDATA"] = env
        assert table.get("377/4").available == 130              # the user's value is kept
        assert table.get("717/0").power == "EMU" and table.get("717/0").operator == "TLGN"
        assert table.get("700/1").length == 242.6                # new classes added
        assert table.get("My class \xa3") is not None
        with open(old, encoding="utf-8-sig") as fh:                  # saved again in the current layout
            assert next(csv.reader(fh)) == fleet.COLUMNS


def tab_rows(path, sheet):
    """Plain cell values of a sheet by name (rows below the title)."""
    import re
    from rstools.statspack.compare import _sheet_cells
    z = zipfile.ZipFile(path)
    wb = z.read("xl/workbook.xml").decode()
    names = re.findall(r'<sheet [^>]*name="([^"]+)"', wb)
    idx = names.index(sheet) + 1
    sst = []
    if "xl/sharedStrings.xml" in z.namelist():
        sst = [re.sub(r"<[^>]+>", "", s) for s in
               re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
    rows = _sheet_cells(z.read(f"xl/worksheets/sheet{idx}.xml"), sst)
    return [[rows[r].get(c) for c in range(1, 7)] for r in sorted(rows) if r > 2]



def test_seats_report(monkeypatch):
    """Seats per train from the fleet data, by corridor or service group, with a time window at a station
    (arriving / departing), passes shown as passes, and the engine writing the report."""
    from rstools.statspack.fleet import FleetTable
    from rstools.statspack.model import build_day
    from rstools.statspack.seats import Group, Window, load_groups, run_seats, DEFAULT_GROUPS
    with tempfile.TemporaryDirectory() as d:
        plan = setup_plan(d)
        fleet = FleetTable.load()
        model = build_day(plan.trent, plan.attune, fleet, 0, {"SNGX", "TLGN"})
        names = plan.attune.locations
        bml = Group("Corridor", "Main line", ["Haywards Heath", "Gatwick Airport", "East Croydon"])
        reports, found, _w = run_seats([model], fleet, bml, None, False, names, [])
        assert [s.train.headcode for s in found] == ["1A02BI"]
        assert found[0].cap.seats == 20 + 223 and found[0].cap.standing == 145
        summary = reports[0].rows[0]
        assert summary[:2] == ["Monday", 1] and summary[6] == 243
        # arriving at London Victoria 06:00-07:00 (1A02 arrives 06:40); 1B03 departs at 07:00
        win = Window("London Victoria", 6 * 3600, 7 * 3600, "arriving")
        _r, found, _w = run_seats([model], fleet, bml, win, False, names, [])
        assert [(s.train.headcode, s.at_time) for s in found] == [("1A02BI", 6 * 3600 + 40 * 60)]
        both = Group("Service group", "Victoria - Brighton", ["London Victoria", "Brighton"])
        dep = Window("London Victoria", 6 * 3600, 7 * 3600 + 1800, "departing")
        _r, found, _w = run_seats([model], fleet, both, dep, False, names, [])
        assert [s.train.headcode for s in found] == ["1B03SX"] and found[0].cap.seats == 52 + 427
        # East Croydon is passed by 1A02
        pas = Window("East Croydon", 6 * 3600, 7 * 3600, "both")
        reports, found, _w = run_seats([model], fleet, bml, pas, False, names, [])
        assert found[0].stops is False and reports[2].rows[0][7] == "Passes"
        # fleet and headcode rules
        assert not run_seats([model], fleet, Group("Service group", "x", bml.route, fleets=["-377/4"]), None,
                             False, names, [])[1]
        assert not run_seats([model], fleet, Group("Service group", "x", bml.route, headcodes=["2"]), None,
                             False, names, [])[1]
        # the built-in list loads, and the engine writes a report for a listed corridor
        groups = load_groups(DEFAULT_GROUPS)
        assert groups and all(g.kind == "Corridor" and len(g.route) >= 2 for g in groups)
        monkeypatch.setenv("LOCALAPPDATA", d)                 # the editable list is created in a scratch folder
        import openpyxl
        from rstools.statspack.engine import seats_report
        paths, _w, summary = seats_report(plan, opts(d, [0]), "Corridor",
                                          "Brighton Main Line (East Croydon - Brighton)",
                                          True, ("East Croydon", "06:00", "07:00"), "both")
        assert os.path.isfile(paths[0]) and summary.startswith("1 train(s), 388 total capacity")
        assert openpyxl.load_workbook(paths[0]).sheetnames == ["Capacity Summary", "Capacity by Hour",
                                                               "Capacity by Train", "Notes"]


def test_unit_and_seats_reports_compare_two_timetables(monkeypatch):
    """With a second (original) timetable, unit and seats reports show what changed: summaries side by side,
    detail rows only where they differ, rows in one timetable only flagged."""
    import copy
    import openpyxl
    from rstools.statspack.engine import seats_report, unit_reports
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        new = setup_plan(d)
        old = copy.deepcopy(new)
        old.trent.diagrams = [x for x in old.trent.diagrams if not (x.depot == "BI" and 0 in x.days)]  # no MO 377/4
        paths, _w, summary = seats_report(new, opts(d, [0]), "Corridor",
                                          "Brighton Main Line (East Croydon - Brighton)", True, old=old)
        assert summary.endswith("0 -> 1 train(s), 0 -> 388 total capacity (+388).")
        wb = openpyxl.load_workbook(paths[0])
        assert wb.sheetnames == ["Comparison Summary", "Capacity Summary", "Capacity by Hour", "Capacity by Train",
                                 "Notes"]
        rows = [r for r in wb["Capacity by Train"].iter_rows(values_only=True) if r[0] == "Monday"]
        assert rows == [("Monday", "1A02BI", "(whole row)", "-", "Present", "Only in the updated", None)]
        seats = {r[1]: r[2:5] for r in wb["Capacity Summary"].iter_rows(values_only=True) if r[0] == "Monday"}
        assert seats["Total seats"] == (0, 243, 243)
        paths, _w = unit_reports(new, opts(d, [0, 1]), ["washes", "depots"], False, old=old)
        wb = openpyxl.load_workbook(paths[0])
        assert wb.sheetnames[0] == "Comparison Summary" and "Depot Moves by Day" in wb.sheetnames
        same, _w = unit_reports(new, opts(d, [0, 1]), ["washes"], False, old=new)
        summary_rows = list(openpyxl.load_workbook(same[0])["Comparison Summary"].iter_rows(min_row=4,
                                                                                             values_only=True))
        assert summary_rows and all(r[2] == 0 and r[3] == 0 and r[4] == 0 for r in summary_rows)


def test_seats_headcode_groups_directions_and_station_to_station(monkeypatch):
    from rstools.statspack.fleet import FleetTable
    from rstools.statspack.model import build_day
    from rstools.statspack.seats import (Group, Window, headcode_group, headcode_groups, journey_group,
                                         network_stations, run_seats)
    from rstools.statspack.engine import seats_report
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        plan = setup_plan(d)
        fleet = FleetTable.load()
        model = build_day(plan.trent, plan.attune, fleet, 0, {"SNGX", "TLGN"})
        names = plan.attune.locations
        # headcode groups from the XML (empty stock 5A01 left out)
        assert [c for c, _d in headcode_groups(plan.attune)] == ["1A", "1B"]
        assert "London Victoria" in network_stations(plan.attune)
        found = run_seats([model], fleet, headcode_group("1A"), None, True, names, [])[1]
        assert [s.train.headcode for s in found] == ["1A02BI"]
        # corridor directions: 1A02 runs Haywards Heath -> Victoria, 1B03 Victoria -> Brighton
        line = Group("Corridor", "Main line", ["London Victoria", "East Croydon", "Gatwick Airport", "Haywards Heath",
                                               "Brighton"])
        heads = {k: [s.train.headcode for s in run_seats([model], fleet, line.with_direction(k), None, True, names,
                                                         [])[1]] for k in ("forward", "reverse", "both")}
        assert heads == {"forward": ["1B03SX"], "reverse": ["1A02BI"], "both": ["1A02BI", "1B03SX"]}
        assert line.with_direction("reverse").direction_text == "Brighton to London Victoria"
        # station to station: stops at both, in that order (East Croydon is only passed by 1A02)
        trips = lambda a, b, w=None: [s.train.headcode for s in run_seats([model], fleet, journey_group(a, b), w,
                                                                          True, names, [])[1]]
        assert trips("Haywards Heath", "London Victoria") == ["1A02BI"]
        assert trips("London Victoria", "Haywards Heath") == []
        assert trips("East Croydon", "London Victoria") == []
        assert trips("Haywards Heath", "London Victoria", Window("", 6 * 3600, 6 * 3600 + 600)) == []
        paths, _w, summary = seats_report(plan, opts(d, [0]), "Station to station", "", True,
                                          ("", "05:00", "06:00"), journey=("Haywards Heath", "London Victoria"))
        assert summary.startswith("1 train(s), 388 total capacity - Haywards Heath to London Victoria, 05:00-06:00 "
                                  "departing")
        paths, _w, summary = seats_report(plan, opts(d, [0]), "Service group", "1B   anything", True)
        assert summary.startswith("1 train(s), 1,202 total capacity - Service group: 1B")


def test_fuel_check_48_hours():
    """Diesel units must be fuelled at least every 48 hours; a whole-week unit wraps to the next week."""
    from rstools.statspack.units import DayDiagram, UnitWeek, fuel_reports

    def unit(n, fuel_days, days=range(7), fleet="171/7"):
        return UnitWeek([DayDiagram(d, f"SU{n}", fleet, "SLHRSTD", 300, "SLHRSTD", 1400, 0, 0,
                                    int(d in fuel_days), [1380] if d in fuel_days else []) for d in days])
    rep = fuel_reports([unit(801, (0, 2, 4, 6)), unit(802, (0, 4)), unit(803, (), range(3)),
                        unit(804, (), fleet="377/4")], {"171/7"}, list(range(7)))[0]
    res = {r[0]: (r[4], r[5], r[9]) for r in rep.rows}
    assert set(res) == {"MO SU801", "MO SU802", "MO SU803"}                # the 377/4 is not checked
    assert res["MO SU801"] == (4, "48:00", "OK")                           # Su 23:00 -> TO 23:00 is exactly 48 h
    assert res["MO SU802"] == (2, "96:00", "Over 48 hours (2 gap(s))")      # MO -> FO and FO -> next MO
    assert res["MO SU803"][2] == "No fuel"
    assert rep.rows[-1][9] == "OK"                                         # problems listed first


def test_capacity_report_seating_and_standing_toggles(monkeypatch):
    """Seating capacity and standing room can each be shown on their own, or both with the total."""
    import openpyxl
    from rstools.statspack.engine import StatsPackError, seats_report
    import pytest
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        plan = setup_plan(d)
        heads = lambda p: [c.value for c in openpyxl.load_workbook(p)["Capacity Summary"][3]]
        both, _w, s_both = seats_report(plan, opts(d, [0]), "Service group", "1A", True)
        seats, _w, s_seat = seats_report(plan, opts(d, [0]), "Service group", "1A", True, standing=False)
        stand, _w, s_stand = seats_report(plan, opts(d, [0]), "Service group", "1A", True, seating=False)
        assert heads(both[0])[-1] == "Total capacity (seats + standing)" and "Standing" in heads(both[0])
        assert "Standing" not in heads(seats[0]) and "Total seats" in heads(seats[0])
        assert "Total seats" not in heads(stand[0]) and "Standing" in heads(stand[0])
        assert s_seat.startswith("1 train(s), 243 seats") and s_stand.startswith("1 train(s), 145 standing room")
        assert s_both.startswith("1 train(s), 388 total capacity")
        assert os.path.basename(both[0]).startswith("Capacity 1A")
        with pytest.raises(StatsPackError):
            seats_report(plan, opts(d, [0]), "Service group", "1A", True, seating=False, standing=False)


# --------------------------------------------------------------------------- #
# TLGN unit diagram print (tab separated, station names, 4-character headcodes, next-day links)
# --------------------------------------------------------------------------- #
def tlgn_lines(num, days, rows, forms=""):
    t = "\t" * 8
    out = ["", f"\t\t\t\t\t\tHE {num}\t{days}\tFROM - 19/12/2026\tUNTIL - 15/05/2027\tFLEET    :379/0", "\t\t4-car",
           "\t\t\tOff (Previous Day)\t", "\t\t\t\t\t\t\tArrives Departs\tRoute\tMileage", ""]
    out += [t + "\t".join(r) for r in rows]
    out += ["", f"\t\t\tForms (Next Day)\t{forms}", "", t + "Mileage:\t(Loaded)\t20.00\t(Empty)\t2.00\t(Total)\t22.00"]
    return out


def write_tlgn(folder):
    so = tlgn_lines("303", "SO", [
        ("Hornsey E.M.U.D.", "", "05+00\xa0", "5T01", "", "303(1)", "  2.00"),
        ("London Kings Cross", "05+29\xa0", "05.54\xa0", "1T02", "", "303(1)", " 12.00"),
        ("Cambridge", "07.00\xa0", "07.10\xa0", "1T17", "", "303(1)", " 22.00"),
        ("Hornsey E.M.U.D.", "08.00\xa0", "", "WASH", "", "", ""),
        ("HRNSYMD", "", "", "STABLD", "", "", "")], forms="316")
    su = tlgn_lines("316", "Su", [
        ("Hornsey E.M.U.D.", "", "06+00\xa0", "5T05", "", "303(1)", "  2.00"),
        ("London Kings Cross", "06+29\xa0", "06.54\xa0", "1T06", "", "303(1)", " 22.00"),
        ("Hornsey E.M.U.D.", "08.00\xa0", "", "STABLD", "", "", "")])
    a, b = os.path.join(folder, "SO.docx"), os.path.join(folder, "SU.docx")
    write_docx(a, so)
    write_docx(b, su)
    return a, b


def test_tlgn_print_and_unit_reports():
    from rstools.statspack.trent import parse_vehicle_layout
    with tempfile.TemporaryDirectory() as d:
        a, b = write_tlgn(d)
        t = parse_vehicle_layout(a)
        (dg,) = t.diagrams
        assert dg.key == "HE303" and dg.next_num == "316" and dg.fleet == "379/0"
        assert [r.headcode for r in dg.rows if r.headcode] == ["5T01", "1T02", "1T17"]
        assert [r.miles for r in dg.rows if r.headcode] == [2.0, 10.0, 10.0]     # running miles -> per move
        assert dg.rows[-1].loc == "HRNSYMD" and dg.rows[1].loc == "KNGX"          # names as TIPLOCs (name table)
        try:                                     # the app takes VehicleLayout29 prints only
            load_plan(PlanInputs("", f"{a} ; {b}"), xml_optional=True)
            raise AssertionError("a VehicleLayout23 / TLGN print is refused")
        except StatsPackError as exc:
            assert "VehicleLayout23" in str(exc) and "VehicleLayout29" in str(exc)


def test_tlgn_headcodes_and_names_match_the_xml():
    from rstools.statspack.model import _short_index, _tiplocs
    from rstools.statspack.attune import AttuneData
    x = AttuneData(path="x", plan="", start="", end="", locations={"KNGX": "London Kings Cross",
                   "HRNSYMD": "Hornsey E.M.U.D."}, trains={"1T02GR": [], "1T17GR": []}, diagram_days=set(),
                   warnings=[])
    assert _short_index(x)["1T02"] == ["1T02GR"]
    assert _tiplocs(x, "London Kings Cross") == {"KNGX"} and _tiplocs(x, "Hornsey EMUD") == "Hornsey EMUD"
    assert _tiplocs(x, "hornsey e.m.u.d.") == {"HRNSYMD"} and _tiplocs(x, "KNGX") == "KNGX"


def test_corridor_station_spellings():
    from rstools.statspack.seats import Stations, load_groups, shown
    st = Stations({"STPXBOX": "St Pancras Low Level", "FRNDNLT": "Farringdon"})
    assert st.find("London St Pancras|St Pancras Low Level") == {"STPXBOX"} and not st.missing
    assert st.find("Nowhere|Elsewhere") == set() and st.missing == {"Nowhere|Elsewhere"}
    names = [g.name for g in load_groups(os.path.join(os.path.dirname(__import__("rstools.statspack.seats",
                                         fromlist=["x"]).__file__), "groups_default.csv"))]
    assert "Thameslink Core (St Pancras - Blackfriars)" in names and "Fen Line (Cambridge - Kings Lynn)" in names
    assert shown("London Blackfriars|Blackfriars") == "London Blackfriars"


def test_attune_day_masks():
    from rstools.days import days_of_mask
    assert days_of_mask("NNYYYYYNN") == {0, 1, 2, 3, 4}
    assert days_of_mask("NNNNNNNYN") == {5}
    assert days_of_mask("NYNNNNNNN") == {6}                  # Sunday is the 2nd character
    assert days_of_mask("NNNYYYYYN") == {1, 2, 3, 4, 5}      # Tue-Sat (after-midnight trains of Mon-Fri)


def test_379_seats_replace_old_placeholders_only(monkeypatch):
    """The 379/0's figures replace the zeros earlier versions shipped, never figures the user entered."""
    import csv
    from rstools.statspack import fleet as F
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fleet.csv")
        _h, rows = F._read_csv(F.DEFAULT_CSV)
        for r in rows:
            if r["Class Name"] == "379/0":
                for c in F._SEAT_COLS:
                    r[c] = "0"                                  # as shipped before 3.11.1
            if r["Class Name"] == "717/0":
                r["Standing Capacity"] = "500"                  # the user's own figure
        F._write(path, rows)
        F._upgrade(path)
        got = {r["Class Name"]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}
        assert [got["379/0"][c] for c in F._SEAT_COLS] == ["20", "189", "136", "325"]
        assert got["717/0"]["Standing Capacity"] == "500"
    # unit lengths: blanks filled (379/0, 717/0), the old wrong 171/8 length corrected, a user's own kept
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fleet.csv")
        _h, rows = F._read_csv(F.DEFAULT_CSV)
        for r in rows:
            if r["Class Name"] in ("379/0", "717/0"):
                r["Unit Length (metres)"] = ""
            if r["Class Name"] == "171/8":
                r["Unit Length (metres)"] = "94.48"
            if r["Class Name"] == "377/4":
                r["Unit Length (metres)"] = "81.0"
        F._write(path, rows)
        F._upgrade(path)
        got = {r["Class Name"]: r["Unit Length (metres)"] for r in csv.DictReader(open(path, encoding="utf-8-sig"))}
        assert (got["379/0"], got["717/0"], got["171/8"], got["377/4"]) == ("80.77", "121.7", "70.86", "81.0")


def test_retired_701_5_removed_unless_edited():
    """701/5 is no longer shipped; an unedited copy of the old row is dropped, a user-edited one is kept."""
    import csv
    from rstools.statspack import fleet as F
    assert F.FleetTable._read(F.DEFAULT_CSV).get("701/5") is None
    shipped = dict(F._RETIRED["701/5"])
    for units, expect_kept in (("27", False), ("30", True)):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fleet.csv")
            _h, rows = F._read_csv(F.DEFAULT_CSV)
            rows.append(dict(shipped, **{"Units Available": units}))
            F._write(path, rows)
            F._upgrade(path)
            got = {r["Class Name"] for r in csv.DictReader(open(path, encoding="utf-8-sig"))}
            assert ("701/5" in got) is expect_kept
            assert {r["Class Name"] for r in rows if r["Class Name"] != "701/5"} <= got


def test_withdrawn_313_455_removed_once():
    """313s and 455s are withdrawn: not in the built-in table, every row of them (edited or not, 'nQ' rows too)
    is removed from a user's copy once, and a row the user adds back afterwards is kept."""
    import csv
    from rstools.statspack import fleet as F
    table = F.FleetTable._read(F.DEFAULT_CSV)
    assert not [r.cls for r in table.rows if "313" in r.cls or "455" in r.cls]
    assert [F._withdrawn_class(n) for n in ("313/2", "3 313Q", "455/8", "4 455Q", "377/4", "4 377Q")] == \
        ["313", "313", "455", "455", "", ""]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fleet.csv")
        _h, rows = F._read_csv(F.DEFAULT_CSV)
        old = [dict(rows[0], **{"Class Name": n, "Units Available": "9"}) for n in ("313/2", "3 313Q", "455/8")]
        F._write(path, rows + old)
        F._upgrade(path)

        def names():
            return {r["Class Name"] for r in csv.DictReader(open(path, encoding="utf-8-sig"))}
        assert not {"313/2", "3 313Q", "455/8"} & names()
        assert {r["Class Name"] for r in rows} <= names()
        F._write(path, rows + old[2:])                     # the user adds a 455 back
        F._upgrade(path)
        assert "455/8" in names()
    with tempfile.TemporaryDirectory() as d:               # a new copy never gets them back
        path = os.path.join(d, "fleet.csv")
        F._upgrade(path)
        assert sorted(json.load(open(os.path.join(d, "fleet_withdrawn.json")))) == ["313", "455"]


def test_vl11_vl05_and_merged_layouts():
    """VehicleLayout11 / 05 (short names) are read like VL29, names become TIPLOCs, and a VL23 print's next-day
    links fill in a VL29 print of the same diagrams."""
    from rstools.statspack.engine import _read_trents
    t = "\t" * 7
    vl11 = ["\t" * 7 + "DIAGRAM :\tBI1\tSO\tFleet\t387/3", "\t\t\tStart Date : 19/12/2026\tEnd Date : 15/05/2027",
            "\t" * 6 + "OFF\t\t\tMiles from Fuel\t0.00",
            t + "\tBarnham\t\t04+20\xa0\t5H92\t1(1)\t22.29",
            t + "\tHay Hth\t06.09\xa0\t\t\tATTTT\t",
            t + "\tHay Hth\t\t06.13\xa0\t1F93\t10(1)/1(2)\t38.30",
            t + "\tVic (C)\t06.58\xa0\t\t\tSTABLD\t",
            "\t" * 6 + "WORKS\t\t\tMiles from Fuel\t0.00",
            "\t" * 7 + "Loaded\t38.30\tEmpty\t22.29\tTotal Mileage\t60.59"]
    vl05 = ["\t" * 6 + "Diagram  :\tBI\t1\tSO\t387/3", "\t\t\tRuns from:\t19/12/2026 until 15/05/2027",
            t + "Barnham\t\t04+20\xa0\t5H92\t\t1(1)",
            t + "Hay Hth\t06.09\xa0\t\t\tATTTT\t",
            t + "Hay Hth\t\t06.13\xa0\t1F93\t\t10(1)/1(2)",
            "\t" * 12 + "21(3)",
            t + "Vic (C)\t06.58\xa0\t\t\tSTABLD\t",
            t + "MILES  : (LD)\t38.30\t(ETY)\t22.29\t(TOT)\t60.59"]
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "vl11.docx"), os.path.join(d, "vl05.docx")
        write_docx(a, vl11)
        write_docx(b, vl05)
        x, y = parse_vehicle_layout(a), parse_vehicle_layout(b)
        assert (x.layout, y.layout) == ("VL11", "VL05")
        (dx,), (dy,) = x.diagrams, y.diagrams
        assert (dx.key, dx.days_code, dx.start, dx.end, dx.total) == ("BI1", "SO", "19/12/2026", "15/05/2027", 60.59)
        assert [r.loc for r in dx.rows] == ["BRHM", "HYWRDSH", "HYWRDSH", "VICTRIC"]     # short names as TIPLOCs
        assert [r.miles for r in dx.rows if r.headcode] == [22.29, 38.30]                 # VL11: miles per move
        assert dy.rows[2].positions == ["10", "1", "21"] and dy.rows[0].miles is None    # VL05: no miles
        assert any("VehicleLayout05" in w for w in y.warnings)
        # several VL29 prints go in one box (a diagram in two of them is read once); other layouts are refused
        v29 = os.path.join(d, "v29.docx")
        write_docx(v29, plan_lines())
        p29 = parse_vehicle_layout(v29)
        both = _read_trents([v29, v29], lambda m: None)
        assert both.layout == "VL29" and len(both.diagrams) == len(p29.diagrams)
        for other in (a, b):
            try:
                _read_trents([v29, other], lambda m: None)
                raise AssertionError("only VehicleLayout29 prints are used")
            except TrentFormatError as exc:
                assert "VehicleLayout29" in str(exc)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_stp_inferred_week_names_and_new_locations():
    """VL23 / 11 / 05 print no LTP / STP: a diagram for a week or less is taken as STP, a print of only
    such diagrams is named by its railway week, and the week 37 names are known."""
    from rstools.statspack.engine import timetable
    t = "\t" * 7
    lines = ["\t" * 6 + "Diagram  :\tBI\t1\tTO\t387/3", "\t\t\tRuns from:\t15/12/2026 until 15/12/2026",
             t + "Ednbg\t\t04+20\xa0\t5H92\t\t1(1)",
             t + "Pole\t06.09\xa0\t\t\tSTABLD\t",
             t + "MILES  : (LD)\t0.00\t(ETY)\t22.29\t(TOT)\t22.29",
             "\t" * 6 + "Diagram  :\tBI\t2\tSX\t387/3", "\t\t\tRuns from:\t14/12/2026 until 14/05/2027",
             t + "NPoleTbSd\t\t04+20\xa0\t5H93\t\t2(1)",
             t + "North PoB\t06.09\xa0\t\t\tSTABLD\t",
             t + "MILES  : (LD)\t0.00\t(ETY)\t1.00\t(TOT)\t1.00"]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vl05.docx")
        write_docx(p, lines)
        data = parse_vehicle_layout(p)
    stp, ltp = data.diagrams
    assert (stp.plan, ltp.plan) == ("STP", "LTP")
    assert [r.loc for r in stp.rows + ltp.rows] == ["EDNB", "POLGATE", "NPLETB", "NPLE818"]
    assert timetable(data) == "DEC26"
    data.diagrams = [stp]
    assert timetable(data) == "STP wc 12 Dec 2026"


def test_stp_stabled_replaces_the_ltp_next_day_working():
    """An STP diagram ending 'Stabld' must not keep the superseded LTP version's link to another diagram."""
    from rstools.statspack.attune import AttuneData, UnitDiagram
    from rstools.statspack.units import xml_links
    x = AttuneData(path="x", plan="", start="", end="", locations={}, trains={}, diagram_days=set(), warnings=[],
                   unit_diagrams=[UnitDiagram("BI", "16", {0}, ["BI8 05+03TO (R)"], plan="L"),
                                  UnitDiagram("BI", "16", {0}, ["Stabld"], plan="S"),
                                  UnitDiagram("BI", "2", {0}, ["BI4 04+40TO"], plan="L"),
                                  UnitDiagram("BI", "2", {0}, ["BI8 04+35TO (F)"], plan="S")])
    links, stabled, _covered = xml_links(x)
    assert (0, "BI16") not in links and (0, "BI16") in stabled
    assert links[(0, "BI2")] == (1, "BI8")


def test_two_units_never_follow_into_one_diagram(monkeypatch):
    """Two next-day workings to the same diagram (a clash in the plan): one unit is followed, the clash reported."""
    from rstools.statspack import units as U
    lines = (diagram("BI", 1, "MO", "377/4", [move("LOVRSWS", "", "1", "", "05+00", "5A01BI", "1(1)", 10.0, 10.0)],
                     10.0, 0.0)
             + diagram("BI", 3, "MO", "377/4", [move("LOVRSWS", "", "1", "", "06+00", "5A05BI", "3(1)", 10.0, 10.0)],
                       10.0, 0.0)
             + diagram("BI", 2, "TO", "377/4", [move("HOVEY36", "", "1", "", "05+00", "5A03BI", "2(1)", 10.0, 10.0)],
                       10.0, 0.0))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "u.docx")
        write_docx(p, lines)
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        monkeypatch.setattr(U, "xml_links", lambda attune: ({(0, "BI1"): (1, "BI2"), (0, "BI3"): (1, "BI2")},
                                                            set(), {0, 1}))
        units, _per_day, warnings = U.follow_units(plan.trent, plan.attune, [0, 1])
        holders = [u.diagrams[0].key for u in units if "BI2" in [x.key for x in u.diagrams]]
        assert holders == ["BI1"], holders
        assert any("BI3 -> " in w and "another unit already forms" in w for w in warnings), warnings


def test_unit_followed_through_its_stabling_diagram(monkeypatch):
    """MO BI1's note skips to WO BI2, while TO BI3 (standing where BI1 stabled) also forms WO BI2: the same unit,
    so it is followed MO BI1 > TO BI3 > WO BI2 - one unit, nothing counted twice, no clash reported."""
    from rstools.statspack import units as U
    lines = (diagram("BI", 1, "MO", "377/4", [move("LOVRSWS", "", "1", "", "05+00", "5A01BI", "1(1)", 10.0, 10.0),
                                              act("HOVEY36", "1", "06+00", "STABLD")], 10.0, 0.0)
             + diagram("BI", 3, "TO", "377/4", [act("HOVEY36", "1", "00+00", "STABLD")], 0.0, 0.0)
             + diagram("BI", 2, "WO", "377/4", [move("HOVEY36", "", "1", "", "05+00", "5A03BI", "2(1)", 10.0, 10.0)],
                       10.0, 0.0))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "u.docx")
        write_docx(p, lines)
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        monkeypatch.setattr(U, "xml_links", lambda attune: ({(0, "BI1"): (2, "BI2"), (1, "BI3"): (2, "BI2")},
                                                            set(), {0, 1, 2}))
        units, _per_day, warnings = U.follow_units(plan.trent, plan.attune, [0, 1, 2])
        assert [[x.key for x in u.diagrams] for u in units] == [["BI1", "BI3", "BI2"]], units
        assert not any("another unit already forms" in w for w in warnings), warnings


def _washing_week(wash_days_a, wash_days_b):
    """Two units, each working one diagram a day Monday to Friday and stabling where it starts (no XML, so every
    link is inferred); `wash_days_*` are the days (0-4) each one is washed."""
    lines = []
    for unit, (loc, fleet, washes) in enumerate((("BRGHTN", "700/0", wash_days_a), ("EBOUSID", "377/4", wash_days_b))):
        for day in range(5):
            num = 10 * (unit + 1) + day
            rows = [move(loc, "", "1", "", "07.00", f"1B{num}SX", f"{num}(1)", 30.0, 30.0)]
            if day in washes:
                rows.append(act(loc, "4", "07+30", "WASH"))
            rows.append(act(loc, "4", "08+00", "STABLD"))
            lines += diagram("SX", num, ("MO", "TO", "WO", "ThO", "FO")[day], fleet, rows, 30.0, 0.0)
    return lines


def test_wash_and_cet_tabs_period_inferred_reasons_and_the_three_day_rule():
    from rstools.statspack.engine import unit_reports
    from rstools.statspack.units import Depots, follow_units, over_wash_limit, wash_cet_reports
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "w.docx")
        write_docx(p, _washing_week([0], [0, 4]))
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        depots = Depots.load({"BRGHTN": "Brighton"}, os.path.join(d, "none.csv"))
        units, per_day, _w = follow_units(plan.trent, None, [0, 1, 2, 3, 4], depots)
        by_key = {u.diagrams[0].key: u for u in units}
        a, b = by_key["SX10"], by_key["SX20"]
        assert len(a.diagrams) == 5 and a.links == ["inferred"] * 4
        assert (a.wash_gap, b.wash_gap) == (4, 3)                  # a: Tue-Fri unwashed; b: Tue-Thu
        assert over_wash_limit(units) == [a]                       # more than 3 days: only the first
        first = a.inferred[0]
        assert first["stabled_at"] == "Brighton (BRGHTN)" and first["forms"] == "TO SX11"
        assert first["match"] == "same location" and "No Attune XML" in first["reason"]
        reps = {r.name: r for r in wash_cet_reports(units, per_day, "week")}
        assert set(reps) == {"Washes by Unit", "Washes by Fleet", "CETs by Unit", "CETs by Fleet", "Inferred Links"}
        rule = {r[0]: r[6] for r in reps["Washes by Unit"].rows}
        assert rule["MO SX10"].startswith("More than 3") and rule["MO SX20"] == "OK"
        assert "1 unit(s) do" in reps["Washes by Unit"].note
        assert len(reps["Inferred Links"].rows) == 8
        # each day separately: the fleets for every day, with day totals and a total for all the days
        days = {r.name: r for r in wash_cet_reports(units, per_day, "days")}
        assert set(days) == {"Washes by Diagram", "Washes by Fleet", "CETs by Diagram", "CETs by Fleet"}
        rows = days["Washes by Fleet"].rows
        assert days["Washes by Fleet"].headers[:2] == ["Day", "Fleet"]
        assert [r[0] for r in rows if r[1] == "Day total"] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        assert rows[-1][:3] == ["All days", "Total", 10] and rows[-1][3] == 3        # 3 washes in the week
        # the entire timetable: only the fleet totals
        whole = wash_cet_reports(units, per_day, "timetable", ("washes",))
        assert [r.name for r in whole] == ["Washes by Fleet"] and whole[0].rows[-1][:3] == ["Total", 10, 3]
        # written: separate tabs, the over-limit units in the notes, A-Z with the notes last
        path = unit_reports(plan, opts(d, [0, 1, 2, 3, 4]), ["washes", "cets"], "week")[0][0]
        import openpyxl
        names = openpyxl.load_workbook(path).sheetnames
        assert names == sorted(n for n in names if n != "Notes") + ["Notes"], names
        assert "Washes by Unit" in names and "CETs by Unit" in names and "Inferred Links" in names
        notes = [c.value for row in openpyxl.load_workbook(path)["Notes"].iter_rows() for c in row if c.value]
        assert any("more than 3 days without a wash" in str(n) for n in notes), notes
        path = unit_reports(plan, opts(d, [0, 1, 2, 3, 4]), ["washes"], "timetable")[0][0]
        assert openpyxl.load_workbook(path).sheetnames == ["Washes by Fleet", "Notes"]


# --------------------------------------------------------------------------- #
# next-day numbers, standing diagrams, CET and fuel rules, possible slots
# --------------------------------------------------------------------------- #
_PLAN_FILES: list = []


def _plan_of(rows_by_diagram, folder):
    """Diagrams as (days, number, fleet, start, end): each starts at `start` at 07.00 on a passenger train and
    ends there (stabling at `end`)."""
    lines = []
    for days, num, fleet, start, end in rows_by_diagram:
        rows = [move(start, "", "1", "", "07.00", f"1B{num:02d}SX", f"{num}(1)", 30.0, 30.0)]
        if end:
            rows.append(act(end, "4", "08+00", "STABLD"))
        lines += diagram("SX", num, days, fleet, rows, 30.0, 0.0)
    _PLAN_FILES.append(0)                      # a new file name each time: a TRENT print is cached by name, time, size
    p = os.path.join(folder, f"n{len(_PLAN_FILES)}.docx")
    write_docx(p, lines)
    return load_plan(PlanInputs("", p), xml_optional=True)


def test_missing_next_day_number_is_inferred_only_when_one_diagram_fits():
    from rstools.statspack.units import checks_report, follow_units
    with tempfile.TemporaryDirectory() as d:
        # one possible diagram: used, and marked as missing its next-day number
        plan = _plan_of([("MO", 10, "377/4", "BRGHTN", "BRGHTN"), ("TO", 20, "377/4", "BRGHTN", "BRGHTN"),
                         ("TO", 21, "700/0", "BRGHTN", "BRGHTN")], d)
        units, _pd, warnings = follow_units(plan.trent, None, [0, 1])
        chain = next(u for u in units if u.diagrams[0].key == "SX10")
        assert [x.key for x in chain.diagrams] == ["SX10", "SX20"] and chain.links == ["inferred"]
        assert "next-day number missing" in chain.inferred[0]["reason"]
        assert not checks_report(units)
        # two possible diagrams: not followed, listed with the candidates
        plan = _plan_of([("MO", 10, "377/4", "BRGHTN", "BRGHTN"), ("TO", 20, "377/4", "BRGHTN", "BRGHTN"),
                         ("TO", 21, "377/4", "BRGHTN", "BRGHTN")], d)
        units, _pd, warnings = follow_units(plan.trent, None, [0, 1])
        first = next(u for u in units if u.diagrams[0].key == "SX10")
        assert [x.key for x in first.diagrams] == ["SX10"]
        rep = checks_report(units)[0]
        assert rep.name == "Next-Day Checks"
        row = next(r for r in rep.rows if r[1] == "SX10")
        assert row[3] == "Next-day number missing" and "TO SX20" in row[4] and "TO SX21" in row[4]
        assert any("could form more than one diagram" in w for w in warnings)
        # two units that could only form the same diagram: neither is chosen for it
        plan = _plan_of([("MO", 10, "377/4", "BRGHTN", "BRGHTN"), ("MO", 11, "377/4", "BRGHTN", "BRGHTN"),
                         ("TO", 20, "377/4", "BRGHTN", "BRGHTN")], d)
        units, _pd, _w = follow_units(plan.trent, None, [0, 1])
        assert all(len(u.diagrams) == 1 for u in units if u.diagrams[0].day == 0)
        assert any("another unit could form it too" in r[4] for r in checks_report(units)[0].rows)


def test_a_unit_that_berths_all_day_forms_the_diagram_that_leaves_after_it():
    from rstools.statspack.units import checks_report, follow_units
    with tempfile.TemporaryDirectory() as d:
        stand = lambda loc: act(loc, "1", "00+00", "STABLD")                      # noqa: E731
        lines = (diagram("SX", 10, "MO", "377/4", [move("BRGHTN", "", "1", "", "07.00", "1B10SX", "10(1)", 30.0, 30.0),
                                                   act("BRGHTN", "4", "08+00", "STABLD")], 30.0, 0.0)
                 + diagram("SX", 11, "TO", "377/4", [stand("BRGHTN")], 0.0, 0.0)
                 + diagram("SX", 12, "WO", "377/4",
                           [move("BRGHTN", "", "1", "", "07.00", "1B12SX", "12(1)", 30.0, 30.0)], 30.0, 0.0))
        p = os.path.join(d, "s.docx")
        write_docx(p, lines)
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        units, per_day, _w = follow_units(plan.trent, None, [0, 1, 2])
        assert [x.key for x in units[0].diagrams] == ["SX10", "SX11", "SX12"] and not checks_report(units)
        assert per_day[1][0].standing and not per_day[0][0].standing
        # standing in a different siding from where the unit arrived: followed, but flagged
        lines2 = (
            diagram("SX", 10, "MO", "377/4", [move("BRGHTN", "", "1", "", "07.00", "1B10SX", "10(1)", 30.0, 30.0),
                                              act("BRGHTN", "4", "08+00", "STABLD")], 30.0, 0.0)
            + diagram("SX", 11, "TO", "377/4", [stand("BRGHSID")], 0.0, 0.0)
            + diagram("SX", 12, "WO", "377/4", [move("BRGHTN", "", "1", "", "07.00", "1B12SX", "12(1)", 30.0, 30.0)],
                      30.0, 0.0))
        p = os.path.join(d, "s2.docx")                  # not the same name: a TRENT print is cached by name, time, size
        write_docx(p, lines2)
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        units, _pd, _w = follow_units(plan.trent, None, [0, 1, 2])
        assert [x.key for x in units[0].diagrams][:2] == ["SX10", "SX11"]
        rows = checks_report(units)[0].rows
        assert any(r[3] == "Berthed in a different place" and "BRGHSID" in r[4] for r in rows), rows


def test_cet_limit_counts_passenger_days_only_and_fuel_needs_real_running():
    from rstools.statspack.units import (CET_LIMIT, DayDiagram, UnitWeek, fuel_reports, over_cet_limit)

    def unit(passenger, cet_days, running=None, fuel_days=(), n=5, fleet="377/4"):
        return UnitWeek([DayDiagram(d, f"SX{d}", fleet, "L", 300, "L", 1400, 0, int(d in cet_days),
                                    int(d in fuel_days), [1380] if d in fuel_days else [],
                                    passenger=d in passenger, running_min=running) for d in range(n)])
    busy = unit(range(5), (0,))
    assert busy.cet_gap == 4 and over_cet_limit([busy]) == [busy] and CET_LIMIT == 3
    quiet = unit((0, 1, 4), (0,))                       # days 2 and 3 are not in passenger service
    assert quiet.cet_gap == 2 and not over_cet_limit([quiet])
    assert unit(range(5), (0, 3)).cet_gap == 2           # a CET starts the count again
    still, moving = unit((), (), 20, (0, 4), fleet="171/7"), unit((), (), 300, (0, 4), fleet="171/7")
    rep = {r[0]: r for r in fuel_reports([still], {"171/7"}, [0, 1, 2, 3, 4])[0].rows}
    assert rep["MO SX0"][9] == "Over 48 hours, but mostly stationary"
    rep = {r[0]: r for r in fuel_reports([moving], {"171/7"}, [0, 1, 2, 3, 4])[0].rows}
    assert rep["MO SX0"][9].startswith("Over 48 hours (") and rep["MO SX0"][6] >= 2


def test_places_where_a_wash_cet_or_fuel_could_be_added():
    from rstools.statspack.units import DayDiagram, UnitWeek, attach_possible

    def diag(key, fleet, stops, done, day=0):
        return DayDiagram(day, key, fleet, "A", 300, "A", 1400, 0, 0, 0, [], standing=False, passenger=True,
                          running_min=300, stops=stops, done=done)
    washer = UnitWeek([diag("SX1", "377/4", [("HOVE", 600, 640)], [("WASH", "HOVE", 620)])])
    long_stop = UnitWeek([diag("SX2", "377/4", [("HOVE", 700, 800), ("BRGHTN", 900, 1000)], [])])
    short_stop = UnitWeek([diag("SX3", "377/4", [("HOVE", 700, 725)], [])])
    done_here = UnitWeek([diag("SX4", "377/4", [("HOVE", 700, 800)], [("WASH", "HOVE", 710)])])
    units = [washer, long_stop, short_stop, done_here]
    per_day = {0: [u.diagrams[0] for u in units]}
    rep = attach_possible(units, per_day, {"171/7"}, [0], {"HOVE": "Hove"}, "every")[0]
    rows = [r for r in rep.rows if r[4] == "WASH"]
    assert [(r[0], r[5], r[8], r[9]) for r in rows] == [("MO SX2", "Hove", 100, 40)]   # learned: 40 min at Hove
    assert long_stop.could["WASH"] == ["Hove MO 11:40-13:20"] and not short_stop.could.get("WASH")
    assert not [r for r in rep.rows if r[4] == "FUEL"]                                  # not a diesel unit
    # only units over a limit
    for u in units:
        u.could.clear()
    assert attach_possible(units, per_day, {"171/7"}, [0], {}, "over")[0].rows == []   # nobody is over a limit
    assert attach_possible(units, per_day, {"171/7"}, [0], {}, "off") == []


def test_possible_option_in_the_unit_reports_and_command_line(capsys):
    import openpyxl
    import pytest
    import TrainPlanningTools as cli
    from rstools.statspack.engine import unit_reports
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "w.docx")
        write_docx(p, _washing_week([0], [0, 4]))
        plan = load_plan(PlanInputs("", p), xml_optional=True)
        for mode in ("every", "over", "off"):
            path = unit_reports(plan, opts(d, [0, 1, 2, 3, 4], possible=mode, output_name=f"u_{mode}"),
                                ["washes", "cets"], "week")[0][0]
            names = openpyxl.load_workbook(path).sheetnames
            assert ("Possible Washes, CETs, Fuel" in names) == (mode != "off"), (mode, names)
            heads = [c.value for c in openpyxl.load_workbook(path)["CETs by Unit"][3]]
            assert ("Could be added at" in heads) == (mode != "off") and "CET every 3 days" in heads
        with pytest.raises(SystemExit) as bad:
            cli.main(["statspack", "--trent", p, "--unit-reports", "washes", "--possible", "sometimes"])
        assert bad.value.code == 2
        with pytest.raises(SystemExit) as bad:
            cli.main(["statspack", "--trent", p, "--possible", "over"])
        assert bad.value.code == 2 and "--possible is used with --unit-reports" in capsys.readouterr().err


def test_evening_peak_runs_until_19_00():
    import json
    from rstools.statspack import stats
    a, e = stats.EVENING
    assert (a, e) == (16 * 3600, 19 * 3600)
    inside = [b for b, (lo, hi) in enumerate(stats.PEAK_BANDS) if lo <= 18 * 3600 + 59 * 60 < hi]
    after = [b for b, (lo, hi) in enumerate(stats.PEAK_BANDS) if lo <= 19 * 3600 < hi]
    assert inside == [3] and after == [4]
    with open(os.path.join(os.path.dirname(stats.__file__), "layout.json"), encoding="utf-8") as fh:
        text = fh.read()
    assert "Evening Peak (16:00 - 19:00)" in text and "17:59" not in json.dumps(json.loads(text))


def test_mileage_over_a_period_counts_each_date_and_stp_only_on_its_dates():
    """The whole timetable, a month or any dates: each date counts its day's diagrams, and an STP version of a
    diagram replaces the LTP one only on the dates it is valid for."""
    import copy

    import openpyxl
    from rstools.statspack import period as pm
    from rstools.statspack.engine import StatsPackError, period_mileage
    with tempfile.TemporaryDirectory() as d:
        plan = setup_plan(d)
        whole, _w, summary = period_mileage(plan, opts(d, [0]), "timetable", "test")
        # 13/12/2026 - 15/05/2027: 22 Mondays (BI1 50 + HE7 30 miles) and 22 Tuesdays (BI1 50 miles)
        assert "2,860.00 unit miles" in summary and os.path.basename(whole[0]).startswith("DEC26 Mileage 13-12-2026")
        unit = {r.cells[0]: r.cells for r in tab(whole[0], "Mileage by Unit").rows}
        assert unit["377/4"][3] == 44 * 50 and unit["700/0"][3] == 22 * 30
        month, _w, summary = period_mileage(plan, opts(d, [0]), "month", "test", month="January 2027")
        assert "520.00 unit miles" in summary                     # 4 Mondays and 4 Tuesdays
        ltp = next(x for x in plan.trent.diagrams if x.key == "BI1" and x.days_code == "MO")
        stp = copy.deepcopy(ltp)
        stp.plan, stp.start, stp.end = "STP", "19/12/2026", "25/12/2026"
        stp.rows = [ltp.rows[0], ltp.rows[-1]]                    # the STP version runs only the 10-mile ECS move
        plan.trent.diagrams.append(stp)
        week, _w, summary = period_mileage(plan, opts(d, [0]), "custom", "test", start="14/12/2026",
                                           end="2026-12-28")
        by_date = {r[0].date(): r for r in openpyxl.load_workbook(week[0])["Mileage by Date"].iter_rows(
            min_row=4, values_only=True) if hasattr(r[0], "date")}
        import datetime as dt
        assert by_date[dt.date(2026, 12, 14)][6] == 80 and by_date[dt.date(2026, 12, 28)][6] == 80   # LTP
        assert by_date[dt.date(2026, 12, 21)][6] == 40 and by_date[dt.date(2026, 12, 21)][3] == 1    # STP week
        assert "300.00 unit miles" in summary                     # 80 + 50, 40 + 50, 80 (Monday 28th)
        for kind, kw, msg in (("month", {"month": "July 2027"}, "outside the timetable"),
                              ("month", {"month": "Smarch"}, "not a month"),
                              ("custom", {"start": "20/12/2026", "end": "14/12/2026"}, "before the first"),
                              ("custom", {"start": "x", "end": "14/12/2026"}, "not a date"),
                              ("other", {}, "not a period")):
            with pytest.raises(StatsPackError, match=msg):
                period_mileage(plan, opts(d, [0]), kind, "test", **kw)
        assert pm.months(plan.trent)[:2] == ["December 2026", "January 2027"] and len(pm.months(plan.trent)) == 6


def test_the_window_makes_mileage_for_a_month(tmp_path, monkeypatch):
    import time
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        import cwn_compare.gui as g
        app = g.App()
    except tk.TclError:
        return                                          # no display
    try:
        monkeypatch.setattr(g.App, "open_outputs", lambda self, *_a, **_k: None)
        from rstools.statspack import gui_tab
        shown = []
        for name in ("showinfo", "showwarning", "showerror"):
            monkeypatch.setattr(gui_tab.messagebox, name, lambda *a, _n=name, **_k: shown.append((_n, a[1:2])))
        plan_dir = str(tmp_path)
        write_xml(os.path.join(plan_dir, "a.xml"))
        write_docx(os.path.join(plan_dir, "a.docx"), plan_lines())
        tab = app.stats_tab
        tab.mode.set("mileage")
        tab._mode_changed()
        assert tab.run_btn.cget("text") == "Create mileage" and str(tab.mileage_frame.winfo_manager()) == "grid"
        tab.vars["xml_a"].set(os.path.join(plan_dir, "a.xml"))
        tab.vars["trent_a"].set(os.path.join(plan_dir, "a.docx"))
        end = time.time() + 30
        while time.time() < end and not tab.month_box.cget("values"):
            app.update()
            time.sleep(0.05)
        assert "January 2027" in tab.month_box.cget("values")
        tab.mileage_month.set("January 2027")
        assert tab.mileage_kind.get() == "month"
        tab.out_dir.set(plan_dir)
        for v in tab.day_vars:
            v.set(False)                                # the days are not used for a period
        tab.run()
        end = time.time() + 60
        while time.time() < end and tab.running:
            app.update()
            time.sleep(0.05)
        assert tab.outputs and os.path.basename(tab.outputs[0]) == "DEC26 Mileage January 2027.xlsx", \
            (shown, tab.log.get("1.0", "end"))
        assert [k for k, _m in shown] == ["showinfo"]
    finally:
        app.destroy()
