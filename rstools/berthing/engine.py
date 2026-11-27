"""Berthing chart runs: make a chart from Attune XML(s), add a round of changes to a chart (an updated XML
against the original one), or compare two charts."""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Callable, List, Sequence

from rstools import naming
from rstools.fsutil import output_folder, unique_stem

from . import writer
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


def _units():
    from rstools.statspack.fleet import FleetTable
    return Units(FleetTable.load())


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


def _fill(layout: Layout, paths: Sequence[str], log: Log):
    xmls, berthing = _stays(paths, log)
    warnings = list(berthing.warnings)
    locations = load_locations()
    if locations.warning:
        warnings.append(locations.warning)
    filled = place(layout, berthing, locations, _units(), warnings)
    return xmls, filled, warnings


def _legend(stp: bool) -> List[str]:
    return writer.LEGEND + ([writer.STP_LEGEND] if stp else [])


def _save(fn, path: str):
    try:
        fn()
    except PermissionError:
        raise BerthingError(f"Cannot save {path}\nThe folder may be read-only, or a file with that name is open "
                            "in Excel.")


def generate(xml_paths: Sequence[str], layout_path: str = "", out_dir: str = "", name: str = "", issue: str = "",
             log: Log = lambda m: None, counts: bool = False,
             progress: Callable[[float, str], None] = lambda f, m: None) -> Result:
    """A new chart from an LTP XML (or an LTP and an STP XML: STP trains in bold on lavender), laid out like
    `layout_path` - or like the app's built-in layout when none is given. No change colours: the chart starts
    clean. `counts` adds the unit counts of each siding location."""
    _check_paths(list(xml_paths), "Attune XML")
    if layout_path:
        _check_paths([layout_path], "chart to take the layout from")
        log(f"Reading the layout of {os.path.basename(layout_path)}")
        layout = read_chart(layout_path, load_locations())
    else:
        layout = load_default()
        log(f"Using {layout.path}")
    _clear_units(layout)
    progress(0.1, "Reading the timetable...")
    xmls, filled, warnings = _fill(layout, xml_paths, log)
    progress(0.6, "Writing the chart...")
    stp = len(xml_paths) > 1
    default = f"Berthing Chart {issue}".strip() if issue else "Berthing Chart " + (_timetable(xmls) or naming.today())
    path = _out(out_dir, name, default + (" STP" if stp and "stp" not in default.lower() else ""))
    first = xmls[-1]
    _save(lambda: writer.write(filled, path, writer.cover_rewriter(issue, first.start, first.end), _legend(stp),
                               _notes(xml_paths, layout_path or layout.path, warnings), counts), path)
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
    log("Original timetable:")
    progress(0.15, "Reading the original timetable...")
    _x0, before, _w0 = _fill(chart, original, log)
    log("Updated timetable:")
    progress(0.4, "Reading the updated timetable...")
    xmls, after, warnings = _fill(chart, updated, log)
    progress(0.65, "Finding the changes...")
    changes, marked = diff(before, after)
    highlight(after, marked, colour.upper())
    carry_colours(chart, after, skip=[STP_FILL])
    stem = os.path.splitext(os.path.basename(chart_path))[0]
    path = _out(out_dir, name, f"{stem} - {issue}" if issue else f"{stem} updated")
    report = os.path.splitext(path)[0] + " - Change Report.xlsx"
    shade = colour_name(colour) or f"#{colour.upper()[-6:]}"
    first = xmls[-1]
    rewrite = writer.cover_rewriter(issue, first.start, first.end)
    cover = lambda t: _updates_line(rewrite(t), shade)
    progress(0.75, "Writing the chart...")
    _save(lambda: writer.write(after, path, cover, _legend(len(updated) > 1),
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
    about = [("Older chart", os.path.basename(old_path)), ("Newer chart", os.path.basename(new_path)),
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

