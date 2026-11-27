"""Default output names: short, readable and unique to what was compared."""
from __future__ import annotations

import datetime as _dt
import os
import re
from collections import Counter
from typing import Iterable, Optional

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_DATE = re.compile(r"\b\d{1,2}[-./]\d{1,2}[-./]\d{2,4}\b")
_NOISE = re.compile(r"\b(?:carriage\s+working\s+notices?|cwn|stats?\s*pack(?:\s+for)?|comparison|copy(?:\s+of)?)\b",
                    re.IGNORECASE)
_COPY = re.compile(r"\s*[(\[]\d+[)\]]\s*$")
MAX_LABEL = 30
MAX_NAME = 120                      # keeps full paths well inside Windows' path length limit


def today() -> str:
    return _dt.date.today().strftime("%d-%m-%Y")


def short_label(path: str) -> str:
    """'C:/.../DEC26 CWN Proof 2 (1).xlsx' -> 'DEC26 Proof 2'."""
    stem = os.path.splitext(os.path.basename(path or ""))[0]
    if " vs " in stem:                      # an earlier comparison: keep its newest side
        stem = stem.rsplit(" vs ", 1)[1]
    text = _COPY.sub("", stem.replace("_", " "))
    text = _NOISE.sub(" ", _DATE.sub(" ", text))
    text = " ".join(text.replace(" - ", " ").split()).strip(" -.")
    text = text or " ".join(stem.replace("_", " ").split())
    return text if len(text) <= MAX_LABEL else text[:MAX_LABEL].rstrip(" -.")


def vs(a: str, b: str) -> str:
    """'DEC26 Proof 1' and 'DEC26 Proof 2' -> 'DEC26 Proof 1 vs Proof 2' (shared start shown once)."""
    wa, wb = a.split(), b.split()
    n = 0
    while n < min(len(wa), len(wb)) - 1 and wa[n].casefold() == wb[n].casefold():
        n += 1
    if n and not any(ch.isalpha() for ch in " ".join(wb[n:])):
        n -= 1                                   # 'Proof 1 vs Proof 2', not 'Proof 1 vs 2'
    return f"{a} vs {' '.join(wb[n:])}" if a and b else (a or b)


def compare_name(first: str, second: str) -> str:
    """Default CWN comparison name: today's date and the two (shortened) file names."""
    if not first or not second:
        return today()
    return clip(f"{today()} {vs(short_label(first), short_label(second))}")


def timetable_of(start_dates: Iterable[str]) -> str:
    """Timetable name from diagram start dates ('14/12/2026' ...) -> 'DEC26' (the most common)."""
    seen: Counter = Counter()
    for d in start_dates:
        m = re.match(r"\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", d or "")
        if m and 1 <= int(m.group(2)) <= 12:
            seen[(int(m.group(3)) % 100, int(m.group(2)))] += 1
    if not seen:
        return ""
    yy, mm = seen.most_common(1)[0][0]
    return f"{MONTHS[mm - 1]}{yy:02d}"


def pick_vs(*pairs) -> Optional[str]:
    """The first pair of labels that tells the two sides apart, as 'a vs b'."""
    for a, b in pairs:
        if a and b and a.casefold() != b.casefold():
            return vs(a, b)
    return None


def clip(name: str) -> str:
    return name if len(name) <= MAX_NAME else name[:MAX_NAME].rstrip(" -.")


def output_stem(name: str) -> str:
    """A typed output name made safe as a file name: characters Windows does not allow become '-', a typed
    '.xlsx' is dropped and the name is shortened to MAX_NAME ('' stays '': the caller picks a default)."""
    import re
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name or "").strip().rstrip(".")
    if name.lower().endswith(".xlsx"):
        name = name[:-5]
    return clip(name)


_PLAIN_FIRST = {"original", "updated", "earlier", "timetable", "train"}


def file_label(label: str) -> str:
    """A file box's label as words for a message: 'Original Attune XML:' -> 'original Attune XML',
    'GTR timetable:' -> 'GTR timetable' (names such as Attune, TRENT, CWN and GTR keep their capitals)."""
    text = label.rstrip(":").replace(" - reference", "").strip()
    first, _sep, rest = text.partition(" ")
    if first.casefold() in _PLAIN_FIRST:
        first = first.lower()
    return f"{first} {rest}".strip()
