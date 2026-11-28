"""Sheets made from the XML rather than from a chart: a location added to a chart, and every sheet of a chart for
an operator with no built-in layout (TLGN). Also the cover's title (the timetable) and issue line.

A sheet made here has a 'TIPLOC <code>' line above its headings and one berth per platform or siding road the
XML uses there ('Plat 3', 'Siding 2', 'Siding (none given)'), so a later round of changes finds its location
again without the berth list."""
from __future__ import annotations

import datetime
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .layout import CoverRow, GridSheet, Layout, Block
from .mapping import Berth, Locations, norm
from .stays import Berthing

OPERATORS = {"SNGX": "Southern/Gatwick Express", "TLGN": "Thameslink/Great Northern"}
TIPLOC_LINE = "TIPLOC"
NO_ROAD = "Siding (none given)"
_TIPLOC = re.compile(r"^\s*TIPLOC\s+([A-Z0-9]{2,8})(?:\s+[-\u2013]\s+(.+?))?\s*$", re.I)
# words after which a location's name says which siding, road or yard at a station it is ('Hitchin Up Sidings')
_SIDING_WORDS = {"sidings", "siding", "sdg", "sdgs", "cs", "carriage", "carriages", "yard", "loop", "loops", "up",
                 "down", "road", "roads", "platform", "platforms", "plat", "jn", "junction", "goods", "holding",
                 "reception", "shed", "stabling", "berthing", "bay", "dock", "no"}
_TITLE = re.compile(r"^(?:.*\s)?berthing\s+chart\s*$", re.I)
_DATES = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$")
_UNIT_TYPE = re.compile(r"^\s*(?:\d{3}/\d|MAINT)\s*$", re.I)
ISSUES = ["Proof 1", "Proof 2", "Proof 3", "Proof 4", "Proof 5", "Proof 6", "Final"]
TITLE_SIZE, ISSUE_COLOUR = 42.0, "FF0000"
PORTION_EXAMPLE = {"TLGN": {"[Eastbourne]": "[Cambridge]"}}


def _article(n: int) -> str:
    """'an' before 8, 11, 18 and 80-89; 'a' otherwise."""
    return "an" if n in (8, 11, 18) or 80 <= n < 90 else "a"


@dataclass
class Place:
    """A location units berth at overnight, for choosing the chart's locations."""
    tiploc: str
    name: str
    units: int                  # overnight stays there (of the chart's fleets)
    depot: bool
    on_chart: bool              # already on a sheet of the chart


def operator_fleets(operator: str, table) -> Optional[Set[str]]:
    """The unit types of an operator in the fleet data; None (every type) for SNGX, whose built-in chart has
    always shown every unit at its locations (700s at London Bridge, for example)."""
    if operator.upper() == "SNGX" or table is None:
        return None
    return {r.cls for r in table.rows if r.operator.upper() == operator.upper()}


def timetable_name(start: str) -> str:
    """'December 2026' for an XML starting 13/12/2026; '' when the date cannot be read."""
    try:
        d = datetime.date.fromisoformat(start[:10])     # a date, even with a time after it
    except (TypeError, ValueError):
        return ""
    return f"{d:%B %Y}"


# ------------------------------------------------------------------ berths
def _label(code: str) -> str:
    if not code:
        return NO_ROAD
    if code[0].isdigit():
        return f"Plat {code}"
    m = re.fullmatch(r"S(\d+[A-Z]?)", code)
    return f"Siding {m.group(1) if m else code}"


def _codes(label: str) -> Tuple[str, ...]:
    if label == NO_ROAD:
        return ("",)
    m = re.fullmatch(r"Plat (\S+)", label)
    if m:
        return (m.group(1), m.group(1) + "F")
    m = re.fullmatch(r"Siding (\S+)", label)
    if m:
        return ("S" + m.group(1),) if m.group(1)[0].isdigit() else (m.group(1),)
    return ("",)


def _sort_key(label: str):
    m = re.search(r"(\d+)", label)
    return (label.startswith("Siding"), label == NO_ROAD, int(m.group(1)) if m else 0, label)


def sheet_tiploc(sheet) -> str:
    """The (first) TIPLOC of a sheet made from an XML, from its 'TIPLOC <code>' line; '' for a chart's own sheet."""
    tips = sheet_tiplocs(sheet)
    return tips[0][0] if tips else ""


def sheet_tiplocs(sheet) -> List[Tuple[str, str]]:
    """[(TIPLOC, siding location)] from a sheet's 'TIPLOC <code>' / 'TIPLOC <code> - <location>' lines."""
    out = []
    for a, _b in getattr(sheet, "preface", []):
        m = _TIPLOC.match(a)
        if m:
            out.append((m.group(1).upper(), (m.group(2) or "").strip()))
    return out


def berth_tiploc(sheet, blk) -> str:
    """The TIPLOC a berth of a sheet made from an XML is at: its own, else its siding location's, else the
    sheet's."""
    if getattr(blk, "tiploc", ""):
        return blk.tiploc
    tips = sheet_tiplocs(sheet)
    sections = getattr(sheet, "sections", [])
    name = sections[blk.section] if 0 <= blk.section < len(sections) else ""
    hit = next((t for t, sec in tips if sec and norm(sec) == norm(name)), "")
    return hit or (tips[0][0] if tips else "")


def drop_locations(sheet, tiplocs: Set[str]) -> None:
    """Take the berths at these TIPLOCs (normalised) off a sheet made from an XML, with their siding locations'
    banners and TIPLOC lines; the other locations' sections are renumbered."""
    sheet.blocks = [b for b in sheet.blocks if norm(berth_tiploc(sheet, b)) not in tiplocs]
    used = sorted({b.section for b in sheet.blocks})
    if sheet.sections:
        renum = {old: new for new, old in enumerate(used)}
        sheet.sections = [sheet.sections[i] for i in used if i < len(sheet.sections)]
        for b in sheet.blocks:
            b.section = renum.get(b.section, 0)
    kept = []
    for a, b in sheet.preface:
        m = _TIPLOC.match(a)
        if m is None or norm(m.group(1)) not in tiplocs:
            kept.append((a, b))
    sheet.preface = kept


def station_groups(found: Sequence["Place"]) -> List[Tuple[str, List["Place"]]]:
    """Locations grouped by the station or siding they are part of, for one sheet each (as SNGX's charts have
    Brighton's platforms and Wall Siding on one sheet): a location joins another whose whole name starts its own
    ('Bedford' takes 'Bedford Carriage Sidings'), or one with the same name before a word that says which
    siding or road it is ('Hitchin Up Sidings' and 'Hitchin Down Sidings'). Returns [(sheet name, places)], each
    group's own station (if it is one of them) first, the groups in name order."""
    def words(p):
        return p.name.split()

    def stem(p) -> str:
        w = words(p)
        for i, word in enumerate(w[1:], start=1):
            if word.casefold().strip(".()") in _SIDING_WORDS:
                return " ".join(w[:i])
        return p.name

    names = {norm(p.name): p for p in found}
    groups: Dict[str, List[Place]] = {}
    title: Dict[str, str] = {}
    for p in found:
        w = words(p)
        owner = next((names[norm(" ".join(w[:i]))] for i in range(1, len(w))
                      if norm(" ".join(w[:i])) in names), None)
        key_name = owner.name if owner is not None else stem(p)
        key = norm(key_name)
        groups.setdefault(key, []).append(p)
        title.setdefault(key, key_name)
    out = []
    for key, members in groups.items():
        members.sort(key=lambda p: (norm(p.name) != key, p.name))
        out.append((title[key], members))
    return sorted(out, key=lambda g: norm(g[0]))


def make_sheet(name: str, tiploc: str, berthing: Berthing, fleets: Optional[Set[str]] = None,
               known: Sequence[str] = ()) -> GridSheet:
    """A sheet for one location: a berth for each platform / road the stays there use (F, the front of a
    platform, goes with the platform); where none do, the `known` berths (from the berth list), else one berth
    with no road given."""
    codes = {s.plat.upper().removesuffix("F") if s.plat[:1].isdigit() else s.plat.upper()
             for s in berthing.stays if s.loc == tiploc and (fleets is None or s.fleet in fleets)}
    labels = sorted({_label(c) for c in codes}, key=_sort_key) or list(dict.fromkeys(known)) or [NO_ROAD]
    return GridSheet(name, corner=("Siding", "Capacity"), preface=[(f"{TIPLOC_LINE} {tiploc}", "")],
                     blocks=[Block(lab) for lab in labels], sections=[name])


def make_group_sheet(name: str, places: Sequence["Place"], berthing: Berthing, fleets: Optional[Set[str]] = None
                     ) -> GridSheet:
    """One sheet for a station and its sidings (see station_groups): a siding location each, with its banner,
    'TIPLOC <code> - <location>' line and berths; a single location is a plain sheet (make_sheet)."""
    if len(places) == 1:
        p = places[0]
        sheet = make_sheet(name, p.tiploc, berthing, fleets)
        for blk in sheet.blocks:
            blk.tiploc = p.tiploc
        return sheet
    sheet = GridSheet(name, corner=("Siding", "Capacity"))
    for i, p in enumerate(places):
        part = make_sheet(p.name, p.tiploc, berthing, fleets)
        plats = all(b.label.startswith("Plat ") for b in part.blocks)
        section = "Platforms" if norm(p.name) == norm(name) and plats else p.name
        sheet.sections.append(section)
        sheet.preface.append((f"{TIPLOC_LINE} {p.tiploc} \u2013 {section}", ""))
        used = {norm(b.label) for b in sheet.blocks}
        for blk in part.blocks:
            blk.section, blk.tiploc = i, p.tiploc
            blk.codes = blk.codes or ";".join(c for c in _codes(blk.label) if c)
            if norm(blk.label) in used:                 # two sidings' 'Siding 1': told apart by their TIPLOC
                blk.label = f"{blk.label} ({p.tiploc})"
            used.add(norm(blk.label))
            sheet.blocks.append(blk)
    return sheet


def known_berths(tiploc: str) -> List[str]:
    """The berths the berth list has at a TIPLOC (as written on the chart), for a sheet made without an XML."""
    from . import mapping
    try:
        rows = mapping._read(mapping.user_path()) if os.path.exists(mapping.user_path()) else []
        rows += mapping._read(mapping.DEFAULT_CSV)
    except OSError:
        return []
    return list(dict.fromkeys(r["Berth"] for r in rows if r.get("TIPLOC", "").upper() == tiploc.upper()
                              and r.get("Berth")))


def with_auto_berths(locations: Locations, layout: Layout) -> Locations:
    """The berth list plus the berths of the layout's sheets made from an XML (found by their TIPLOC line)."""
    out = Locations(dict(locations.sheets), locations.path, locations.warning)
    for sheet in layout.sheets:
        if not isinstance(sheet, GridSheet) or not (sheet_tiplocs(sheet) or any(b.tiploc for b in sheet.blocks)):
            continue
        out.sheets[norm(sheet.name)] = {
            norm(b.label): Berth(berth_tiploc(sheet, b), tuple(c for c in b.codes.split(";") if c) or _codes(b.label))
            for b in sheet.blocks}
    return out


# ------------------------------------------------------------------ locations
def places(berthing: Berthing, names: Dict[str, str], depots, charted: Iterable[str],
           fleets: Optional[Set[str]] = None) -> List[Place]:
    """Every location units of `fleets` berth at overnight, busiest first."""
    count = Counter(s.loc for s in berthing.stays
                    if s.fleet.upper() != "MAINT" and (fleets is None or s.fleet in fleets))
    on = set(charted)
    out = [Place(t, names.get(t, t), n, bool(depots.depot_of(t)) if depots is not None else False, t in on)
           for t, n in count.items() if t]
    return sorted(out, key=lambda p: (-p.units, p.name))


def find_place(text: str, names: Dict[str, str], known: Iterable[str] = ()) -> str:
    """The TIPLOC a typed location means: a TIPLOC, or a location name (case and spacing do not matter)."""
    t = text.strip()
    pool = set(names) | set(known)
    if t.upper() in pool:
        return t.upper()
    hits = [k for k, v in names.items() if norm(v) == norm(t)]
    if hits:
        return sorted(hits)[0]
    starts = sorted(k for k, v in names.items() if norm(v).startswith(norm(t)))
    return starts[0] if len(starts) == 1 else ""


def charted_tiplocs(layout: Layout, locations: Locations) -> Set[str]:
    out = set()
    for sheet in layout.sheets:
        if isinstance(sheet, GridSheet):
            for blk in sheet.blocks:
                br = locations.berth(sheet.name, blk.label)
                if br is not None and br.tiploc:
                    out.add(br.tiploc)
    return out


def sheet_name(name: str, tiploc: str, taken: Iterable[str]) -> str:
    used = {norm(t) for t in taken}
    clean = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:31] or tiploc
    return clean if norm(clean) not in used else f"{clean[:31 - len(tiploc) - 3]} ({tiploc})"


# ------------------------------------------------------------------ cover
def operator_cover(base: Sequence[CoverRow], operator: str, table) -> List[CoverRow]:
    """The built-in cover for another operator: its name on the first line and its own unit types in the list
    of unit lengths."""
    rows = [CoverRow(dict(r.cells), r.merged) for r in base]
    if rows and rows[0].cells:
        col, (_t, size, bold, colour) = next(iter(rows[0].cells.items()))
        rows[0].cells = {col: (OPERATORS.get(operator.upper(), operator), size, bold, colour)}
    types = [i for i, r in enumerate(rows) if any(_UNIT_TYPE.match(t) and not t.upper().startswith("MAINT")
                                                  for (t, *_x) in r.cells.values())]
    if table is None:
        return rows
    mine = sorted((r for r in table.rows if r.operator.upper() == operator.upper() and r.cars), key=lambda r: r.cls)
    classes = [r.cls.split("/")[0] for r in mine]
    example = "387" if "387" in classes else classes[0] if classes else ""      # a class that runs coupled
    for r in rows:                     # the examples of coupled units and portions: this operator's own
        for col, (t, size, bold, colour) in list(r.cells.items()):
            text = re.sub(r"^\((\d{3})$", lambda m: f"({example}" if example else m.group(0), t)
            text = PORTION_EXAMPLE.get(operator.upper(), {}).get(text, text)
            r.cells[col] = (text, size, bold, colour)
    if not types:
        return rows
    style = rows[types[0]].cells
    (c1, (_a, s1, b1, k1)), (c2, (_b, s2, b2, k2)) = list(style.items())[:2]
    new = [CoverRow({c1: (r.cls, s1, b1, k1), c2: (f"is {_article(r.cars)} {r.cars} car unit", s2, b2, k2)})
           for r in mine]
    return rows[:types[0]] + new + rows[types[-1] + 1:]


def set_cover(rows: List[CoverRow], timetable: str, issue: str, clear_issue: bool) -> List[CoverRow]:
    """The title line reads '<timetable> Berthing Chart' and the line under it the issue ('Proof 1', 'Final' or
    whatever is typed). With no issue, `clear_issue` leaves that line blank (a new chart does not take the
    built-in chart's 'Proof 2'); otherwise the chart's own issue is kept."""
    rows = [CoverRow(dict(r.cells), r.merged) for r in rows]
    at = next((i for i, r in enumerate(rows) if any(_TITLE.match(t) for (t, *_x) in r.cells.values())), None)
    if at is None:
        return rows
    if timetable:
        col, (_t, size, bold, colour) = next(iter(rows[at].cells.items()))
        rows[at].cells = {col: (f"{timetable} Berthing Chart", size, bold, colour)}
    nxt = rows[at + 1] if at + 1 < len(rows) else None
    texts = [t for (t, *_x) in nxt.cells.values()] if nxt is not None else []
    if nxt is None or any(_DATES.match(t) for t in texts):
        if not issue:
            return rows
        nxt = CoverRow({}, True)
        rows.insert(at + 1, nxt)
    if issue:
        col = min(nxt.cells) if nxt.cells else min(rows[at].cells)
        size = next(iter(nxt.cells.values()))[1] if nxt.cells else TITLE_SIZE
        nxt.cells, nxt.merged = {col: (issue, size, True, ISSUE_COLOUR)}, True
    elif clear_issue:
        nxt.cells = {}
    return rows


# ------------------------------------------------------------------ choosing locations (the Choose locations window)
@dataclass
class Choice:
    """A location in the Choose locations list: ticked = on the chart."""
    key: str                    # a sheet name, or a TIPLOC for a location found in the XML or typed
    text: str                   # as listed
    default: bool               # on the chart unless it is unticked
    ticked: bool


def initial_choices(operator: str, sheets: Sequence[str], leave_out: Sequence[str], add: Sequence[str]) -> List[Choice]:
    """The list before the XML is read: the layout's sheets (SNGX, or a saved location set), and the locations
    left out and added before."""
    out_keys = {norm(x) for x in leave_out}
    rows: List[Choice] = []
    if operator.upper() == "SNGX" or sheets:
        rows = [Choice(s, s, True, norm(s) not in out_keys) for s in sheets]
    else:
        rows = [Choice(x, x, True, False) for x in leave_out]
    seen = {norm(r.key) for r in rows}
    rows += [Choice(x, f"{x} (added)", False, True) for x in add if norm(x) not in seen]
    return rows


def merge_places(rows: List[Choice], found: Sequence[Place], operator: str, from_xml: Optional[bool] = None
                 ) -> List[Choice]:
    """The list with the XML's berthing locations added: when the chart's sheets are made from the XML (TLGN
    with no saved location set) each place (not depots) is on the chart by default; otherwise the places with no
    sheet can be ticked to add them."""
    out = list(rows)
    by_key = {norm(r.key): r for r in out}
    tlgn = operator.upper() != "SNGX" if from_xml is None else from_xml
    for p in found:
        if p.on_chart:
            continue
        what = f"{p.name} ({p.tiploc}) - {p.units} overnight stay{'s' if p.units != 1 else ''}" + \
               (", depot" if p.depot else "")
        hit = by_key.get(norm(p.tiploc)) or by_key.get(norm(p.name))
        default = tlgn and not p.depot
        if hit is not None:
            hit.key, hit.text, hit.default = p.tiploc, what, default
            continue
        row = Choice(p.tiploc, what, default, default)
        out.append(row)
        by_key[norm(p.tiploc)] = row
    return out


def chosen(rows: Sequence[Choice]) -> Tuple[List[str], List[str]]:
    """(leave out, add) from the ticks."""
    return ([r.key for r in rows if r.default and not r.ticked], [r.key for r in rows if not r.default and r.ticked])
