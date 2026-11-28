"""Stats Pack runs: create a pack, compare two plans, compare two packs."""
from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Set, Tuple

from rstools import naming
from rstools.fsutil import output_folder

from rstools.docexport import ext_for

from .compare import CompareOptions
from .attune import AttuneData, AttuneError, parse_attune_xml
from rstools.days import DAYS, DAY_NAMES
from .fleet import FleetTable
from .model import build_day
from .stats import TAB_ORDER, Table, build_tables, weekly_tables
from .trent import FORMAT_HELP, TrentData, TrentFormatError, parse_vehicle_layout
from .output import sink_for
from .report_compare import compare_reports
from rstools.naming import agree, plural
from .output import save_sink

OUTPUTS = {
    "totals_days": "One workbook: totals for the selected days, then every day's tabs",
    "totals": "One workbook: totals for the selected days only",
    "days": "A separate workbook for each day",
}


class StatsPackError(Exception):
    pass


@dataclass
class PlanInputs:
    xml: str
    trent: str


@dataclass
class PackOptions:
    days: List[int]
    operators: Set[str]
    fleets: Optional[Set[str]]        # None = all fleets
    output: str = "totals_days"       # see OUTPUTS
    output_dir: str = ""
    output_name: str = ""
    compare: CompareOptions = field(default_factory=CompareOptions)   # comparison outputs only
    fmt: str = "xlsx"                 # xlsx | pdf | docx
    possible: str = "every"           # unit reports: where a WASH / CET / FUEL could be added - every | over | off


@dataclass
class LoadedPlan:
    trent: TrentData
    attune: AttuneData
    warnings: List[str] = field(default_factory=list)


def cached(parser, path: str):
    """parser(path), remembered while the file is unchanged - the app reads a TRENT print when it
    is chosen (to list its fleets) and again when the pack is run (rstools.filecache)."""
    from rstools import filecache
    return filecache.remember(parser, path)


def split_paths(text: str) -> List[str]:
    """Several files in one box, separated by ';' (e.g. the TLGN SX, SO and SU unit diagram prints)."""
    return [p.strip().strip('"') for p in (text or "").split(";") if p.strip().strip('"')]


def _read_trents(paths: List[str], log) -> TrentData:
    """One or more TRENT VehicleLayout29 prints read as one (e.g. the SNGX and TLGN prints, or the LTP print with a
    week's STP print). A diagram in more than one print is read once."""
    parts = []
    for p in paths:
        log(f"Reading TRENT print {os.path.basename(p)}")
        t = cached(parse_vehicle_layout, p)
        if t.layout != "VL29":
            raise TrentFormatError(f"'{os.path.basename(p)}' is a TRENT VehicleLayout{t.layout[2:]} print. "
                                   + FORMAT_HELP)
        parts.append(t)
    if len(parts) == 1:
        return parts[0]
    seen, diagrams, warnings = set(), [], []
    for t in parts:
        warnings += t.warnings
        for d in t.diagrams:
            key = (d.key, d.days_code, d.plan, d.start, tuple((r.headcode, r.dep) for r in d.rows[:3]))
            if key not in seen:
                seen.add(key)
                diagrams.append(d)
    return TrentData(parts[0].path, diagrams, warnings, "VL29")


def empty_attune() -> AttuneData:
    """No XML: trains and next-day workings come from the TRENT print alone; location names from the built-in
    lists (the GTR locations of the Dec 26 plan, and the TRENT names)."""
    from rstools.timetable.base import load_tiplocs
    from .trent import name_table
    names = dict(name_table()["name"])
    names.update(load_tiplocs())
    return AttuneData(path="", plan="", start="", end="", locations=names, trains={}, diagram_days=set(), warnings=[])


def load_plan(inputs: PlanInputs, log: Callable[[str], None] = lambda m: None,
              xml_optional: bool = False) -> LoadedPlan:
    trents = split_paths(inputs.trent)
    if not trents:
        raise StatsPackError("Choose the TRENT unit diagram print.")
    for p in trents:
        if not os.path.isfile(p):
            raise StatsPackError(f"The TRENT print could not be found:\n{p}")
    if not (xml_optional and not inputs.xml) and (not inputs.xml or not os.path.isfile(inputs.xml)):
        raise StatsPackError("Choose the Attune XML file.")
    try:
        trent = _read_trents(trents, log)
        if inputs.xml:
            log(f"Reading Attune XML {os.path.basename(inputs.xml)}")
            attune = cached(parse_attune_xml, inputs.xml)
        else:
            attune = empty_attune()
    except (TrentFormatError, AttuneError) as exc:
        raise StatsPackError(str(exc))
    warnings = list(trent.warnings) + list(attune.warnings)
    # same-plan sanity check: how many TRENT headcodes exist in the XML at all
    # (only days covered by both files, so a single-day XML is not flagged)
    common = trent.days() & attune.days()
    heads = {r.headcode for d in trent.diagrams if d.days & common for r in d.rows if r.headcode}
    if heads:
        short = {h[:4] for h in attune.trains}                 # TLGN prints give 4-character headcodes
        found = sum(1 for h in heads if h in attune.trains or (len(h) == 4 and h in short))
        if found / len(heads) < 0.8:
            warnings.append(f"Only {found} of {len(heads)} headcodes in the TRENT print are in the XML - the XML "
                            "and the TRENT print may not be from the same plan.")
    return LoadedPlan(trent, attune, warnings)


def day_availability(plan: LoadedPlan, days: Sequence[int]) -> List[str]:
    """Messages for ticked days missing from the TRENT print or the XML."""
    msgs = []
    t_days, x_days = plan.trent.days(), plan.attune.days()
    sources = (("TRENT print", t_days),) + ((("XML", x_days),) if plan.attune.path else ())
    for d in days:
        missing = [src for src, have in sources if d not in have]
        if missing:
            msgs.append(f"{DAY_NAMES[d]} ({DAYS[d]}) is not in the {' or the '.join(missing)}.")
    return msgs


def default_name() -> str:
    """Fallback name when the timetable cannot be worked out."""
    return naming.today() + " Stats Pack"


def timetable(trent: TrentData) -> str:
    """The timetable a TRENT print is for, from its diagrams' start dates, e.g. 'DEC26'; a print of
    short-term diagrams only (a week's STP) is named by its week, e.g. 'STP wc 12 Dec 2026'."""
    from datetime import datetime, timedelta
    from .trent import _span_days
    ds = trent.diagrams
    if ds and all(0 <= _span_days(d.start, d.end) <= 6 for d in ds):
        try:
            first = min(datetime.strptime(d.start, "%d/%m/%Y") for d in ds)
        except ValueError:
            first = None
        if first is not None:
            sat = first - timedelta(days=(first.weekday() - 5) % 7)       # railway weeks run Saturday to Friday
            return f"STP wc {sat.day} {sat:%b %Y}"
    return naming.timetable_of(d.start for d in ds)


def pack_name(trent: TrentData, days: Sequence[int] = ()) -> str:
    """'Stats pack for DEC26' (plus the day code for a single-day pack)."""
    tt = timetable(trent)
    if not tt:
        return default_name()
    return f"Stats pack for {tt}" + (f" {DAYS[days[0]]}" if len(days) == 1 else "")


def plans_name(old: TrentData, new: TrentData, old_xml: str = "", new_xml: str = "", days: Sequence[int] = ()) -> str:
    """'DEC26 vs MAY27'; when both are the same timetable, the (shortened) file names."""
    a, b = timetable(old), timetable(new)
    name = (naming.pick_vs((a, b), (naming.short_label(old.path), naming.short_label(new.path)),
                           (naming.short_label(old_xml), naming.short_label(new_xml)))
            or (naming.vs(a, b) if a else naming.today() + " Comparison"))
    return naming.clip(name + (f" {DAYS[days[0]]}" if len(days) == 1 else ""))


def packs_name(old_path: str, new_path: str) -> str:
    """'<original pack> vs <updated pack>', shortened."""
    a, b = naming.short_label(old_path), naming.short_label(new_path)
    return naming.clip(naming.pick_vs((a, b)) or naming.vs(a, b))


def _safe(name: str) -> str:
    return naming.output_stem(name)


def unique_path(folder: str, stem: str, ext: str = ".xlsx") -> str:
    """folder/stem.ext, shortened if needed so Excel can open it, with ' (2)'... if it already exists."""
    from rstools.fsutil import unique_stem
    return os.path.join(folder, unique_stem(folder, stem, (ext,)) + ext)


def _info(plan: LoadedPlan, version: str) -> dict:
    return {"version": version, "created": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "inputs": f"Attune XML: {plan.attune.path}\nTRENT print: {plan.trent.path}"}


def build_pack(plan: LoadedPlan, opts: PackOptions, version: str,
               progress: Callable[[float, str], None] = lambda f, m: None
               ) -> Tuple[List[Tuple[int, List[Table]]], List[str]]:
    fleet = FleetTable.load()
    info = _info(plan, version)
    per_day, warnings = [], ([fleet.warning] if fleet.warning else [])
    xml_days = plan.attune.days()
    no_cars: set = set()
    for i, d in enumerate(opts.days):
        progress(0.1 + 0.6 * i / max(len(opts.days), 1), f"Building {DAY_NAMES[d]}...")
        # a day missing from the XML is reported once (day_availability), not train by train
        model = build_day(plan.trent, plan.attune, fleet, d, opts.operators, opts.fleets,
                          report_missing=d in xml_days)
        if not model.diagrams:
            warnings.append(f"{DAY_NAMES[d]}: no diagrams for the selected operators and fleets.")
            continue
        warnings += [f"{DAY_NAMES[d]}: {w}" for w in model.warnings]
        no_cars |= {dg.fleet for dg in model.diagrams if dg.cars is None}
        per_day.append((d, build_tables(model, info)))
    if no_cars:                         # reported once, not day by day
        warnings.append(f"Fleet(s) {', '.join(sorted(no_cars))} in the TRENT print are not in the fleet table, so "
                        "their vehicle figures and the vehicle totals show as ??? (unknown). Add them with 'Edit "
                        "fleet data' if they should be counted.")
    return per_day, warnings


def _plan_books(days: List[int], opts: PackOptions, stem: str):
    """[(file stem, [(sheet name, title, tab name, day or 'week')])] for the chosen output.
    A single day always gives one single-day workbook in the TRACS-RS layout."""
    def day_tabs(d, prefix):
        return [((f"{DAYS[d]} {n}"[:31] if prefix else n), _title(n) + (f" - {DAY_NAMES[d]}" if prefix else ""), n, d)
                for n in TAB_ORDER if not (prefix and n == "Glossary")]
    if len(days) == 1:
        return [(stem, day_tabs(days[0], False))]
    if opts.output == "days":
        return [(f"{stem} {DAYS[d]}", day_tabs(d, False)) for d in days]
    span = "+".join(DAYS[d] for d in days)
    week = [(n, _title(n) + ("" if n == "Glossary" else f" - total ({span})"), n, "week") for n in TAB_ORDER]
    if opts.output == "totals":
        return [(stem, week)]
    return [(stem, week + [t for d in days for t in day_tabs(d, True)])]


def _tables_by_key(per_day, info, need_week: bool):
    by = {d: {t.name: t for t in tables} for d, tables in per_day}
    if need_week:
        by["week"] = {t.name: t for t in weekly_tables([(DAYS[d], t) for d, t in per_day], info)}
    return by


def write_pack(per_day: List[Tuple[int, List[Table]]], opts: PackOptions, plan: LoadedPlan, version: str) -> List[str]:
    """Write the stats pack workbook(s) for the chosen output. Returns the paths written."""
    if not per_day:
        raise StatsPackError("No diagrams match the selected days, operators and fleets.")
    folder = output_folder(opts.output_dir)
    days = [d for d, _t in per_day]
    books = _plan_books(days, opts, _safe(opts.output_name.strip() or pack_name(plan.trent, days)))
    tables = _tables_by_key(per_day, _info(plan, version), any(k == "week" for _s, tabs in books for *_x, k in tabs))
    paths = []
    for stem, tabs in books:
        sink = sink_for(opts.fmt)
        for sheet, title, name, key in tabs:
            sink.table(sheet, title, tables[key][name])
        p = unique_path(folder, stem, sink.ext)
        save_sink(sink, p, stem)
        paths.append(p)
    return paths


def _title(name: str) -> str:
    return {"Formation Mileage by Service Co": "Formation Mileage by Service Code"}.get(name, name)


# --------------------------------------------------------------------------- #
# comparisons
# --------------------------------------------------------------------------- #
def compare_plans(old: LoadedPlan, new: LoadedPlan, opts: PackOptions, version: str,
                  progress: Callable[[float, str], None] = lambda f, m: None) -> Tuple[List[str], List[str], int]:
    """Stats pack of the new plan with every difference from the old plan highlighted."""
    from .compare import summary_rows, write_comparison
    progress(0.05, "Building the original plan...")
    old_pd, w_old = build_pack(old, opts, version)
    progress(0.4, "Building the updated plan...")
    new_pd, w_new = build_pack(new, opts, version)
    warnings = [f"Original plan - {w}" for w in w_old] + [f"Updated plan - {w}" for w in w_new]
    if not new_pd:
        raise StatsPackError("No diagrams in the updated plan match the selected days, operators and fleets.")
    folder = output_folder(opts.output_dir)
    days = [d for d, _t in new_pd]
    books = _plan_books(days, opts, _safe(opts.output_name.strip()
                                          or plans_name(old.trent, new.trent, old.attune.path, new.attune.path, days)))
    need_week = any(k == "week" for _s, tabs in books for *_x, k in tabs)
    info = _info(new, version)
    new_t = _tables_by_key(new_pd, info, need_week)
    old_t = _tables_by_key(old_pd, info, need_week and bool(old_pd))
    progress(0.75, "Writing the comparison...")
    paths, total = [], 0
    for stem, tabs in books:
        sink = sink_for(opts.fmt)
        entries = [(sheet, title, new_t[key][name], old_t.get(key, {}).get(name)) for sheet, title, name, key in tabs]
        key = "week" if any(k == "week" for *_x, k in tabs) else tabs[0][3]
        label = "plans" if key == "week" else DAY_NAMES[int(key)]
        total += write_comparison(sink, entries, f"Differences between {label}" if key == "week" else
                                  f"Differences - {label}", opts.compare,
                                  summary_rows(old_t.get(key, {}), new_t[key]))
        p = unique_path(folder, stem, sink.ext)
        save_sink(sink, p, stem)
        paths.append(p)
    return paths, warnings, total


def compare_packs(old_path: str, new_path: str, output_dir: str = "", output_name: str = "",
                  opts: Optional[CompareOptions] = None, fmt: str = "xlsx") -> Tuple[str, int]:
    """Compare two stats pack workbooks. Returns (output path, number of differences)."""
    from .compare import PackReadError, compare_pack_files
    for label, path in (("original", old_path), ("updated", new_path)):
        if not path or not os.path.isfile(path):
            raise StatsPackError(f"Choose the {label} stats pack.")
    folder = output_folder(output_dir)
    out = unique_path(folder, _safe(output_name.strip() or packs_name(old_path, new_path)), ext_for(fmt))
    try:
        return out, compare_pack_files(old_path, new_path, out, opts)
    except PackReadError as exc:
        raise StatsPackError(str(exc))


# --------------------------------------------------------------------------- #
# unit reports: washes / CETs, depot returns / swaps, captive units
# --------------------------------------------------------------------------- #
UNIT_REPORTS = {"washes": "Washes", "cets": "CETs", "depots": "Depot returns and swaps",
                "captive": "Captive diagrams / units", "fuel": "Fuel check (171s, every 48 hours)"}


def _unit_report_list(plan: LoadedPlan, opts: PackOptions, which: Sequence[str], period,
                      progress: Callable[[float, str], None] = lambda f, m: None) -> Tuple[list, List[str]]:
    from .fleet import FleetTable
    from .model import operator_of
    from .units import (CET_LIMIT, WASH_LIMIT, Depots, Report, _period, attach_possible, captive_reports,
                        checks_report, depot_reports, follow_units, fuel_reports, over_cet_limit, over_wash_limit,
                        wash_cet_reports)
    period = _period(period)
    week = period == "week"
    days = sorted(opts.days)
    names = plan.attune.locations
    depots = Depots.load(names)
    progress(0.2, "Following units through the week..." if week else "Reading the diagrams...")
    units, per_day, warnings = follow_units(plan.trent, plan.attune, days, depots)
    table = FleetTable.load()
    depot_of = {d.key: d.depot for d in plan.trent.diagrams}

    def wanted(x) -> bool:
        return (operator_of(depot_of.get(x.key, ""), table.operator(x.fleet)) in opts.operators
                and (opts.fleets is None or x.fleet in opts.fleets))
    per_day = {d: [x for x in diags if wanted(x)] for d, diags in per_day.items()}
    units = [u for u in units if wanted(u.diagrams[0])]
    from .stabling import learn                   # where units start and end their day (not depots): kept as
    places = {}                                   # stabling locations, new ones said in the log
    for diags in per_day.values():
        for x in diags:
            for loc in (x.start_loc, x.end_loc):
                if loc and loc not in places:
                    places[loc] = (loc, names.get(loc, loc), operator_of(depot_of.get(x.key, ""),
                                                                          table.operator(x.fleet)))
    learn(places.values(), lambda t: bool(depots.depot_of(t)), getattr(plan.attune, "path", "") or "",
          warnings.append)
    if not any(per_day.values()):
        raise StatsPackError("No diagrams match the selected days, operators and fleets.")
    progress(0.6, "Writing the report...")
    reports = []
    kinds = tuple(k for k in ("washes", "cets") if k in which)
    diesel = {r.cls for r in table.rows if (r.power or "").upper().startswith("D") or r.cls.startswith("171")}
    possible = week and opts.possible != "off" and any(k in which for k in ("washes", "cets", "fuel"))
    if possible:
        reports += attach_possible(units, per_day, diesel, days, names, opts.possible)
    if kinds:
        reports += wash_cet_reports(units, per_day, period, kinds, possible)
        late = over_wash_limit(units) if (week and "washes" in kinds) else []
        if late:
            warnings.append(f"{plural(len(late), 'unit')} {agree(len(late), 'goes', 'go')} more than {WASH_LIMIT} "
                            "days without a wash "
                            f"(e.g. {', '.join(u.diagrams[0].label for u in late[:6])}): see the Washes by Unit tab.")
        late_cet = over_cet_limit(units) if (week and "cets" in kinds) else []
        if late_cet:
            warnings.append(f"{plural(len(late_cet), 'unit')} {agree(len(late_cet), 'goes', 'go')} more than "
                            f"{CET_LIMIT} days in passenger service without a "
                            f"CET (e.g. {', '.join(u.diagrams[0].label for u in late_cet[:6])}): see the CETs by "
                            "Unit tab.")
    if week:
        reports += checks_report(units)
    if "depots" in which:
        reports += depot_reports(per_day, depots, names)
    if "captive" in which:
        reports += captive_reports(units, per_day, depots, names, week, days)
    if "fuel" in which:                              # always across days: a 48-hour rule spans days
        reports += fuel_reports(units, diesel, days, possible)
    span = ("week" if week else "whole timetable" if period == "timetable"
            else "+".join(DAYS[d] for d in days) if len(days) < 7 else "each day")
    reports.sort(key=lambda r: r.name.lower())              # tabs in A-Z order, the notes last
    reports.append(Report("Notes", f"How this report was made ({span})", ["Note"],
                          [[w] for w in warnings] + [[
                              "Days: " + ", ".join(DAY_NAMES[d] for d in days) + ". Depots: locations named "
                              "T&RSMD, TMD, EMUD, Depot, Shed or Traincare, plus the depot list (Settings > "
                              "Depots). Units stabling at Lovers Walk, Stewarts Lane or Selhurst end their "
                              "cycle there unless the XML or TRENT print names their next working (never "
                              "inferred), as those depots form whatever is needed the next day."]]))
    return reports, warnings


def _plan_label(plan: LoadedPlan) -> str:
    return os.path.basename(plan.trent.path) + (f" + {os.path.basename(plan.attune.path)}" if plan.attune.path else "")


def _save_reports(reports, opts: PackOptions, stem: str) -> str:
    sink = sink_for(opts.fmt)
    for rep in reports:
        sink.report(rep)
    folder = output_folder(opts.output_dir)
    path = unique_path(folder, _safe(stem), sink.ext)
    save_sink(sink, path, stem)
    return path


def unit_reports(plan: LoadedPlan, opts: PackOptions, which: Sequence[str], week,
                 progress: Callable[[float, str], None] = lambda f, m: None,
                 old: Optional[LoadedPlan] = None) -> Tuple[List[str], List[str]]:
    """Write the chosen unit reports (one file). `week` is the period: 'week' (True) follows each unit through the
    ticked days with the next-day workings; 'days' (False) reports each ticked day separately; 'timetable' gives
    the fleet totals for all the ticked days together. With `old`,
    the reports of both timetables are compared (old = original, plan = updated)."""
    if not which:
        raise StatsPackError("Tick at least one unit report.")
    days = sorted(opts.days)
    reports, warnings = _unit_report_list(plan, opts, which, week, progress)
    tt = timetable(plan.trent)
    if old is not None:
        progress(0.3, "Original timetable...")
        old_reports, old_warn = _unit_report_list(old, opts, which, week)
        warnings = [f"Original: {w}" for w in old_warn] + [f"Updated: {w}" for w in warnings]
        reports = compare_reports(old_reports, reports, _plan_label(old), _plan_label(plan))
        default = f"Unit report {timetable(old.trent) or 'original'} vs {tt or 'updated'}"
    else:
        default = f"Unit report for {tt or naming.today()}"
    stem = opts.output_name.strip() or naming.clip(default + (f" {DAYS[days[0]]}" if len(days) == 1 else ""))
    return [_save_reports(reports, opts, stem)], warnings


# --------------------------------------------------------------------------- #
# capacity report: by headcode group, corridor or station to station, per day / week, optionally in a time window
# --------------------------------------------------------------------------- #
def seats_name(trent: TrentData, group_name: str, days: Sequence[int], window_text: str = "") -> str:
    tt = timetable(trent)
    group_name = re.sub(r"\s*\(.*\)$", "", group_name)          # 'Coastway West (Brighton - ...)'
    return naming.clip(f"Capacity {group_name}" + (f" {window_text.replace(':', '')}" if window_text else "")
                       + (f" {tt}" if tt else "") + (f" {DAYS[days[0]]}" if len(days) == 1 else ""))


def _stem_name(group) -> str:
    """'West Coastway Brighton to Southampton', '1F', 'Brighton to London Victoria'."""
    base = re.sub(r"\s*\(.*\)$", "", group.name)
    if group.kind == "Corridor" and group.direction != "both":
        return f"{base} {group.direction_text}"
    return base


def seats_group(kind: str, name: str, corridor_dir: str = "both", journey: Tuple[str, str] = ("", "")):
    """The trains to count: a headcode group ('1F'), a corridor in one direction or both, or station to
    station."""
    from .seats import JOURNEY, headcode_group, journey_group, load_groups
    if kind == JOURNEY:
        if not journey[0].strip() or not journey[1].strip():
            raise StatsPackError("Choose both stations.")
        return journey_group(*journey)
    code = name.strip().split(" ")[0] if name.strip() else ""
    groups = [g for g in load_groups() if g.kind == kind]
    typed = " ".join(name.split()).casefold()
    custom = next((g for g in groups if g.name in (name, code) or g.name.casefold() == typed), None)
    if custom is None and typed and kind == "Corridor":         # part of a name typed in: the one it matches
        found = [g for g in groups if typed in g.name.casefold()]
        custom = found[0] if len(found) == 1 else None
    if custom is not None:
        return custom.with_direction(corridor_dir) if kind == "Corridor" else custom
    if kind == "Service group" and re.fullmatch(r"[0-9][A-Z]", code.upper()):
        return headcode_group(code)
    raise StatsPackError(f"{kind} '{name}' is not known." + (" Choose one from the list (Settings > Corridors)."
                                                             if kind == "Corridor" else
                                                             " Use a headcode group such as 1F."))


def _seats_list(plan: LoadedPlan, opts: PackOptions, group, week: bool, window, direction: str, progress, log,
                seating: bool = True, standing: bool = True):
    from .seats import SeatsError, Window, parse_time, run_seats
    fleet = FleetTable.load()
    warnings = [fleet.warning] if fleet.warning else []
    try:
        win = (Window(window[0].strip(), parse_time(window[1]), parse_time(window[2]), direction)
               if window else None)
        if win is not None and not win.station:
            raise StatsPackError("Choose the station for the time window.")
        if win is not None and win.start == win.end:
            raise StatsPackError("The two times of the window are the same - nothing can be in it.")
        models = []
        xml_days = plan.attune.days()
        for i, d in enumerate(opts.days):
            progress(0.1 + 0.6 * i / max(len(opts.days), 1), f"Building {DAY_NAMES[d]}...")
            m = build_day(plan.trent, plan.attune, fleet, d, opts.operators, opts.fleets,
                          report_missing=d in xml_days)
            warnings += [f"{DAY_NAMES[d]}: {w}" for w in m.warnings]
            models.append(m)
        progress(0.75, "Counting seats...")
        reports, found, warnings = run_seats(models, fleet, group, win, week, plan.attune.locations, warnings, log,
                                             seating, standing)
    except SeatsError as exc:
        raise StatsPackError(str(exc))
    return reports, found, warnings, group, win


def seats_report(plan: LoadedPlan, opts: PackOptions, kind: str, group_name: str, week: bool,
                 window: Optional[Tuple[str, str, str]] = None, direction: str = "both",
                 progress: Callable[[float, str], None] = lambda f, m: None,
                 log: Callable[[str], None] = lambda m: None,
                 old: Optional[LoadedPlan] = None, corridor_dir: str = "both",
                 journey: Tuple[str, str] = ("", ""), seating: bool = True,
                 standing: bool = True) -> Tuple[List[str], List[str], str]:
    """Capacity report: seats and / or standing room (`seating`, `standing`) of the trains in a headcode
    group (kind 'Service group', name '1F'), on a
    corridor (in `corridor_dir`: forward / reverse / both) or from one station to another (kind 'Station
    to station', `journey`). `window` is (station, from HH:MM, to HH:MM) or None for the whole day; for
    station to station the window is the departure from the first station. With `old`, the original
    timetable (old) and the updated one (plan) are compared. Returns ([path], warnings, summary)."""
    group = seats_group(kind, group_name, corridor_dir, journey)
    if window and kind == "Station to station":
        window = (journey[0], window[1], window[2])
        direction = "departing"
    if not seating and not standing:
        raise StatsPackError("Tick seating capacity, standing room or both.")
    from .seats import capacity_words, hour_figure
    what = capacity_words(seating, standing)
    reports, found, warnings, group, win = _seats_list(plan, opts, group, week, window, direction, progress, log,
                                                       seating, standing)
    seats = sum(hour_figure(s.cap, seating, standing) for s in found)
    where = group.label + (f", {win.text}" if win else "")
    span = (f"{win.text.split(' ')[0]}" + {"arriving": " arr", "departing": " dep"}.get(win.direction, "")
            if win else "")                                  # e.g. '07:00-10:00 arr'
    if old is not None:
        log("Original timetable:")
        o_reports, o_found, o_warn, _g, _w = _seats_list(old, opts, group, week, window, direction,
                                                         lambda f, m: None, log, seating, standing)
        o_seats = sum(hour_figure(s.cap, seating, standing) for s in o_found)
        warnings = [f"Original: {w}" for w in o_warn] + [f"Updated: {w}" for w in warnings]
        reports = compare_reports(o_reports, reports, _plan_label(old), _plan_label(plan))
        stem = opts.output_name.strip() or (seats_name(plan.trent, _stem_name(group), opts.days, span) + " compared")
        change = seats - o_seats
        summary = (f"{where}: {len(o_found)} -> {plural(len(found), 'train')}, {o_seats:,} -> {seats:,} {what} "
                   f"({'+' if change >= 0 else ''}{change:,}).")
    else:
        stem = opts.output_name.strip() or seats_name(plan.trent, _stem_name(group), opts.days, span)
        summary = (f"{plural(len(found), 'train')}, {seats:,} {what} - {where}"
                   + (f" (average {seats / len(opts.days):,.0f} {what} a day)" if week and len(opts.days) > 1 else "")
                   + ".")
    progress(0.9, "Saving...")
    return [_save_reports(reports, opts, stem)], warnings, summary


# --------------------------------------------------------------------------- #
# mileage over a period
# --------------------------------------------------------------------------- #
def period_name(trent: TrentData, period) -> str:
    """'DEC26 Mileage 13-12-2026 to 15-05-2027' (or '... January 2027')."""
    tt = timetable(trent)
    label = period.label.split(" (")[0]
    if " - " in label:
        label = f"{period.start:%d-%m-%Y} to {period.end:%d-%m-%Y}"
    return naming.clip(" ".join(x for x in (tt, "Mileage", label) if x))


def period_mileage(plan: LoadedPlan, opts: PackOptions, kind: str, version: str, month: str = "", start: str = "",
                   end: str = "", progress: Callable[[float, str], None] = lambda f, m: None
                   ) -> Tuple[List[str], List[str], str]:
    """The stats pack's mileage tabs added up over the whole timetable, one month or a custom period (see
    rstools.statspack.period). Returns ([path], warnings, summary)."""
    from . import period as pm
    try:
        per = pm.resolve(plan.trent, kind, month, start, end)
        info = _info(plan, version)
        info["inputs"] += f"\nPeriod: {per.label}"
        totals, by_date, warnings = pm.build(plan.trent, plan.attune, opts.operators, opts.fleets, per, info,
                                             progress)
    except pm.PeriodError as exc:
        raise StatsPackError(str(exc))
    folder = output_folder(opts.output_dir)
    stem = _safe(opts.output_name.strip() or period_name(plan.trent, per))
    progress(0.95, "Writing...")
    path = pm.write(totals, by_date, per, opts.fmt, lambda s, ext: unique_path(folder, s, ext), stem, info)
    total = by_date.rows[-1].cells
    miles = f"{total[6]:,.2f} unit miles" if isinstance(total[6], float) else "unit miles unknown (???)"
    return [path], warnings, f"{per.label}: {plural(per.days, 'day')}, {miles}."
