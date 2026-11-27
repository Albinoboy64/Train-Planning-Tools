"""Days of the week, shared by every reader and report: names, codes and the day each code means (0 = Monday)."""
from __future__ import annotations

import re
from typing import Set

DAYS = ["MO", "TO", "WO", "ThO", "FO", "SO", "Su"]          # display codes, Monday first
DAY_CODES = ("MO", "TO", "WO", "ThO", "FO", "SO", "SuO")    # the CWN / platform workings codes
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_LETTERS = ("M", "T", "W", "Th", "F", "S", "Su")
_TOKENS = re.compile(r"Su|Sa|Th|Tu|M|T|W|F|S", re.I)
TOKEN_DAY = {"m": 0, "t": 1, "tu": 1, "w": 2, "th": 3, "f": 4, "s": 5, "sa": 5, "su": 6}     # one letter group
_INDEX = TOKEN_DAY


def days_of_code(code: str) -> Set[int]:
    """Weekdays (0 = Monday) covered by a days-run code such as WO, ThO, SX, MSX, FSX, Su, MTWThF.

    'X' codes exclude days from Monday-Saturday (the Sunday timetable is separate)."""
    code = code.strip()
    if not code:
        return set()
    if code.lower() in ("su", "suo"):
        return {6}
    suffix, body = "", code
    if len(code) > 1 and code[-1] in "OXox":
        suffix, body = code[-1].upper(), code[:-1]
    tokens = _TOKENS.findall(body)
    if not tokens or "".join(tokens).lower() != body.lower():
        return set()
    days = {_INDEX[t.lower()] for t in tokens}
    if suffix == "X":
        return set(range(6)) - days
    return days


def days_of_mask(mask: str) -> Set[int]:
    """Attune daysRun mask of 9 characters: the 2nd is Sunday, the 3rd-8th Monday-Saturday
    ('NNYYYYYNN' Mon-Fri, 'NNNNNNNYN' Saturday, 'NYNNNNNNN' Sunday). The 9th is read as Sunday too."""
    mask = (mask or "").upper()
    if len(mask) < 9:
        return {i for i, ch in enumerate(mask[-7:]) if ch == "Y"}
    days = {i for i, ch in enumerate(mask[2:8]) if ch == "Y"}
    if mask[1] == "Y" or mask[8] == "Y":
        days.add(6)
    return days
