"""Where each unit berths overnight: from the end of one day's diagram (the arrival, a 'finish' on the chart)
to the start of the diagram it works next (the departure, a 'start'), following Attune's next-day working
notes. A unit that does not work for a day or more shows 'Berth' on those days."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from rstools.statspack.days import DAY_NAMES, days_of_code
from rstools.statspack.model import PLAN_PRIORITY
from rstools.statspack.trent import is_empty_headcode

from .xmlread import BerthXML, Move, TrainVersion, UnitDiagram, platform

# 'BI8 05+03TO (R)': next diagram, its departure time, the day it runs and the unit's position (front/rear)
_NOTE = re.compile(r"^\s*([A-Z]{1,4})\s*(\d+[A-Z]?)\s+(\d{1,2})[:+.](\d{2})\s*([A-Za-z]*)\s*(?:\(([FMR])\))?")


@dataclass
class End:
    """One end of a stay: the train that brings the unit in (arrival) or takes it out (departure)."""
    day: int                    # weekday of the diagram, 0 = Monday
    time: int                   # seconds from that day's midnight (past 24:00 just after midnight)
    train: str                  # headcode
    plat: str                   # platform / siding road at the location ('' if the XML gives none)
    ecs: bool                   # an empty (class 5/3/0) move
    stp: bool                   # from an STP diagram (marked only when an STP input is attached)
    group: Tuple[int, str]      # (XML, trainKey): units on the same train share it
    coupled: List[str]          # the units on that train, front first ([] for a unit on its own)
    rp: bool = False            # leaves as the rear portion of a unit that moved in that day


@dataclass
class Stay:
    unit: str                   # the diagram the unit works on its arrival day, e.g. 'BI19'
    fleet: str                  # '387/3'
    loc: str                    # TIPLOC it berths at
    plat: str                   # platform / road it berths on
    first_night: int            # weekday of the first night (the arrival day)
    nights: int                 # 1 = leaves the next day; 3 = berthed for two whole days as well
    arrive: End
    depart: Optional[End]       # None when the XML does not say what the unit works next


@dataclass
class Visit:
    """A diagram ending or starting at a location (depot sheets list these without linking them)."""
    day: int
    time: int
    train: str
    fleet: str
    ecs: bool
    stp: bool


@dataclass
class Berthing:
    stays: List[Stay]
    finishes: Dict[str, List[Visit]]        # TIPLOC -> diagrams ending there
    starts: Dict[str, List[Visit]]          # TIPLOC -> diagrams starting there
    days: Set[int]                          # weekdays the XML(s) have diagrams for
    warnings: List[str] = field(default_factory=list)
    unlinked: int = 0                       # stays whose next working is not in the XML


def _choose(xmls: Sequence[BerthXML]) -> Dict[Tuple[int, str], UnitDiagram]:
    """The diagram that runs for each (weekday, diagram): STP over LTP, then the later XML (an STP export
    attached after the LTP one) over the earlier."""
    best: Dict[Tuple[int, str], UnitDiagram] = {}
    rank: Dict[Tuple[int, str], Tuple[int, int]] = {}
    for x in xmls:
        for d in x.diagrams:
            r = (PLAN_PRIORITY.get(d.plan.upper(), 0), d.source)
            for day in d.days:
                if (day, d.key) not in rank or r >= rank[(day, d.key)]:
                    best[(day, d.key)], rank[(day, d.key)] = d, r
    return best


def _next_day(day: int, code: str) -> int:
    allowed = days_of_code(code) if code else set()
    allowed = allowed or {(day + 1) % 7}
    return next((day + k) % 7 for k in range(1, 8) if (day + k) % 7 in allowed)


def build(xmls: Sequence[BerthXML], mark_stp: bool = False) -> Berthing:
    """Every overnight stay in the XML(s). With several XMLs (an LTP and an STP export), each day's STP
    diagrams replace the LTP ones; `mark_stp` flags the arrivals and departures that come from STP."""
    best = _choose(xmls)
    trains: Dict[Tuple[int, str], TrainVersion] = {(x.diagrams[0].source if x.diagrams else 0, k): t
                                                   for x in xmls for k, t in x.trains.items()}

    def train_of(d: UnitDiagram, m: Move) -> Optional[TrainVersion]:
        return trains.get((d.source, m.key))

    def is_stp(d: UnitDiagram) -> bool:
        return mark_stp and d.plan.upper() == "S"

    stays: List[Stay] = []
    finishes: Dict[str, List[Visit]] = defaultdict(list)
    starts: Dict[str, List[Visit]] = defaultdict(list)
    days = {day for day, _k in best}
    claimed: Dict[Tuple[int, str], Stay] = {}
    unlinked = clashes = elsewhere = 0
    for (day, key), d in sorted(best.items(), key=lambda kv: (kv[0][0], kv[1].moves[-1].arr if kv[1].moves else 0,
                                                            kv[0][1])):
        if not d.moves:
            continue                            # a diagram that only stands somewhere: part of a stay below
        first, last = d.moves[0], d.moves[-1]
        starts[first.origin].append(Visit(day, first.dep, first.train, d.fleet, is_empty_headcode(first.train),
                                          is_stp(d)))
        finishes[last.dest].append(Visit(day, last.arr, last.train, d.fleet, is_empty_headcode(last.train),
                                         is_stp(d)))
        loc = last.dest
        arrive = End(day, last.arr, last.train, platform(train_of(d, last), loc, True),
                     is_empty_headcode(last.train), is_stp(d), (d.source, last.key), list(last.coupled))
        # follow the next-day working, through any diagrams in which the unit only stands (still berthed)
        nights, at, notes, depart, nxt = 0, day, d.notes, None, None
        for _hop in range(7):
            m = next((m for m in (_NOTE.match(n) for n in notes) if m), None)
            if m is None:
                break
            nday = _next_day(at, m.group(5))
            nights += (nday - at) % 7 or 7
            nxt = best.get((nday, m.group(1) + m.group(2)))
            if nxt is None:
                break
            if nxt.moves:
                fm = nxt.moves[0]
                depart = End(nday, fm.dep, fm.train, platform(train_of(nxt, fm), fm.origin, False),
                             is_empty_headcode(fm.train), is_stp(nxt), (nxt.source, fm.key), list(fm.coupled))
                if fm.origin != loc:
                    elsewhere += 1
                depart.rp = _moved_in_front(best, nday, nxt.key, fm)
                break
            at, notes = nday, nxt.notes
            if nights >= 7:
                break
        if depart is None or nxt is None:
            unlinked += 1
            stays.append(Stay(key, d.fleet, loc, arrive.plat, day, 1, arrive, None))
            continue
        stay = Stay(key, d.fleet, loc, arrive.plat, day, min(max(nights, 1), 7), arrive, depart)
        target = (depart.day, nxt.key)
        if target in claimed:                   # two units cannot form the same diagram: keep the first
            clashes += 1
            stay.depart, stay.nights = None, 1
        else:
            claimed[target] = stay
        stays.append(stay)
    warnings = []
    missing = [DAY_NAMES[i] for i in range(7) if i not in days]
    if missing:
        warnings.append("The XML has no diagrams for " + ", ".join(missing) + ", so those days are empty. "
                        "Use an export covering the whole week.")
    if clashes:
        warnings.append(f"{clashes} next-day working(s) name a diagram another unit already forms; the first was "
                        "kept and the other shows only its arrival. Check the plan.")
    if elsewhere:
        warnings.append(f"{elsewhere} unit(s) start their next diagram away from where they berthed (a move the "
                        "diagrams do not show).")
    return Berthing(stays, dict(finishes), dict(starts), days, warnings, unlinked)


def _moved_in_front(best: Dict[Tuple[int, str], UnitDiagram], day: int, key: str, fm: Move) -> bool:
    """RP: the berthed unit leaves as the rear portion, attached to by a unit in front of it that moved in that
    day (its previous move that day arrived at the berth)."""
    if len(fm.coupled) < 2 or key not in fm.coupled:
        return False
    for other in fm.coupled[:fm.coupled.index(key)]:
        d = best.get((day, other))
        if d is None:
            continue
        idx = next((i for i, m in enumerate(d.moves) if m.key == fm.key and m.origin == fm.origin), None)
        if idx and d.moves[idx - 1].dest == fm.origin:
            return True
    return False
