"""Reader for the Attune 'Voyager plan train export' (.vpt).

A plain comma-separated text file, one train after another:

    00,VoyagerPlanTrainExport,2,20261126152819,AA,20270516,20271211,       the file
    01,1F01BT  ,20270522,L,0000,P,4136,  ,EBOURNE,VICTRIC,V,375 ,20271211,64,...   a train
    04,4136,1,EBOURNE,HMPDNPK,L,P,0,Y,17970,0,17760,0,Y,N,0,0,0,30,1  ,   ,    ,0,0,0,0,S,...   one leg of it
    03,6,10,20270522,CONTRACT,...                                                notes (not read)

An 01 line is a train: its ID, first and last date, the days it runs (a bit for each day, Sunday = 1 to
Saturday = 64), origin and destination, distance, traction and timing load. Its legs (04 lines, matched by the
train's path number) go from one timing point to the next with the times in seconds from midnight: when the leg
starts and ends, the dwell at its end, the platform and stop / pass at its start, the line, and the engineering,
pathing, performance and adjustment allowances. The trains come out as the same PrintTrain objects the train print
readers make, so they are compared, paired and shown by the same code.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List, Optional

from .prints import Call, PrintError, PrintTrain

HEADER = "VoyagerPlanTrainExport"
# what a VPT never carries (so it is not compared with a train print's): the public times
LACKS_TIMES = frozenset({"pub_arr", "pub_dep", "off_arr", "off_dep"})
WEEKDAY_BIT = (2, 4, 8, 16, 32, 64, 1)             # Monday ... Sunday


def is_vpt(path: str) -> bool:
    """True when the file starts like a Voyager plan train export."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(200).decode("latin-1")
    except OSError:
        return False
    return head.startswith("00," + HEADER)


def days_from_bits(bits: int) -> frozenset:
    """Weekdays (0 = Monday) in a day mask where Sunday is 1 and Saturday is 64."""
    return frozenset(i for i, bit in enumerate(WEEKDAY_BIT) if bits & bit)


def days_text(days: frozenset) -> str:
    """The days as a days-run code: Mon-Fri 'SX', Saturday 'SO', Sunday 'Su', else the day letters."""
    if days == frozenset(range(5)):
        return "SX"
    if days == frozenset({5}):
        return "SO"
    if days == frozenset({6}):
        return "Su"
    if days == frozenset(range(7)):
        return "Daily"
    from rstools.days import DAY_LETTERS
    return "".join(DAY_LETTERS[d] for d in sorted(days))


def clock(sec: int, role: str) -> str:
    """A time as the Attune train prints show it: '05.37', a half minute as '05a52½' (arrival) / '05p53½'
    (departure), and a passing time as '05/41'."""
    sec %= 86400
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    half = s >= 30
    mark = "/" if role == "pass" else ("a" if role == "wtt_arr" else "p") if half else "."
    return f"{h:02d}{mark}{m:02d}" + ("½" if half else "")


def _minutes(sec: int) -> str:
    """An allowance as minutes: '1', '½', '1½'."""
    whole, half = divmod(sec, 60)[0], sec % 60 >= 30
    return f"{whole if whole or not half else ''}{'½' if half else ''}" or "0"


def _date(text: str) -> str:
    return f"{text[6:8]}/{text[4:6]}/{text[:4]}" if len(text) == 8 and text.isdigit() else ""


def _records(path: str):
    """(file header fields, [01 train header fields], {path id: [04 leg fields]}) of a VPT file."""
    from rstools.fsutil import long_path
    name = os.path.basename(path)
    top: List[str] = []
    heads: List[List[str]] = []
    legs: Dict[str, List[List[str]]] = defaultdict(list)
    from rstools import limits
    try:
        limits.check_size(long_path(path), "VPT_MAX_BYTES", "VPT export")
        with open(long_path(path), encoding="latin-1", newline="") as fh:
            first = fh.readline()
            if not first.startswith("00," + HEADER):
                raise PrintError(f"'{name}' is not an Attune Voyager plan train export (.vpt).")
            top = first.rstrip("\r\n").split(",")
            for line in fh:
                rec = line.rstrip("\r\n").split(",")
                kind = rec[0]
                if kind == "01" and len(rec) > 47:
                    heads.append(rec)
                elif kind == "04" and len(rec) > 26:
                    legs[rec[1]].append(rec)
    except OSError as exc:
        raise PrintError(f"'{name}' could not be read ({exc}).")
    return top, heads, legs


def read_vpt(path: str) -> List[PrintTrain]:
    """The trains of a VPT file (see the module text)."""
    from .base import load_tiplocs
    name = os.path.basename(path)
    _top, heads, legs = _records(path)
    names = load_tiplocs()
    return [t for t in (_train(h, legs.get(h[6], []), names, name) for h in heads) if t.calls]


def _iso(text: str) -> str:
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 and text.isdigit() else ""


def read_plan(path: str):
    """A VPT as a stationbook.Plan: its trains (calls, working times, platforms, days, dates and the line each
    leg runs on) but no unit diagrams. Used for another operator's trains in a station book or a Section 4
    check, and for the running lines of a Section 4 check."""
    from rstools.stationbook import Call as PlanCall, Plan, Train
    from .base import load_tiplocs
    top, heads, legs = _records(path)
    names = load_tiplocs()
    trains: Dict[str, List] = defaultdict(list)
    for h in heads:
        rows = sorted(legs.get(h[6], []), key=lambda r: int(r[2] or 0))
        t = Train(h[1].strip(), set(days_from_bits(int(h[13] or 0))), h[3].strip() or "L",
                  valid_from=_iso(h[2]), valid_until=_iso(h[12]))
        pending: Optional[PlanCall] = None
        arrival: Optional[int] = None
        for r in rows:
            frm, to = r[3].strip(), r[4].strip()
            start, end = int(r[11] or 0), int(r[9] or 0)
            stop = r[26].strip() == "S"
            if frm == to:
                if pending is not None and r[19].strip():
                    pending.plat = r[19].strip()
                continue
            if pending is None:
                pending = PlanCall(frm, None, None, None, None, "", stop, stop)
                arrival = None
            c = pending
            c.dep = start
            if not stop:
                c.arr = None
            elif arrival is not None:
                c.arr = arrival
            c.stops = c.passenger = stop
            if r[19].strip():
                c.plat = r[19].strip()
            t.calls.append(c)
            if r[21].strip():
                t.lines[len(t.calls)] = r[21].strip()       # the leg into the next call
            pending = PlanCall(to, None, None, None, None, "", True, True)
            arrival = end
        if pending is not None and arrival is not None and t.calls:
            pending.arr, pending.stops, pending.passenger = arrival, True, True
            t.calls.append(pending)
        if t.calls:
            trains[t.id].append(t)
    locations = dict(names)
    op = top[4].strip() if len(top) > 4 else ""
    return Plan(path, _iso(top[5]) if len(top) > 5 else "", locations, dict(trains), [],
                _iso(top[6]) if len(top) > 6 else "", op)


def _train(h: List[str], rows: List[List[str]], names: Dict[str, str], source: str) -> PrintTrain:
    ident = h[1].strip()
    days = days_from_bits(int(h[13] or 0))
    info = {"TrainID": ident, "From": _date(h[2]), "Until": _date(h[12]), "Timing Load": h[11].strip(),
            "Power Type": h[46].strip(), "Limiting Speed": h[47].strip(), "Train Category": h[34].strip(),
            "Distance": f"{float(h[25]):.2f}" if h[25].strip() else "", "Origin Loc": h[8].strip(),
            "Destination Loc": h[9].strip()}
    info = {k: v for k, v in info.items() if v}
    t = PrintTrain(ident[:4], "", days_text(days), [], [], source, 0, ident=ident, info=info, kind="vpt",
                   lacks=LACKS_TIMES, dayset=days)
    rows = sorted(rows, key=lambda r: int(r[2] or 0))
    pending: Optional[Call] = None              # the location the last leg arrived at, its departure still to come
    arrival: Optional[int] = None

    def call(tiploc: str) -> Call:
        shown = names.get(tiploc.strip().upper(), tiploc.strip())
        return Call(shown, tiploc.strip().casefold(), {}, "", {}, tiploc.strip().upper())

    def finish(c: Call):
        c.details = " ".join(c.fields.values())
        t.calls.append(c)

    for r in rows:
        frm, to = r[3].strip(), r[4].strip()
        start, end = int(r[11] or 0), int(r[9] or 0)
        stop = r[26].strip() == "S"
        if frm == to:                           # the closing line of the train: the platform it arrives at
            if pending is not None and r[19].strip():
                pending.fields["plat"] = r[19].strip()
            continue
        if pending is None:                     # the origin
            c = call(frm)
            c.times["wtt_dep" if stop else "pass"] = clock(start, "wtt_dep" if stop else "pass")
        else:
            c = pending
            if stop:
                if arrival is not None:
                    c.times["wtt_arr"] = clock(arrival, "wtt_arr")
                c.times["wtt_dep"] = clock(start, "wtt_dep")
            else:
                c.times["pass"] = clock(start, "pass")
        if r[19].strip():
            c.fields["plat"] = r[19].strip()
        finish(c)
        pending = call(to)
        arrival = end
        if r[21].strip():
            pending.fields["line"] = r[21].strip()
        for key, sec in zip(("eng", "pth", "prf", "adj"), r[22:26]):
            if sec.strip() not in ("", "0"):
                pending.fields[key] = _minutes(int(sec))
    if pending is not None and arrival is not None:          # the destination: arrival only
        pending.times["wtt_arr"] = clock(arrival, "wtt_arr")
        finish(pending)
    return t
