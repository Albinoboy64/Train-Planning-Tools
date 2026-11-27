"""Berthing chart runs: make a chart from Attune XML(s), add a round of changes to a chart (an updated XML
against the original one), or compare two charts."""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Callable, List, Sequence

from rstools import naming
from rstools.fsutil import output_folder, unique_stem

from . import auto, writer
from .chart import Units, place
from .compare import carry_colours, colour_name, diff, highlight, write_report
from .layout import Layout, load_default, read_chart
from .mapping import load as load_locations
from .stays import build
from .xmlread import BerthingError, read_xml

STP_FILL = "E4DFEC"
Log = Callable[[str], None]


@dataclass
class Result:
    chart: str
    report: str = ""
    summary: str = ""
    warnings: List[str] = field(default_factory=list)


def _table():
    from rstools.statspack.fleet import FleetTable
    return FleetTable.load()


def _check_paths(paths: Sequence[str], what: str):
    if not paths or not all(paths):
        raise BerthingError(f"Choose the {what}.")
    for p in paths:
        if not os.path.isfile(p):
            raise BerthingError(f"This file could not be found:\n{p}")


def _out(folder: str, name: str, default: str, tails=(".xlsx",)) -> str:
    folder = output_folder(folder)
    return os.path.join(folder, unique_stem(folder, naming.clip(name or default), tails) + tails[0])


def _stays(paths: Sequence[str], log: Log):
    xmls = []
    for i, p in enumerate(paths):
        log(f"Reading {os.path.basename(p)}")
        xmls.append(read_xml(p, i))
    return xmls, build(xmls, mark_stp=len(xmls) > 1)


def _fill(layout: Layout, paths: Sequence[str], log: Log, fleets=None, read=None):
    xmls, berthing = read if read is not None else _stays(paths, log)
    warnings = list(berthing.warnings)
    locations = load_locations()
    if locations.warning:
        warnings.append(locations.warning)
    filled = place(layout, berthing, auto.with_auto_berths(locations, layout), Units(_table()), warnings, fleets)
    return xmls, filled, warnings


def _legend(stp: bool, operator: str = "SNGX") -> List[str]:
    lines = writer.LEGEND if operator.upper() == "SNGX" else writer.LEGEND[1:]     # 387/2 and 387/3 colours: SNGX
    return lines + ([writer.STP_LEGEND] if stp else [])


def _names(xmls) -> dict:
    out: dict = {}
    for x in xmls:
        out.update(x.locations)
    return out


def _operator_of(layout: Layout) -> str:
    """TLGN for a chart whose cover names Thameslink, else SNGX."""
    text = " ".join(t for r in layout.cover for (t, *_x) in r.cells.values()).casefold()
    return "TLGN" if "thameslink" in text else "SNGX"


def choose_sheets(layout: Layout, xmls, berthing, operator: str, table, leave_out: Sequence[str] = (),
                  add: Sequence[str] = ()) -> List[str]:
    """The layout's sheets for the chart: for TLGN, one for every place TLGN units berth overnight (not depots);
    less the sheets left out (by name or TIPLOC), plus a sheet for each location added (by name or TIPLOC).
    Returns warnings."""
    from rstools.statspack.units import Depots
    names = _names(xmls)
    fleets = auto.operator_fleets(operator, table)
    warnings: List[str] = []
    if operator.upper() != "SNGX":
        found = auto.places(berthing, names, Depots.load(names), (), fleets)
        layout.sheets = []
        for p in sorted((p for p in found if not p.depot), key=lambda p: p.name):
            name = auto.sheet_name(p.name, p.tiploc, [s.name for s in layout.sheets])
            layout.sheets.append(auto.make_sheet(name, p.tiploc, berthing, fleets))
    out = {auto.norm(x) for x in leave_out if x.strip()}
    if out:
        layout.sheets = [s for s in layout.sheets
                         if auto.norm(s.name) not in out and auto.norm(auto.sheet_tiploc(s)) not in out]
    if add:
        locations = auto.with_auto_berths(load_locations(), layout)
        on = auto.charted_tiplocs(layout, locations)
        known = {s.loc for s in berthing.stays}
        for text in (t for t in add if t.strip()):
            tip = auto.find_place(text, names, known)
            if not tip:
                warnings.append(f"'{text}' is not a location in the XML, so it was not added. Use its TIPLOC or "
                                "its name as the XML gives it.")
            elif tip in on:
                warnings.append(f"{names.get(tip, tip)} ({tip}) is already on the chart, so it was not added again.")
            else:
                name = auto.sheet_name(names.get(tip, tip), tip, [s.name for s in layout.sheets])
                layout.sheets.append(auto.make_sheet(name, tip, berthing, fleets))
                on.add(tip)
                if not any(s.loc == tip and (fleets is None or s.fleet in fleets) for s in berthing.stays):
                    warnings.append(f"No units berth overnight at {name} in the XML, so its sheet is empty.")
    return warnings


def find_places(xml_paths: Sequence[str], operator: str = "SNGX", layout_path: str = "",
                log: Log = lambda m: None) -> List[auto.Place]:
    """Where units (of the operator's types) berth overnight in the XML(s), for choosing the chart's locations;
    `on_chart` marks those the chart already has a sheet for."""
    from rstools.statspack.units import Depots
    _check_paths(list(xml_paths), "Attune XML")
    xmls, berthing = _stays(xml_paths, log)
    names = _names(xmls)
    table = _table()
    on: set = set()
    if operator.upper() == "SNGX":
        layout = read_chart(layout_path, load_locations()) if layout_path else load_default()
        on = auto.charted_tiplocs(layout, auto.with_auto_berths(load_locations(), layout))
    return auto.places(berthing, names, Depots.load(names), on, auto.operator_fleets(operator, table))


def _save(fn, path: str):
    from rstools.fsutil import save_output
    save_output(fn, path, BerthingError)


def generate(xml_paths: Sequence[str], layout_path: str = "", out_dir: str = "", name: str = "", issue: str = "",
             log: Log = lambda m: None, counts: bool = False,
             progress: Callable[[float, str], None] = lambda f, m: None, operator: str = "SNGX",
             leave_out: Sequence[str] = (), add: Sequence[str] = ()) -> Result:
    """A new chart from an LTP XML (or an LTP and an STP XML: STP trains in bold on lavender), laid out like
    `layout_path` - or like the app's built-in layout when none is given. No change colours: the chart starts
    clean. `counts` adds the unit counts of each siding location.
    operator: SNGX (the built-in layout) or TLGN (a sheet for every place TLGN units berth overnight, made from
    the XML, and only TLGN units). leave_out / add: sheets left out of the layout, and locations added to it
    (by name or TIPLOC). The cover's title is the timetable the XML is for and its issue line `issue`."""
    operator = (operator or "SNGX").upper()
    if operator not in auto.OPERATORS:
        raise BerthingError(f"'{operator}' is not a chart type: use " + " or ".join(auto.OPERATORS) + ".")
    _check_paths(list(xml_paths), "Attune XML")
    if layout_path and operator != "SNGX":
        raise BerthingError(f"A {operator} chart is laid out from the XML, so it cannot take the layout of a chart.")
    if layout_path:
        _check_paths([layout_path], "chart to take the layout from")
        log(f"Reading the layout of {os.path.basename(layout_path)}")
        layout = read_chart(layout_path, load_locations())
    else:
        layout = load_default()
        log(f"Using {layout.path}" if operator == "SNGX" else f"Making the {operator} sheets from the XML")
    _clear_units(layout)
    progress(0.1, "Reading the timetable...")
    read = _stays(xml_paths, log)
    xmls, berthing = read
    table = _table()
    if operator != "SNGX":
        layout.cover = auto.operator_cover(layout.cover, operator, table)
    picked = choose_sheets(layout, xmls, berthing, operator, table, leave_out, add)
    if not layout.sheets:
        raise BerthingError("No locations are left on the chart. Choose at least one location.")
    first = xmls[-1]
    layout.cover = auto.set_cover(layout.cover, auto.timetable_name(first.start), issue, clear_issue=True)
    _x, filled, warnings = _fill(layout, xml_paths, log, auto.operator_fleets(operator, table), read)
    warnings = picked + warnings
    progress(0.6, "Writing the chart...")
    stp = len(xml_paths) > 1
    prefix = "" if operator == "SNGX" else operator + " "
    default = f"{prefix}Berthing Chart {_timetable(xmls) or naming.today()}" + (f" {issue}" if issue else "")
    path = _out(out_dir, name, default + (" STP" if stp and "stp" not in default.lower() else ""))
    where = layout_path or (layout.path if operator == "SNGX" else f"the {operator} locations in the XML")
    _save(lambda: writer.write(filled, path, writer.cover_rewriter("", first.start, first.end),
                               _legend(stp, operator), _notes(xml_paths, where, warnings), counts), path)
    n = _count(filled)
    return Result(path, "", f"{n} unit stay(s) placed on {len(filled.sheets)} sheet(s)." +
                  (" STP trains are in bold on lavender." if stp else ""), warnings)


def add_round(chart_path: str, original: Sequence[str], updated: Sequence[str], colour: str, out_dir: str = "",
              name: str = "", issue: str = "", log: Log = lambda m: None, counts: bool = False,
              progress: Callable[[float, str], None] = lambda f, m: None) -> Result:
    """The chart remade from the updated XML(s), with every cell that differs from the original XML(s)
    filled in `colour`, and the chart's earlier highlights kept where nothing changed. Plus a change report."""
    _check_paths([chart_path], "berthing chart to add the changes to")
    _check_paths(list(original), "original Attune XML")
    _check_paths(list(updated), "updated Attune XML")
    log(f"Reading {os.path.basename(chart_path)}")
    progress(0.03, "Reading the chart...")
    chart = read_chart(chart_path, load_locations())
    operator = _operator_of(chart)
    fleets = auto.operator_fleets(operator, _table())
    log("Original timetable:")
    progress(0.15, "Reading the original timetable...")
    _x0, before, _w0 = _fill(chart, original, log, fleets)
    log("Updated timetable:")
    progress(0.4, "Reading the updated timetable...")
    xmls, after, warnings = _fill(chart, updated, log, fleets)
    progress(0.65, "Finding the changes...")
    changes, marked = diff(before, after)
    highlight(after, marked, colour.upper())
    carry_colours(chart, after, skip=[STP_FILL])
    stem = os.path.splitext(os.path.basename(chart_path))[0]
    path = _out(out_dir, name, f"{stem} - {issue}" if issue else f"{stem} updated")
    report = os.path.splitext(path)[0] + " - Change Report.xlsx"
    shade = colour_name(colour) or f"#{colour.upper()[-6:]}"
    first = xmls[-1]
    after.cover = auto.set_cover(after.cover, auto.timetable_name(first.start), issue, clear_issue=False)
    rewrite = writer.cover_rewriter("", first.start, first.end)
    cover = lambda t: _updates_line(rewrite(t), shade)
    progress(0.75, "Writing the chart...")
    _save(lambda: writer.write(after, path, cover, _legend(len(updated) > 1, operator),
                               _notes(list(updated), chart_path, warnings), counts), path)
    about = [("Chart", os.path.basename(path)), ("Original XML", ", ".join(map(os.path.basename, original))),
             ("Updated XML", ", ".join(map(os.path.basename, updated))), ("Highlight colour", shade),
             ("Made", f"{datetime.datetime.now():%d/%m/%Y %H:%M}")]
    progress(0.92, "Writing the change report...")
    _save(lambda: write_report(report, changes, "Berthing chart changes", about), report)
    return Result(path, report, f"{len(changes)} change(s) highlighted in {shade}.", warnings)


def compare_charts(old_path: str, new_path: str, colour: str, out_dir: str = "", name: str = "",
                   log: Log = lambda m: None, counts: bool = False,
                   progress: Callable[[float, str], None] = lambda f, m: None) -> Result:
    """The newer chart, tidied, with every cell that differs from the older one filled in `colour` (its own
    earlier highlights kept), and a change report."""
    _check_paths([old_path, new_path], "two berthing charts")
    if os.path.abspath(old_path) == os.path.abspath(new_path):
        raise BerthingError("The two charts selected are the same file.")
    locations = load_locations()
    log(f"Reading {os.path.basename(old_path)}")
    progress(0.05, "Reading the older chart...")
    old = read_chart(old_path, locations)
    log(f"Reading {os.path.basename(new_path)}")
    progress(0.35, "Reading the newer chart...")
    new = read_chart(new_path, locations)
    progress(0.65, "Finding the changes...")
    changes, marked = diff(old, new)
    highlight(new, marked, colour.upper())
    a, b = (naming.short_label(p) for p in (old_path, new_path))
    path = _out(out_dir, name, f"{naming.today()} {naming.vs(a, b)}")
    report = os.path.splitext(path)[0] + " - Change Report.xlsx"
    shade = colour_name(colour) or f"#{colour.upper()[-6:]}"
    progress(0.75, "Writing the chart...")
    _save(lambda: writer.write(new, path, lambda t: _updates_line(t, shade), (), [], counts), path)
    about = [("Original chart", os.path.basename(old_path)), ("Updated chart", os.path.basename(new_path)),
             ("Highlight colour", shade), ("Made", f"{datetime.datetime.now():%d/%m/%Y %H:%M}")]
    progress(0.92, "Writing the change report...")
    _save(lambda: write_report(report, changes, "Berthing chart changes", about), report)
    return Result(path, report, f"{len(changes)} difference(s) between the charts, highlighted in {shade}.", [])


def _updates_line(text: str, shade: str) -> str:
    import re
    return re.sub(r"(?i)^(updates highlighted in )\w[\w ]*$", lambda m: m.group(1) + shade.lower(), text)


def _clear_units(layout: Layout):
    """A new chart starts without highlights (the layout chart's units are replaced anyway)."""
    for sheet in layout.sheets:
        for blk in sheet.blocks:
            if hasattr(blk, "units"):
                blk.units = {}


def _count(layout: Layout) -> int:
    n = 0
    for sheet in layout.sheets:
        for blk in sheet.blocks:
            for row in getattr(blk, "units", {}).values():
                n += sum(1 for c in row[::2] if c is not None and c.text and "Berth" not in c.text
                         and c.text.split(")")[-1].strip()[:1].isdigit())
    return n


def _timetable(xmls) -> str:
    starts = [x.start for x in xmls if x.start]
    if not starts:
        return ""
    try:
        d = datetime.date.fromisoformat(starts[-1])
    except ValueError:
        return ""
    return f"{naming.MONTHS[d.month - 1].title()} {d:%y}"


def _notes(xmls: Sequence[str], layout_path: str, warnings: Sequence[str]) -> List[str]:
    where = layout_path if layout_path.startswith("the built-in") else os.path.basename(layout_path)
    lines = [f"Made {datetime.datetime.now():%d/%m/%Y %H:%M} from " + ", ".join(map(os.path.basename, xmls))
             + f", in the layout of {where}."]
    if len(xmls) > 1:
        lines.append("LTP and STP: each day's STP diagrams replace the LTP ones; STP trains are in bold on lavender.")
    lines += list(warnings) or ["Nothing needs checking."]
    return lines



def layout_sheets(layout_path: str = "") -> List[str]:
    """The location sheets of the chart's layout (the built-in one when no chart is given)."""
    layout = read_chart(layout_path, load_locations()) if layout_path else load_default()
    return [s.name for s in layout.sheets]
