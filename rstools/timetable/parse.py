"""Read timetable workbooks (GTR timetable check sheets and Network Rail timetable tables).

Both layouts are 'train grids': trains across the columns, locations down the rows with an
arrival / departure marker, and header rows above them (headcode, operator, days...). The
layout is recognised from its labels rather than fixed positions:

* GTR:  TID / Departure Time / Origin / Destination / TOC / Day of Operation header rows,
        'arr' / 'dep' markers, times like '05 10' or '07a05', '.....' for no time, and blank
        location cells under a station meaning 'same station' (e.g. Norwood Junction dep);
* Network Rail: page blocks of Operator / Train ID/Head Code / Notes header rows, 'a' / 'd'
        markers, times like '0510', '. .' for no time, day restrictions (FO, FX, SM) in Notes.

Each sheet is one section (OUT/RTN x SX/SO/SuO), taken from the sheet name or its headings.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SECTIONS = ("OUT SX", "RTN SX", "OUT SO", "RTN SO", "OUT SuO", "RTN SuO")
DAY_CODES = {"SX", "SO", "SUO", "SU", "MO", "MX", "MSX", "TO", "WO", "THO", "FO", "FX", "FSX", "SM", "MFO", "TTHO",
             "TWTHO", "MTWO"}
_HEADCODE_LABEL = re.compile(r"^(tid|train\s*id.*|head\s*code|headcode|train\s*id/head\s*code)$", re.I)
_LABELS = {
    "operator": re.compile(r"^(operator|toc)$", re.I),
    "days": re.compile(r"^(day\s*of\s*operation|days?\s*(of\s*operation|run)?)$", re.I),
    "notes": re.compile(r"^notes$", re.I),
    "origin": re.compile(r"^origin$", re.I),
    "destination": re.compile(r"^destination$", re.I),
    "departure": re.compile(r"^departure\s*time$", re.I),
}
_ROLE = {"a": "arr", "arr": "arr", "arrive": "arr", "d": "dep", "dep": "dep", "depart": "dep"}
_HEADCODE = re.compile(r"^\s*(\d[A-Z]\d{2})", re.I)


class TimetableError(Exception):
    pass


@dataclass
class Event:
    loc: str                    # normalised location name (for matching)
    name: str                   # location as shown
    role: str                   # 'arr' | 'dep'
    time: str                   # HHMM
    raw: str                    # the cell as shown


@dataclass
class TTrain:
    section: str                # e.g. 'OUT SX'
    headcode: str               # 4-character headcode ('' if none)
    raw_id: str                 # as shown (e.g. '9R00ET')
    operator: str
    days: str                   # day code ('SX', 'MSX', 'FO'...)
    notes: str
    column: int                 # position within the section (chronological order of the table)
    events: List[Event] = field(default_factory=list)
    origin: str = ""
    destination: str = ""

    @property
    def first_time(self) -> str:
        return self.events[0].time if self.events else ""

    def label(self) -> str:
        return self.raw_id or self.headcode or "(no headcode)"


@dataclass
class Timetable:
    path: str
    identifier: str             # e.g. 'K_D26'
    sections: Dict[str, List[TTrain]]
    locations: Dict[str, List[Tuple[str, str]]]     # section -> [(loc, role)] rows shown in the table
    warnings: List[str]


def norm_loc(name: str) -> str:
    """'London Bridge (C)' / '  London Bridge (LBG)' -> 'london bridge'."""
    text = re.sub(r"\([^)]*\)", " ", str(name or "")).replace("&", " and ")
    return " ".join(text.split()).casefold()


HALF = "½"


def norm_time(value) -> Optional[str]:
    """A timetable cell as HHMM (with '½' kept for a half minute: '0634½'), or None when it is not a
    time. Footnote characters before, within or after the digits are ignored ('0634a', '06a34', 'a0634',
    '05 10' -> 0634/0510); blanks, dots, dashes and footnote-only cells are not times. A half minute is
    '½', 'H' after the minutes ('0634H'), or 30 seconds in an Excel time."""
    if value is None:
        return None
    if isinstance(value, (_dt.time, _dt.datetime)):
        return f"{value.hour:02d}{value.minute:02d}" + (HALF if value.second >= 30 else "")
    if isinstance(value, float) and 0 <= value < 1:           # an Excel time stored as a fraction of a day
        halves = round(value * 2880)
        minutes = halves // 2
        return f"{minutes // 60 % 24:02d}{minutes % 60:02d}" + (HALF if halves % 2 else "")
    if isinstance(value, (int, float)):
        value = f"{int(value):04d}"
    text = str(value)
    half = HALF in text or bool(re.search(r"\d\s*[Hh]\s*$", text))
    digits = re.sub(r"\D", "", text)
    if len(digits) != 4:
        return None
    hh, mm = int(digits[:2]), int(digits[2:])
    return digits + (HALF if half else "") if hh <= 23 and mm <= 59 else None


def has_halves(tt: "Timetable") -> bool:
    """True when the timetable shows half minutes (a working timetable); a public one never does."""
    return any(e.time.endswith(HALF) for trains in tt.sections.values() for t in trains for e in t.events)


def public_time(hhmm: str, role: str) -> str:
    """'0634½' -> public time: departures round down, arrivals round up (whole minutes unchanged)."""
    if not hhmm.endswith(HALF):
        return hhmm
    mins = int(hhmm[:2]) * 60 + int(hhmm[2:4]) + (1 if role == "arr" else 0)
    return f"{mins // 60 % 24:02d}{mins % 60:02d}"


def to_public(tt: "Timetable") -> "Timetable":
    """The timetable with its half minutes rounded to public times (for comparing with a public one)."""
    from dataclasses import replace
    sections = {sec: [replace(t, events=[replace(e, time=public_time(e.time, e.role)) for e in t.events])
                      for t in trains] for sec, trains in tt.sections.items()}
    return replace(tt, sections=sections)


def norm_headcode(raw) -> str:
    m = _HEADCODE.match(str(raw or ""))
    return m.group(1).upper() if m else ""


def section_of(sheet: str, headings: List[str]) -> Optional[str]:
    """The section a sheet holds, from its name ('... - OUT SX', 'OUT_K_D26_SX_...') or headings."""
    tokens = [t.upper() for t in re.split(r"[\s_\-]+", sheet) if t]
    direction = next((t for t in tokens if t in ("OUT", "RTN")), None)
    day = next((t for t in tokens if t in ("SX", "SO", "SUO", "SU")), None)
    text = " ".join(headings).lower()
    if day is None:
        day = ("SX" if "mondays to fridays" in text else "SO" if "saturday" in text
               else "SUO" if "sunday" in text else None)
    if direction is None:
        direction = ("RTN" if re.search(r"\blondon to\b", text)
                     else "OUT" if re.search(r"\bto london\b", text) else None)
    if not direction or not day:
        return None
    return f"{direction} {'SuO' if day in ('SUO', 'SU') else day}"


def read_timetable(path: str) -> Timetable:
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    try:
        import openpyxl
        from rstools.fsutil import check_office_file
        check_office_file(path)     # refuse a 'zip bomb' before unpacking
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:               # not a readable workbook
        raise TimetableError(f"'{os.path.basename(path)}' could not be read as an Excel workbook ({exc}).")
    sections: Dict[str, List[TTrain]] = defaultdict(list)
    locations: Dict[str, List[Tuple[str, str]]] = {}
    warnings: List[str] = []
    identifier = ""
    notes: Dict[str, Dict[str, str]] = {}          # sheet name -> {note code: description}
    try:
        for ws in wb.worksheets:                   # the notes sheets first (they follow their tables)
            if ws.title.lower().endswith("notes"):
                notes[re.sub(r"[_\s-]*notes$", "", ws.title, flags=re.I)] = {
                    str(r[0]).strip(): str(r[1]).strip() for r in ws.iter_rows(values_only=True)
                    if len(r) > 1 and r[0] not in (None, "") and r[1] not in (None, "")}
        for ws in wb.worksheets:
            if ws.title.lower().endswith("notes"):
                continue
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            headings = [str(r[0]) for r in rows[:12] if r and isinstance(r[0], str)]
            if not identifier:
                m = next((re.match(r"^table\s+(\S+)", h, re.I) for h in headings
                          if re.match(r"^table\s", h, re.I)), None)
                identifier = m.group(1).rstrip("R") if m else ""
            trains, locs = _read_sheet(rows)
            if not trains:
                continue
            sec = section_of(ws.title, headings)
            if sec is None:
                warnings.append(f"Sheet '{ws.title}': could not tell its section (OUT/RTN and SX/SO/SuO) - skipped.")
                continue
            base = len(sections[sec])
            sheet_notes = notes.get(ws.title, {})
            for t in trains:
                _origin_from_notes(t, sheet_notes)
                t.section, t.column = sec, base + t.column
                if not t.days or t.days in ("SU", "SUO"):
                    t.days = t.days or sec.split()[1]
            sections[sec].extend(trains)
            seen = locations.setdefault(sec, [])
            for item in locs:
                if item not in seen:
                    seen.append(item)
    except ET.ParseError as exc:                   # a damaged sheet inside the workbook
        raise TimetableError(f"'{os.path.basename(path)}' looks damaged and could not be read ({exc}). Open it in "
                             "Excel, save it and try again.")
    finally:
        wb.close()
    if not sections:
        raise TimetableError(f"No timetable sections were found in '{os.path.basename(path)}'. Expected sheets of "
                             "trains across the columns and locations down the rows, with a headcode row "
                             "(TID / Train ID).")
    return Timetable(path, identifier, dict(sections), locations, warnings)


def _origin_from_notes(t: TTrain, sheet_notes: Dict[str, str]):
    """Where an NR train really starts / ends, from its note ('D' = 'From Epsom',
    'A' = 'From Brighton to Bedford'); the table only shows part of the journey."""
    for code in t.notes.split():
        m = re.match(r"^from\s+(.+?)(?:\s+to\s+(.+))?$", sheet_notes.get(code, ""), re.I)
        if m:
            t.origin = t.origin or m.group(1).strip()
            t.destination = t.destination or (m.group(2) or "").strip()


def _label(cell) -> str:
    return " ".join(str(cell).split()) if isinstance(cell, str) else ""


def _read_sheet(rows: List[list]):
    """All trains on one sheet (several page blocks are joined left to right, top to bottom)."""
    trains: List[TTrain] = []
    locs: List[Tuple[str, str]] = []
    block: Optional[dict] = None
    station = ""
    for r, row in enumerate(rows):
        if not row:
            continue
        label = _label(row[0])
        if _HEADCODE_LABEL.match(label):
            cols = [c for c in range(1, len(row)) if norm_headcode(row[c]) or (isinstance(row[c], str)
                                                                                  and row[c].strip() and c >= 2)]
            first = min((c for c in cols if c >= 2), default=None)
            if first is None:
                block = None
                continue
            block = {"cols": [c for c in range(first, len(row)) if row[c] not in (None, "")],
                     "meta": defaultdict(dict), "trains": {}}
            for c in block["cols"]:
                block["trains"][c] = TTrain("", norm_headcode(row[c]), str(row[c]).strip(), "", "", "",
                                            len(trains) + len(block["trains"]))
            # header rows above the headcode row on the same block (Operator for NR, TOC below for GTR)
            for back in range(max(0, r - 6), r):
                _meta(rows[back], block)
            trains.extend(block["trains"].values())
            station = ""
            continue
        if block is None:
            continue
        role = _ROLE.get(str(row[1]).strip().lower()) if len(row) > 1 and row[1] is not None else None
        if role is None:
            if label and not _meta(row, block) and re.match(r"^table\s", label, re.I):
                block = None
            continue
        name = label or station                     # blank location: same station as the row above
        if not name:
            continue
        station = name
        loc = norm_loc(name)
        if (loc, role) not in locs:
            locs.append((loc, role))
        for c, train in block["trains"].items():
            raw = row[c] if c < len(row) else None
            t = norm_time(raw)
            if t:
                train.events.append(Event(loc, name.strip(), role, t, str(raw).strip()))
    for tr in trains:
        if not tr.days:
            tr.days = ""
    return [tr for tr in trains if tr.events], locs


def _meta(row: list, block: dict) -> bool:
    """Read an Operator / TOC / Day / Notes / Origin / Destination row into the block's trains."""
    label = _label(row[0]) if row else ""
    for key, pattern in _LABELS.items():
        if pattern.match(label):
            for c, train in block["trains"].items():
                value = row[c] if c < len(row) else None
                text = " ".join(str(value).split()) if value not in (None, "") else ""
                if key == "operator":
                    train.operator = text.upper()
                elif key == "days":
                    train.days = text.upper().replace("SUN", "SU")
                elif key == "notes":
                    train.notes = text
                    codes = [w.upper() for w in text.split() if w.upper() in DAY_CODES]
                    if codes and not train.days:
                        train.days = codes[0]
                elif key == "origin":
                    train.origin = text
                elif key == "destination":
                    train.destination = text
            return True
    return False
