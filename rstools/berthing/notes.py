"""Location notes on berthing charts, edited in the app for each timetable.

The built-in layout carries each berth's notes (e.g. 'Max 12 CET', 'Attachments are not permitted'). In the
app (Data > Berthing chart notes...) a berth's notes can be changed, added or removed for a timetable - the
current one and the next five (May 26, Dec 26, ...) - and every chart made for that timetable shows them. A
berth with no entry for the timetable keeps the layout's own notes.

Saved in berth_notes.json in the settings folder (rstools.branding.settings_dir):

    {"DEC26": {"Brighton|Sdg 3": {"label_note": "CET", "notes": ["Max 12 CET", "..."], "removed": false}}}

`label_note` is shown beside the berth's name, each line of `notes` on a row under it (a long one across the
day columns, in the berth's box). A note with two parts for columns A and B is written 'A | B'.
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Dict, List, Optional, Tuple

from .layout import Block, GridSheet, Layout

FILE_NAME = "berth_notes.json"
SPLIT = " | "                                   # a note row with text in both columns A and B


def path() -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), FILE_NAME)


def _clean(text: str) -> str:
    """Text safe to keep and write to a chart: no control characters, at most the note length allowed."""
    from rstools import limits
    from rstools.fsutil import clean_cell
    text = str(clean_cell(str(text or ""))).replace("\t", " ").strip()
    return text[:int(limits.get("BERTH_NOTE_CHARS"))]


def key(sheet: str, label: str) -> str:
    """'Brighton|Sdg 3': a berth, as notes are saved."""
    return f"{' '.join(sheet.split())}|{' '.join(label.split())}"


def _norm(k: str) -> str:
    return " ".join(k.split()).casefold()


# --------------------------------------------------------------------------- timetables
def timetable_label(tt: str) -> str:
    """'DEC26' -> 'Dec 26'."""
    return f"{tt[:3].title()} {tt[3:]}" if len(tt) == 5 else tt


def upcoming_timetables(today: Optional[datetime.date] = None, n: int = 6) -> List[str]:
    """The timetable running on `today` and the ones after it: ['MAY26', 'DEC26', 'MAY27', ...] (n of them)."""
    from rstools.rules import timetable_of
    tt = timetable_of(today or datetime.date.today())
    out = [tt]
    while len(out) < n:
        season, year = out[-1][:3], int(out[-1][3:])
        out.append(f"DEC{year:02d}" if season == "MAY" else f"MAY{(year + 1) % 100:02d}")
    return out


def timetable_of_start(start: str) -> str:
    """'2026-12-13' (an XML's start date) -> 'DEC26' ('' if it is not a date)."""
    from rstools.rules import parse_date, timetable_of
    day = parse_date(start)
    return timetable_of(day) if day else ""


# --------------------------------------------------------------------------- saved notes
def load(file: str = "") -> Dict[str, Dict[str, dict]]:
    """Every timetable's saved notes ({} when there are none or the file cannot be read)."""
    from rstools import limits
    try:
        file = file or path()
        if os.path.getsize(file) > limits.get("BERTH_NOTES_MAX_BYTES"):
            return {}
        with open(file, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    out: Dict[str, Dict[str, dict]] = {}
    if not isinstance(data, dict):
        return out
    for tt, berths in data.items():
        if not isinstance(tt, str) or not isinstance(berths, dict):
            continue
        for k, v in berths.items():
            if isinstance(k, str) and isinstance(v, dict):
                out.setdefault(tt, {})[k] = entry(v.get("label_note", ""), v.get("notes") or [],
                                                  bool(v.get("removed")))
    return out


def save(data: Dict[str, Dict[str, dict]], file: str = "") -> bool:
    """Save every timetable's notes (atomically); False if the settings folder cannot be written."""
    from rstools.fsutil import write_json
    return write_json(file or path(), {tt: dict(sorted(b.items())) for tt, b in sorted(data.items()) if b})


def entry(label_note: str = "", notes=(), removed: bool = False) -> dict:
    lines = [_clean(n) for n in (notes if isinstance(notes, (list, tuple)) else []) if isinstance(n, str)]
    return {"label_note": _clean(label_note), "notes": [n for n in lines if n], "removed": bool(removed)}


def entry_of(blk: Block) -> dict:
    """A berth's notes in the layout, as an entry (what the app shows before anything is changed)."""
    label_note = blk.notes[0][1] if 0 in blk.notes else ""
    lines = []
    for off in sorted(o for o in blk.notes if o):
        a, b = blk.notes[off]
        if a or b:
            lines.append(f"{a}{SPLIT}{b}" if a and b else a or b)
    lines += [t for _k, t in sorted(blk.data_notes.items()) if t]
    return entry(label_note, lines)


def berths(layout: Layout) -> List[Tuple[str, GridSheet, Block]]:
    """(key, sheet, berth) of every berth in the layout, in chart order."""
    return [(key(sh.name, b.label), sh, b) for sh in layout.sheets if isinstance(sh, GridSheet) for b in sh.blocks]


def _set(blk: Block, e: dict):
    """Replace a berth's notes with an entry's (its units are left alone)."""
    blk.notes = {}
    blk.data_notes = {}
    if e.get("removed"):
        return
    if e.get("label_note"):
        blk.notes[0] = ("", e["label_note"])
    for i, line in enumerate(e.get("notes") or [], start=1):
        a, _sep, b = line.partition(SPLIT)
        blk.notes[i] = (a.strip(), b.strip())


def apply(layout: Layout, timetable: str, data: Optional[Dict[str, Dict[str, dict]]] = None) -> int:
    """Put the notes saved for `timetable` on the layout's berths. Returns how many berths were changed."""
    saved = (load() if data is None else data).get(timetable) or {}
    if not saved:
        return 0
    wanted = {_norm(k): e for k, e in saved.items()}
    n = 0
    for k, _sh, blk in berths(layout):
        e = wanted.get(_norm(k))
        if e is not None:
            _set(blk, e)
            n += 1
    return n


def strip(layout: Layout):
    """Every note off the chart (berths, and the note rows above and before them); berths and capacities stay."""
    for sh in layout.sheets:
        if isinstance(sh, GridSheet):
            sh.preface, sh.lead = [], []
            for blk in sh.blocks:
                blk.notes, blk.data_notes = {}, {}
