"""Running lines for the Section 4 check.

An Attune XML has no running lines, so where a possession blocks only some lines (say the Fast lines) the check can
only say "check the line used". A VPT export gives the line each leg of a train runs on ('SL', 'FL', 'DBF', 'UML'...).
Here a line code and a possession's Blocked text are both read into a direction (Down / Up) and a kind of line
(Fast, Slow, Main...), and compared. Only a clear answer is given: a code or Blocked text this cannot read is
'unknown' and the clash keeps "check the line used".
"""
from __future__ import annotations

import re
from typing import Dict, Sequence, Set, Tuple

BLOCKED, OPEN, UNKNOWN = "blocked", "open", "unknown"
_KINDS = {"F": "Fast", "S": "Slow", "M": "Main", "R": "Relief", "L": "Local", "Q": "Quarry"}
_WORDS = {"fast": "Fast", "slow": "Slow", "main": "Main", "relief": "Relief", "local": "Local", "quarry": "Quarry"}
_DIRS = {"D": "Down", "U": "Up"}
CODE_TEXT = ("A line code gives its direction from the first letter (D = Down, U = Up, none for both) and its kind "
             "from the last letter or letters: F Fast, S Slow, M / ML Main, R Relief, L Local, Q Quarry (e.g. SL, FL, "
             "DBF, UBS, UML, QL). Anything else is unknown.")


def parse_code(code: str) -> Tuple[str, str]:
    """(direction, kind) of a line code: ('Down', 'Fast') for 'DBF'; '' where the code does not say."""
    c = (code or "").strip().upper()
    if not c or not c.isalpha():
        return "", ""
    direction = _DIRS.get(c[0], "") if len(c) >= 2 and c not in ("SL", "FL", "QL") else ""
    if c in ("SL", "FL", "ML", "RL", "QL", "LL"):
        return "", _KINDS[c[0]]
    if len(c) == 2 and c[0] in _DIRS and c[1] in "FSMRLQ":        # 'DR': Down relief
        return _DIRS[c[0]], _KINDS[c[1]]
    if c.endswith("ML"):
        return direction, "Main"
    if len(c) == 3 and c[2] in "FS" and direction:               # 'DBF': Down, route letter, Fast / Slow
        return direction, _KINDS[c[2]]
    return direction, ""


def parse_blocked(text: str) -> Tuple[str, Set[str]]:
    """(direction, kinds) of a possession's Blocked text: ('', {'Fast'}) for 'Fast Lines BLOCKED'."""
    t = (text or "").lower()
    down, up = bool(re.search(r"\b(down|dn)\b", t)), bool(re.search(r"\bup\b", t))
    direction = "" if down == up or re.search(r"\ball\b|\bboth\b", t) else ("Down" if down else "Up")
    return direction, {k for w, k in _WORDS.items() if re.search(rf"\b{w}\b", t)}


def verdict(blocked: str, codes: Sequence[str]) -> Tuple[str, str]:
    """(BLOCKED / OPEN / UNKNOWN, why) for a train on `codes` (the lines of its legs through the section) when the
    possession's Blocked text is `blocked`. Open only when the answer is clear: both are Fast / Slow and differ, or
    the direction is the other one."""
    bdir, bkinds = parse_blocked(blocked)
    if not bkinds and not bdir:
        return UNKNOWN, ""
    used = [(c, *parse_code(c)) for c in dict.fromkeys(c.strip() for c in codes if c.strip())]
    used = [u for u in used if u[1] or u[2]]
    if not used:
        return UNKNOWN, ""
    shown = ", ".join(u[0] for u in used)
    verdicts = []
    for code, ldir, kind in used:
        if bdir and ldir and bdir != ldir:
            verdicts.append((OPEN, f"{code} is the {ldir} line; only the {bdir} line is blocked"))
        elif kind and bkinds:
            if kind in bkinds:
                verdicts.append((BLOCKED, f"{code} is a {kind} line, which is blocked"))
            elif kind in ("Fast", "Slow") and bkinds <= {"Fast", "Slow"}:
                verdicts.append((OPEN, f"{code} is a {kind} line; only the {' and '.join(sorted(bkinds))} "
                                       "lines are blocked"))
            else:
                verdicts.append((UNKNOWN, ""))
        else:
            verdicts.append((UNKNOWN, ""))
    if any(v[0] == BLOCKED for v in verdicts):
        return BLOCKED, next(v[1] for v in verdicts if v[0] == BLOCKED)
    if all(v[0] == OPEN for v in verdicts):
        return OPEN, verdicts[0][1]
    return UNKNOWN, f"Line(s) used: {shown}"


def line_codes(train, first: int, last: int) -> Dict[int, str]:
    """The line codes of the legs of a VPT train between call indexes first and last."""
    lo, hi = sorted((first, last))
    return {i: c for i, c in train.lines.items() if lo < i <= hi}
