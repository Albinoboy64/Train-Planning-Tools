"""Reader for Network Rail CIF schedule files (the Common Interface File that TPS and the timetable feeds
export): fixed-width text records of 80 characters.

    HD  the file (its dates)                    TI  a location (TIPLOC, its name and CRS code)
    BS  a schedule: UID, dates, days run, headcode, STP indicator (P permanent, O overlay, N new, C cancel)
    BX  more of it: the operator (ATOC code)    LO / LI / LT  origin, calls and destination with working
                                                                times, public times and platforms

Only what other operators' trains need is read: headcode, operator, days, dates and each call's times and
platform. For each UID and days run, the schedule valid for longest is kept (the timetable's own pattern, not a
one-day overlay or a short STP); cancellations (C) and deletions are left out. The trains
come out as a stationbook.Plan, like an Attune XML or a VPT, so every task that takes other operators' files
takes a CIF too."""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


class CifError(Exception):
    pass


def is_cif(path: str) -> bool:
    """True when the file starts with a CIF header record ('HD' followed by the file's identity)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(82).decode("latin-1")
    except OSError:
        return False
    return head.startswith("HD") and len(head.split("\n")[0].rstrip("\r")) >= 40


def _secs(text: str) -> Optional[int]:
    """'0534' / '0534H' (half a minute) as seconds after midnight; None if blank."""
    t = text.strip()
    if len(t) < 4 or not t[:4].isdigit():
        return None
    s = int(t[:2]) * 3600 + int(t[2:4]) * 60
    return s + 30 if t[4:5] == "H" else s


def _date(text: str) -> str:
    """'261213' (yymmdd) as '2026-12-13'; '' if not a date."""
    t = text.strip()
    if len(t) != 6 or not t.isdigit():
        return ""
    return f"20{t[:2]}-{t[2:4]}-{t[4:]}"


def _hd_date(text: str) -> str:
    """The header's 'ddmmyy' as '20yy-mm-dd'."""
    t = text.strip()
    if len(t) != 6 or not t.isdigit():
        return ""
    return f"20{t[4:]}-{t[2:4]}-{t[:2]}"


def _span(start: str, end: str) -> int:
    """How many days a schedule is valid for (0 if its dates cannot be read)."""
    import datetime
    try:
        a, b = datetime.date.fromisoformat(_date(start)), datetime.date.fromisoformat(_date(end))
    except ValueError:
        return 0
    return (b - a).days + 1


def read_plan(path: str):
    """The CIF's trains as a stationbook.Plan (no unit diagrams). Raises CifError for a file that is not a CIF."""
    from rstools import limits
    name = os.path.basename(path)
    try:
        limits.check_size(path, "CIF_MAX_BYTES", "CIF file")
        fh = open(path, encoding="latin-1")
    except OSError as exc:
        raise CifError(f"'{name}' could not be opened: {exc}")
    with fh:
        head = fh.readline().rstrip("\r\n")
        if not head.startswith("HD"):
            raise CifError(f"'{name}' is not a CIF file (it does not start with an HD header record).")
        return _read_records(path, head.ljust(80), fh)


def _read_records(path: str, head: str, lines):
    from rstools.stationbook import Call, Plan, Train, _unroll
    name = os.path.basename(path)
    start, end = _hd_date(head[48:54]), _hd_date(head[54:60])
    locations: Dict[str, str] = {}
    best: Dict[str, Tuple[int, "Train"]] = {}          # UID + days run -> (days valid, train)
    cur: Optional[Train] = None
    cur_key, cur_rank = "", 0
    raw: List[list] = []
    ops: Dict[str, int] = defaultdict(int)

    def finish():
        nonlocal cur
        if cur is not None and raw:
            times = _unroll([t for r in raw for t in r[1:5]])
            for i, r in enumerate(raw):
                arr, arr_pub, dep, dep_pub = times[4 * i:4 * i + 4]
                cur.calls.append(Call(r[0], arr, arr_pub, dep, dep_pub, r[5], r[6], r[7]))
            older = best.get(cur_key)
            if older is None or cur_rank > older[0]:
                best[cur_key] = (cur_rank, cur)
        cur = None
        raw.clear()

    for line in lines:
        line = line.rstrip("\r\n")
        rec = line[:2]
        line = line.ljust(80)
        if rec == "TI" or rec == "TA":
            tip = line[2:9].strip()
            desc = line[18:44].strip().title()
            if tip and desc:
                locations[tip] = desc
        elif rec == "BS":
            finish()
            stp = line[79]
            if line[2] == "D" or stp == "C":           # a deletion or a cancellation: nothing runs
                continue
            days = {i for i, ch in enumerate(line[21:28]) if ch == "1"}
            cur = Train(line[32:36].strip(), days, "S" if stp in "NO" else "L",
                        valid_from=_date(line[9:15]), valid_until=_date(line[15:21]))
            cur_key, cur_rank = line[3:9] + "|" + line[21:28], _span(line[9:15], line[15:21])
        elif rec == "BX" and cur is not None:
            op = line[11:13].strip()
            cur.operator = op
            if op:
                ops[op] += 1
        elif cur is not None and rec in ("LO", "LI", "LT"):
            tip = line[2:9].strip()
            if rec == "LO":
                raw.append([tip, None, None, _secs(line[10:15]), _secs(line[15:19]), line[19:22].strip(), True,
                            True])
            elif rec == "LT":
                raw.append([tip, _secs(line[10:15]), _secs(line[15:19]), None, None, line[19:22].strip(), True,
                            True])
            else:
                passing = _secs(line[20:25])
                if passing is not None:
                    raw.append([tip, None, None, passing, None, line[33:36].strip(), False, False])
                else:
                    pub = _secs(line[25:29]) is not None or _secs(line[29:33]) is not None
                    raw.append([tip, _secs(line[10:15]), _secs(line[25:29]), _secs(line[15:20]), _secs(line[29:33]),
                                line[33:36].strip(), True, pub])
        elif rec == "ZZ":
            finish()
    finish()
    trains: Dict[str, List] = defaultdict(list)
    for _rank, t in best.values():
        if t.calls and t.id:
            trains[t.id].append(t)
    if not trains:
        raise CifError(f"'{name}' has no train schedules.")
    from .base import load_tiplocs
    names = load_tiplocs()
    names.update(locations)
    operator = max(ops, key=lambda k: ops[k]) if ops else ""
    return Plan(path, start, names, dict(trains), [], end, operator)
