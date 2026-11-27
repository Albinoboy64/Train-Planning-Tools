"""Berthing chart runs: make a chart from Attune XML(s), add a round of changes to a chart (an updated XML
against the original one), or compare two charts."""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from rstools import naming
from rstools.fsutil import output_folder, unique_stem

from . import auto, writer
from .chart import Units, place
from .compare import carry_colours, colour_name, diff, highlight, write_report
from .layout import GridSheet, Layout, read_chart
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


def _fill(layout: Layout, paths: Sequence[str], log: Log, fleets=None, read=None, extra=None):
    """The layout filled from the XML(s); `extra`: other operators' (stays, warnings, names) added to it."""
    import dataclasses
    xmls, berthing = read if read is not None else _stays(paths, log)
    warnings = list(berthing.warnings)
    if extra is not None and extra[0]:
        berthing = dataclasses.replace(berthing, stays=list(berthing.stays) + list(extra[0]))
    if extra is not None:
        warnings += extra[1]
    locations = load_locations()
    if locations.warning:
        warnings.append(locations.warning)
    filled = place(layout, berthing, auto.with_auto_berths(locations, layout), Units(_table()), warnings, fleets)
    return xmls, filled, warnings


def _legend(stp: bool, operator: str = "SNGX", others: bool = False) -> List[str]:
    lines = writer.LEGEND if operator.upper() == "SNGX" else writer.LEGEND[1:]     # 387/2 and 387/3 colours: SNGX
    return lines + ([writer.STP_LEGEND] if stp else []) + ([writer.OTHERS_LEGEND] if others else [])


def _others(paths: Sequence[str], log: Log):
    """Other operators' stays, or None when no files are given."""
    if not paths:
        return None
    from .others import other_stays
    return other_stays(list(paths), log)


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
                  add: Sequence[str] = (), names: Optional[dict] = None, blank: bool = False,
                  from_xml: Optional[bool] = None) -> List[str]:
    """The layout's sheets for the chart: made from the XML (`from_xml`; by default for TLGN when it has no saved
    location set), one for every place the operator's units berth overnight (not depots);
    less the sheets left out (by name or TIPLOC), plus a sheet for each location added (by name or TIPLOC).
    names: the location names to find an added location in (default: the XMLs'). blank: a blank chart (no
    warning that a sheet has no units). Returns warnings."""
    from rstools.statspack.units import Depots
    names = _names(xmls) if names is None else names
    fleets = auto.operator_fleets(operator, table)
    warnings: List[str] = []
    if from_xml is None:
        from . import sets
        from_xml = operator.upper() != "SNGX" and not sets.has_set(operator)
    if from_xml:
        found = auto.places(berthing, names, Depots.load(names), (), fleets)
        layout.sheets = []
        for station, group in auto.station_groups([p for p in found if not p.depot]):
            name = auto.sheet_name(station, group[0].tiploc, [s.name for s in layout.sheets])
            layout.sheets.append(auto.make_group_sheet(name, group, berthing, fleets))
    out = {auto.norm(x) for x in leave_out if x.strip()}
    if out:                         # a sheet by name; a location (TIPLOC) on its own sheet or within a station's
        kept = []
        for s in layout.sheets:
            if auto.norm(s.name) in out:
                continue
            if isinstance(s, GridSheet) and (auto.sheet_tiplocs(s) or any(b.tiploc for b in s.blocks)):
                auto.drop_locations(s, out)
                if not s.blocks:
                    continue
            kept.append(s)
        layout.sheets = kept
    if add:
        locations = auto.with_auto_berths(load_locations(), layout)
        on = auto.charted_tiplocs(layout, locations)
        known = {s.loc for s in berthing.stays}
        for text in (t for t in add if t.strip()):
            tip = auto.find_place(text, names, known)
            if not tip:
                where = "the XML" if xmls else "the app's location list"
                warnings.append(f"'{text}' is not a location in {where}, so it was not added. Use its TIPLOC or "
                                f"its name as {where} gives it.")
            elif tip in on:
                warnings.append(f"{names.get(tip, tip)} ({tip}) is already on the chart, so it was not added again.")
            else:
                name = auto.sheet_name(names.get(tip, tip), tip, [s.name for s in layout.sheets])
                layout.sheets.append(auto.make_sheet(name, tip, berthing, fleets, auto.known_berths(tip)))
                on.add(tip)
                if not blank and not any(s.loc == tip and (fleets is None or s.fleet in fleets)
                                         for s in berthing.stays):
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
    from . import sets
    if operator.upper() == "SNGX" or sets.has_set(operator):
        layout = read_chart(layout_path, load_locations()) if layout_path else sets.base_layout(operator)
        on = auto.charted_tiplocs(layout, auto.with_auto_berths(load_locations(), layout))
    return auto.places(berthing, names, Depots.load(names), on, auto.operator_fleets(operator, table))


def _save(fn, path: str):
    from rstools.fsutil import save_output
    save_output(fn, path, BerthingError)


def generate(xml_paths: Sequence[str], layout_path: str = "", out_dir: str = "", name: str = "", issue: str = "",
             log: Log = lambda m: None, counts: bool = False,
             progress: Callable[[float, str], None] = lambda f, m: None, operator: str = "SNGX",
             leave_out: Sequence[str] = (), add: Sequence[str] = (), others: Sequence[str] = (),
             show_notes: bool = True) -> Result:
    """A new chart from an LTP XML (or an LTP and an STP XML: STP trains in bold on lavender), laid out like
    `layout_path` - or like the app's built-in layout when none is given. No change colours: the chart starts
    clean. `counts` adds the unit counts of each siding location.
    operator: SNGX (the built-in layout) or TLGN (a sheet for every place TLGN units berth overnight, made from
    the XML, and only TLGN units). leave_out / add: sheets left out of the layout, and locations added to it
    (by name or TIPLOC). The cover's title is the timetable the XML is for and its issue line `issue`.
    others: other operators' files (Attune XML, VPT or CIF) whose units are added in grey (rstools.berthing.others).
    show_notes: the location notes, with any edited in the app for the XML's timetable (berthing.notes); False
    leaves every note off."""
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
        from . import sets
        layout = sets.base_layout(operator)
        log(f"Using {layout.path}" if operator == "SNGX" or sets.has_set(operator)
            else f"Making the {operator} sheets from the XML")
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
    extra = _others(others, log)
    _x, filled, warnings = _fill(layout, xml_paths, log, auto.operator_fleets(operator, table), read, extra)
    warnings = picked + warnings
    _location_notes(filled, xmls, show_notes, log, operator)
    progress(0.6, "Writing the chart...")
    stp = len(xml_paths) > 1
    prefix = "" if operator == "SNGX" else operator + " "
    default = f"{prefix}Berthing Chart {_timetable(xmls) or naming.today()}" + (f" {issue}" if issue else "")
    path = _out(out_dir, name, default + (" STP" if stp and "stp" not in default.lower() else ""))
    where = layout_path or (layout.path if not layout.path.startswith("the built-in") or operator == "SNGX"
                            else f"the {operator} locations in the XML")
    _save(lambda: writer.write(filled, path, writer.cover_rewriter("", first.start, first.end),
                               _legend(stp, operator, bool(others)), _notes(xml_paths, where, warnings, others),
                               counts), path)
    n = _count(filled)
    return Result(path, "", f"{n} unit stay(s) placed on {len(filled.sheets)} sheet(s)." +
                  (" STP trains are in bold on lavender." if stp else ""), warnings)


def blank(operator: str = "SNGX", layout_path: str = "", xml_paths: Sequence[str] = (), out_dir: str = "",
          name: str = "", issue: str = "", timetable: str = "", start: str = "", end: str = "",
          leave_out: Sequence[str] = (), add: Sequence[str] = (), log: Log = lambda m: None,
          progress: Callable[[float, str], None] = lambda f, m: None, show_notes: bool = True) -> Result:
    """A blank berthing chart: the sheets, berths, capacities and notes with no units, to fill in by hand.
    SNGX: the built-in layout or your saved location set (or the layout of `layout_path`). TLGN: your saved
    location set; with none, a sheet for every place TLGN units berth overnight in the XML(s) given (not depots),
    or with no XML only the locations added. The location notes are shown unless `show_notes` is False.
    leave_out / add as for generate(); an added location is found in the XML(s), else in the app's location
    list, and its berths come from the XML, else from the berth list. The cover's title is the timetable (from
    the XML, else `timetable`) and its dates those of the XML (else start / end, ISO dates, or none)."""
    operator = (operator or "SNGX").upper()
    if operator not in auto.OPERATORS:
        raise BerthingError(f"'{operator}' is not a chart type: use " + " or ".join(auto.OPERATORS) + ".")
    if layout_path and operator != "SNGX":
        raise BerthingError(f"A {operator} chart has no layout of its own, so it cannot take the layout of a chart.")
    if xml_paths:
        _check_paths(list(xml_paths), "Attune XML")
    for iso in (start, end):
        if iso:
            try:
                datetime.date.fromisoformat(iso)
            except ValueError:
                raise BerthingError(f"'{iso}' is not a date: use YYYY-MM-DD.")
    if layout_path:
        _check_paths([layout_path], "chart to take the layout from")
        log(f"Reading the layout of {os.path.basename(layout_path)}")
        layout = read_chart(layout_path, load_locations())
    else:
        from . import sets
        layout = sets.base_layout(operator)
    _clear_units(layout)
    progress(0.1, "Reading the locations...")
    if xml_paths:
        xmls, berthing = _stays(xml_paths, log)
    else:
        from .stays import Berthing
        xmls, berthing = [], Berthing([], {}, {}, set())
    names = _names(xmls)
    if not xmls:
        from rstools.timetable.base import load_tiplocs
        names = load_tiplocs()
    table = _table()
    if operator != "SNGX":
        layout.cover = auto.operator_cover(layout.cover, operator, table)
    warnings = choose_sheets(layout, xmls, berthing, operator, table, leave_out, add, names, blank=True)
    if not layout.sheets:
        raise BerthingError("No locations are on the chart." + (
            " A TLGN chart without an XML or a saved location set has only the locations you add: add at least one "
            "(by name or TIPLOC), choose an XML to take TLGN's berthing locations from, or make TLGN's location set in "
            "Settings > Berthing locations." if operator != "SNGX" and not xmls
            else " Choose at least one location."))
    if xmls:
        start, end = xmls[-1].start, xmls[-1].end
        timetable = auto.timetable_name(start) or timetable
    layout.cover = auto.set_cover(layout.cover, timetable.strip(), issue, clear_issue=True)
    _location_notes(layout, xmls, show_notes, log, operator, timetable)
    rewrite = writer.cover_rewriter("", start, end)
    dated = bool(start and end)

    def cover(text: str) -> str:
        import re
        if not dated and re.fullmatch(r"\s*\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s*", text):
            return ""                       # the built-in chart's own dates are not this chart's
        return rewrite(text)
    progress(0.6, "Writing the chart...")
    prefix = "" if operator == "SNGX" else operator + " "
    when = _timetable(xmls) or (timetable.strip() if timetable.strip() else "")
    default = f"{prefix}Blank Berthing Chart" + (f" {when}" if when else "") + (f" {issue}" if issue else "")
    path = _out(out_dir, name, default)
    where = layout_path or (layout.path if operator == "SNGX" else f"the {operator} locations")
    made = (f"Made {datetime.datetime.now():%d/%m/%Y %H:%M} as a blank chart, in the layout of "
            + (where if where.startswith("the ") else os.path.basename(where))
            + (" (locations from " + ", ".join(map(os.path.basename, xml_paths)) + ")" if xml_paths else "") + ".")
    _save(lambda: writer.write(layout, path, cover, _legend(False, operator), [made] + (warnings or [])), path)
    return Result(path, "", f"Blank chart with {len(layout.sheets)} location sheet(s).", warnings)


def add_round(chart_path: str, original: Sequence[str], updated: Sequence[str], colour: str, out_dir: str = "",
              name: str = "", issue: str = "", log: Log = lambda m: None, counts: bool = False,
              progress: Callable[[float, str], None] = lambda f, m: None, others: Sequence[str] = (),
              show_notes: bool = True) -> Result:
    """The chart remade from the updated XML(s), with every cell that differs from the original XML(s)
    filled in `colour`, and the chart's earlier highlights kept where nothing changed. Plus a change report.
    `show_notes` as for generate."""
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
    extra = _others(others, log)            # the same on both sides: only the chart's own trains are compared
    _x0, before, _w0 = _fill(chart, original, log, fleets, extra=extra)
    log("Updated timetable:")
    progress(0.4, "Reading the updated timetable...")
    xmls, after, warnings = _fill(chart, updated, log, fleets, extra=extra)
    progress(0.65, "Finding the changes...")
    changes, marked = diff(before, after)
    highlight(after, marked, colour.upper())
    carry_colours(chart, after, skip=[STP_FILL])
    _location_notes(after, xmls, show_notes, log, operator)
    stem = os.path.splitext(os.path.basename(chart_path))[0]
    path = _out(out_dir, name, f"{stem} - {issue}" if issue else f"{stem} updated")
    report = os.path.splitext(path)[0] + " - Change Report.xlsx"
    shade = colour_name(colour) or f"#{colour.upper()[-6:]}"
    first = xmls[-1]
    after.cover = auto.set_cover(after.cover, auto.timetable_name(first.start), issue, clear_issue=False)
    rewrite = writer.cover_rewriter("", first.start, first.end)
    cover = lambda t: _updates_line(rewrite(t), shade)
    progress(0.75, "Writing the chart...")
    _save(lambda: writer.write(after, path, cover, _legend(len(updated) > 1, operator, bool(others)),
                               _notes(list(updated), chart_path, warnings, others), counts), path)
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


def _location_notes(layout: Layout, xmls, show: bool, log: Log, operator: str = "SNGX", timetable: str = ""):
    """The notes edited in the app for the XML's timetable (or a blank chart's `timetable`, e.g. 'May 2027') on
    the chart's berths, or every note off."""
    from . import notes
    if not show:
        notes.strip(layout)
        log("Location notes left off the chart.")
        return
    starts = [x.start for x in xmls if x.start]
    tt = notes.timetable_of_start(starts[-1]) if starts else notes.timetable_of_name(timetable)
    n = notes.apply(layout, tt, operator=operator) if tt else 0
    if n:
        log(f"{n} location note(s) from the app's {notes.timetable_label(tt)} notes.")


def _timetable(xmls) -> str:
    starts = [x.start for x in xmls if x.start]
    if not starts:
        return ""
    try:
        d = datetime.date.fromisoformat(starts[-1])
    except ValueError:
        return ""
    return f"{naming.MONTHS[d.month - 1].title()} {d:%y}"


def _notes(xmls: Sequence[str], layout_path: str, warnings: Sequence[str], others: Sequence[str] = ()) -> List[str]:
    where = layout_path if layout_path.startswith("the ") else os.path.basename(layout_path)
    lines = [f"Made {datetime.datetime.now():%d/%m/%Y %H:%M} from " + ", ".join(map(os.path.basename, xmls))
             + f", in the layout of {where}."]
    if others:
        lines.append("Other operators' trains from " + ", ".join(map(os.path.basename, others)) + ".")
    if len(xmls) > 1:
        lines.append("LTP and STP: each day's STP diagrams replace the LTP ones; STP trains are in bold on lavender.")
    lines += list(warnings) or ["Nothing needs checking."]
    return lines



def make_location_set(xml_paths: Sequence[str], operator: str = "TLGN", leave_out: Sequence[str] = (),
                      add: Sequence[str] = (), log: Log = lambda m: None) -> list:
    """The sheets of a location set made from XML(s): one for every place the operator's units berth overnight
    (not depots), a berth for each platform or road used there with its codes, less `leave_out`, plus `add`.
    Saved with sets.save (Settings > Berthing locations > Make from XML...)."""
    from .layout import GridSheet, load_default
    _check_paths(list(xml_paths), "Attune XML")
    xmls, berthing = _stays(xml_paths, log)
    layout = load_default()
    warnings = choose_sheets(layout, xmls, berthing, operator, _table(), leave_out, add, from_xml=True, blank=True)
    for w in warnings:
        log("WARNING: " + w)
    for sheet in layout.sheets:
        if isinstance(sheet, GridSheet):
            for blk in sheet.blocks:
                blk.codes = blk.codes or ";".join(c for c in auto._codes(blk.label) if c)
    if not layout.sheets:
        raise BerthingError(f"No {operator} units berth overnight in the XML (away from depots), so no locations "
                            "were found.")
    return layout.sheets


def layout_sheets(layout_path: str = "", operator: str = "SNGX") -> List[str]:
    """The location sheets of the chart's layout: a chart's, else the operator's location set (the built-in
    layout for SNGX); none for TLGN with no saved set (its sheets come from the XML)."""
    from . import sets
    if not layout_path and operator.upper() != "SNGX" and not sets.has_set(operator):
        return []
    layout = read_chart(layout_path, load_locations()) if layout_path else sets.base_layout(operator)
    return [s.name for s in layout.sheets]
