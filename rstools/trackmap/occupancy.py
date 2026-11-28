"""Where every unit stands at a station or siding through one day, from an Attune XML's unit diagrams (the same
reading as berthing charts: rstools.berthing.xmlread): for each unit, each time it is at one of the place's locations,
on which platform or road, from when to when, the train it arrived as and the one it leaves as, and the units it is
coupled to (front first)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DAY = 86400
END = 30 * 3600                     # the day shown runs to 06:00 the next morning (units stabled overnight)


@dataclass
class Stand:
    """One unit at one location, on one platform or road, for a while."""
    unit: str                       # diagram key, e.g. 'BI19'
    fleet: str                      # '377/4'
    loc: str                        # TIPLOC
    plat: str                       # platform or road as the XML gives it ('' if not given)
    start: int                      # seconds from the day's midnight
    end: int
    arrived_as: str                 # headcode ('' when the unit was there at the start of the day)
    leaves_as: str                  # headcode ('' when it is still there at the end)
    formation: Tuple[str, ...]      # the units it stands with, front first (from the train it arrived as)
    order: int = 0                  # its place in that formation (0 = front)
    passing: bool = False           # a call in the middle of a train's journey (not standing between trains)
    was: str = ""                   # the diagram it arrived on, when it then forms another (BI1 -> BI10)

    def at(self, t: int) -> bool:
        return self.start <= t < self.end


def _times(call, base: int) -> Tuple[Optional[int], Optional[int]]:
    arr = None if call.arr is None else call.arr + base
    dep = None if call.dep is None else call.dep + base
    return arr, dep


def _calls_on_move(train, move) -> List[Tuple[Any, Optional[int], Optional[int]]]:
    """The train's calls during this move (its part of the train), with times on the diagram's own clock (a train
    timed from its own midnight is moved by whole days to match the move)."""
    if train is None or not train.calls:
        return []
    first = next((c for c in train.calls if c.loc == move.origin and c.dep is not None), None)
    shift = 0
    if first is not None:
        shift = round((move.dep - first.dep) / DAY) * DAY
    out = []
    inside = False
    for c in train.calls:
        arr, dep = _times(c, shift)
        if not inside and c.loc == move.origin and dep is not None and abs(dep - move.dep) <= 120:
            inside = True
        if inside:
            out.append((c, arr, dep))
            if c.loc == move.dest and arr is not None and abs(arr - move.arr) <= 120:
                break
    return out


def stands(xml, locs: Iterable[str], day: int) -> List[Stand]:
    """Every unit's stands at these locations (TIPLOCs) on `day` (0 = Monday), from the BerthXML `xml`."""
    want = set(locs)
    out: List[Stand] = []
    for d in xml.diagrams:
        if day not in d.days or (d.fleet or "").upper() == "MAINT":
            continue
        moves = sorted(d.moves, key=lambda m: m.dep)
        here: Optional[Tuple[str, str, int, str, Tuple[str, ...]]] = None   # loc, plat, since, arrived as, formation
        for m in moves:
            train = xml.trains.get(m.key)
            calls = _calls_on_move(train, m)
            form = tuple(m.coupled) or (d.key,)
            if m.origin in want:
                plat = next((c.plat for c, _a, _d in calls if c.loc == m.origin), "") or (here[1] if here else "")
                since, arrived, f0 = (here[2], here[3], here[4]) if here and here[0] == m.origin else (0, "", form)
                if m.dep > since:
                    out.append(Stand(d.key, d.fleet, m.origin, plat, since, m.dep, arrived, m.train, f0,
                                     f0.index(d.key) if d.key in f0 else 0))
            for c, arr, dep in calls[1:-1]:                 # calls on the way, where the train waits
                if c.loc in want and c.stops and arr is not None and dep is not None and dep > arr:
                    out.append(Stand(d.key, d.fleet, c.loc, c.plat, arr, dep, m.train, m.train, form,
                                     form.index(d.key) if d.key in form else 0, passing=True))
            plat = next((c.plat for c, _a, _d in reversed(calls) if c.loc == m.dest), "")
            here = (m.dest, plat, m.arr, m.train, form)
        if here and here[0] in want and here[2] < END:
            out.append(Stand(d.key, d.fleet, here[0], here[1], here[2], END, here[3], "", here[4],
                             here[4].index(d.key) if d.key in here[4] else 0))
    out = _join_next(out, {d.key: d for d in xml.diagrams if day in d.days})
    out.sort(key=lambda s: (s.loc, s.plat, s.start, s.order))
    return out


_NEXT = re.compile(r"^\s*([A-Z]{1,4})\s*(\d+[A-Z]?)\s+(\d{1,2})[:+.](\d{2})")


def _join_next(found: List[Stand], diagrams) -> List[Stand]:
    """A unit that arrives in the small hours and then forms another diagram the same morning (its end note says
    so: 'BI10 05:00') is one unit: its arrival and the other diagram's 'there from the start of the day' are joined
    into one stand, so it is not drawn twice."""
    first = {(s.unit, s.loc): s for s in found if not s.arrived_as and s.start == 0}
    drop = set()
    for s in found:
        if s.leaves_as or s.end != END:
            continue
        d = diagrams.get(s.unit)
        nxt = next((m for m in (_NEXT.match(n) for n in getattr(d, "notes", []) or []) if m), None)
        if nxt is None:
            continue
        follow = first.get((nxt.group(1) + nxt.group(2), s.loc))
        if follow is not None and s.start < follow.end:      # it arrives before the next diagram leaves
            follow.start, follow.arrived_as, follow.was = s.start, s.arrived_as, s.unit
            follow.formation, follow.order = s.formation, s.order
            drop.add(id(s))
    return [s for s in found if id(s) not in drop]


def present(all_stands: Sequence[Stand], t: int) -> Dict[Tuple[str, str], List[Stand]]:
    """The units on each (location, platform / road) at time t, in the order they stand from the stop end: those
    that arrived first nearest it, and within a train its formation from the front."""
    by: Dict[Tuple[str, str], List[Stand]] = {}
    for s in all_stands:
        if s.at(t):
            by.setdefault((s.loc, s.plat), []).append(s)
    for group in by.values():
        group.sort(key=lambda s: (s.start, s.order))
    return by


def place_locations(xml_locations: Dict[str, str], place: str) -> List[str]:
    """The XML's locations that are part of a place: its name, and those named after it ('Brighton', 'Brighton Wall
    Siding', 'Brighton Down Siding'), not junctions or signals."""
    key = " ".join(place.split()).casefold()
    out = []
    for tip, name in xml_locations.items():
        n = " ".join(name.split()).casefold()
        if (n == key or n.startswith(key + " ")) and not any(w in n for w in (" jn", "junction", "signal", " sig ")):
            out.append(tip)
    return sorted(out)
