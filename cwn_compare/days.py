"""Days of the week in a CWN: which days a CWN covers, which days each train runs, and a CWN cut down
to the trains running on chosen days.

A train's DAYS cell says when it runs: blank = every day the CWN covers, 'MO' / 'FO' / 'ThFO' = only
those days, 'MX' / 'FSX' = the CWN's days except those. The days a CWN covers come from its own
wording ('Mondays to Fridays', 'Saturdays', 'Sundays' on the cover or above the headings, or in the
file name) together with every DAYS code used in it.
"""
from __future__ import annotations

import dataclasses
import os
import re
from typing import Iterable, List, Optional, Set, Tuple

from .model import CWNModel, SheetModel, _day_tokens

DAY_CODES = ("MO", "TO", "WO", "ThO", "FO", "SO", "SuO")
DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAYS = frozenset(range(5))
ALL = frozenset(range(7))
_TOKEN_DAY = {"m": 0, "t": 1, "tu": 1, "w": 2, "th": 3, "f": 4, "s": 5, "sa": 5, "su": 6}
_HINTS = (
    (re.compile(r"\b(daily|every\s*day|7\s*day|seven\s*day|mon(day)?s?\s*(to|-|–)\s*sun(day)?s?)\b", re.I), ALL),
    (re.compile(r"\b(mon(day)?s?\s*(to|-|–)\s*sat(urday)?s?|mtwthfs|m-sa)\b", re.I), frozenset(range(6))),
    (re.compile(r"\b(mon(day)?s?\s*(to|-|–)\s*fri(day)?s?|weekdays?|m-f)\b", re.I), WEEKDAYS),
    (re.compile(r"\b(saturdays?|sats?)\b", re.I), frozenset({5})),
    (re.compile(r"\b(sundays?|suns?)\b", re.I), frozenset({6})),
)
# short codes are only trusted in the file name ('SU' in a sheet may be the Selhurst depot code)
_NAME_CODES = {"SX": WEEKDAYS, "MF": WEEKDAYS, "SO": frozenset({5}), "SAT": frozenset({5}), "SUO": frozenset({6}),
               "SU": frozenset({6}), "SUN": frozenset({6})}


def code_days(code: str, base: Iterable[int]) -> Optional[Set[int]]:
    """Days one DAYS cell runs ('FSX', 'MO FO', '' ...) within the CWN's days `base`; None if the cell
    is not a day code (it is then treated as every day of the CWN)."""
    base = set(base)
    parts = [p for p in re.split(r"[\s,/&+;]+", code or "") if p]
    if not parts:
        return set(base)
    out: Set[int] = set()
    for part in parts:
        parsed = _day_tokens(part)
        if parsed is None:
            return None
        tokens, suffix = parsed
        listed = {_TOKEN_DAY[t.lower()] for t in tokens}
        out |= (base - listed) if suffix == "X" else listed
    return out


def _codes(model: CWNModel) -> List[str]:
    return [b.days for sh in model.sheets.values() for b in sh.blocks if b.days]


def coverage(model: CWNModel, path: str = "") -> Tuple[Set[int], bool]:
    """(days the CWN covers, whether that had to be assumed). Assumed means neither the wording nor
    the DAYS codes say which days it is for; every day is then offered."""
    found: Set[int] = set()
    name = os.path.splitext(os.path.basename(path or ""))[0]
    text = " ".join([model.day_hint, name.replace("_", " ")])
    for pattern, days in _HINTS:
        if pattern.search(text):
            found |= days
    name_codes = [_NAME_CODES[t] for t in re.split(r"[\s_\-.()]+", name.upper()) if t in _NAME_CODES]
    for days in name_codes:
        found |= days
    has_blank = any(not b.days for sh in model.sheets.values() for b in sh.blocks)
    codes = _codes(model)
    for code in codes:
        for part in re.split(r"[\s,/&+;]+", code):
            parsed = _day_tokens(part) if part else None
            if parsed is None:
                continue
            tokens, suffix = parsed
            listed = {_TOKEN_DAY[t.lower()] for t in tokens}
            found |= (WEEKDAYS - listed) if suffix == "X" else listed   # 'MX' in a CWN: Tuesday to Friday
    hinted = any(p.search(text) for p, _d in _HINTS) or bool(name_codes)
    if not found:
        return set(ALL), True
    if has_blank and not hinted and found & WEEKDAYS:
        # trains with no DAYS code run every day of the CWN; with weekday codes (MO, FO, MX...) and no
        # wording to say otherwise, that is Monday to Friday
        return found | WEEKDAYS, True
    return found, not hinted and has_blank


def block_days(days_text: str, base: Set[int]) -> Set[int]:
    got = code_days(days_text, base)
    return set(base) if got is None else got


def filter_model(model: CWNModel, chosen: Iterable[int], base: Optional[Set[int]] = None) -> CWNModel:
    """The CWN with only the trains (blocks) that run on at least one of the `chosen` days."""
    chosen = set(chosen)
    base = set(base) if base is not None else coverage(model)[0]
    sheets = {}
    for key, sh in model.sheets.items():
        kept = [dataclasses.replace(b, order=i)            # copies: the original model is left as it was
                for i, b in enumerate(b for b in sh.blocks if block_days(b.days, base) & chosen)]
        sheets[key] = SheetModel(sh.key, sh.title, sh.header_row, sh.cols, sh.max_col, kept)
    return CWNModel(sheets, model.other_sheets, list(model.warnings), model.day_hint)


def label(days: Iterable[int]) -> str:
    days = sorted(set(days))
    if set(days) == WEEKDAYS:
        return "Mon-Fri"
    if set(days) == set(ALL):
        return "every day"
    return ", ".join(DAY_LABELS[d] for d in days)


def parse_day_list(text: str) -> Set[int]:
    """'MO,TO,FO' / 'Mon Tue' / 'weekdays' -> {0, 1, 4} (for the command line)."""
    out: Set[int] = set()
    for part in re.split(r"[\s,;]+", text.strip()):
        if not part:
            continue
        low = part.lower()
        if low in ("weekdays", "mf", "mon-fri"):
            out |= WEEKDAYS
            continue
        hit = next((i for i, (c, lab) in enumerate(zip(DAY_CODES, DAY_LABELS))
                    if low in (c.lower(), lab.lower(), c.lower().rstrip("o"))), None)
        if hit is None:
            raise ValueError(f"Unknown day '{part}' (use MO, TO, WO, ThO, FO, SO, SuO)")
        out.add(hit)
    return out


def read_days(path: str) -> Tuple[List[int], bool]:
    """(days a CWN file covers, assumed?) - for the day picker; run in a helper process."""
    from .engine import load_model
    from .meta import is_comparison_output, read_meta_file
    from .model import model_from_dict
    if is_comparison_output(path):
        meta = read_meta_file(path) or {}
        model = model_from_dict(meta["baseline"])
    else:
        model = load_model(path)
    days, assumed = coverage(model, path)
    return sorted(days), assumed
