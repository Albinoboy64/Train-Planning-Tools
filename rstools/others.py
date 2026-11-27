"""Other operators' trains, for the tasks that list trains at a place (berthing charts, platform workings and
CWNs; station books have their own merge): read from the operator's Attune XML, a VPT or a Network Rail CIF.

Such files often have no unit diagrams, so what forms what is not known. Where it is needed it is worked out by
place: a train that ends at a location is taken to form the next train starting there, from the same platform
or road when both give one (first in, first out). A pair that crosses midnight into another day is an overnight
stay; one on the same day is a turnround. The stock type is not known either: the operator code (or the
headcode, on a berthing chart) stands in for it."""
from __future__ import annotations

import os
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Sequence, Set, Tuple

if TYPE_CHECKING:
    from rstools.stationbook import Plan, Train

DAY = 86400
WEEK = 7 * DAY
EMPTY_CLASSES = "035"          # empty stock and light engines: working times shown 'HH+MM'


class OthersError(Exception):
    pass


def load(paths: Sequence[str], log=lambda _m: None) -> list:
    """The plans (stationbook.Plan) of other operators' files: Attune XML, VPT or CIF. Raises OthersError
    with a plain message for a file that cannot be read."""
    from rstools.stationbook import StationBookError, _plan_of
    plans = []
    for p in paths:
        if not os.path.isfile(p):
            raise OthersError(f"This file could not be found:\n{p}")
        log(f"Reading other operator's trains: {os.path.basename(p)}")
        try:
            plans.append(_plan_of(p))
        except (StationBookError, ValueError) as exc:
            raise OthersError(f"{os.path.basename(p)}: {exc}")
        except Exception as exc:                    # a VPT or CIF that cannot be read
            raise OthersError(f"{os.path.basename(p)} could not be read as an Attune XML, VPT or CIF ({exc}).")
    return plans


def operator(plan, train=None) -> str:
    """The train's operator code: from the train (CIF), else the file (XML heading, VPT), else the file name."""
    op = (getattr(train, "operator", "") or plan.operator or "").strip()
    return op or os.path.splitext(os.path.basename(plan.path))[0][:12]


def runs_on(plan, day: int) -> list:
    """The train versions running on a weekday (0 = Monday): for each headcode, the STP over the LTP one."""
    from rstools.stationbook import PLAN_PRIORITY
    out = []
    for versions in plan.trains.values():
        on = [t for t in versions if day in t.days]
        if not on:
            continue
        top = max(PLAN_PRIORITY.get(t.plan.upper(), 0) for t in on)
        out += [t for t in on if PLAN_PRIORITY.get(t.plan.upper(), 0) == top]
    return out


def fleets(plan) -> Dict[str, str]:
    """{headcode: unit type} from the file's unit diagrams, where it has them."""
    out: Dict[str, str] = {}
    for d in plan.diagrams:
        for m in d.moves:
            if m.train and d.fleet:
                out.setdefault(m.train, d.fleet)
    return out


def is_empty(train) -> bool:
    return bool(train.id) and train.id[0] in EMPTY_CLASSES


@dataclass
class End:
    """A train ending (arr) or starting (dep) at a location on a weekday."""
    kind: str                   # 'arr' or 'dep'
    day: int                    # the weekday the train runs (0 = Monday)
    time: int                   # seconds from that day's midnight (past 24:00 after midnight)
    loc: str
    plat: str
    train: "Train"
    plan: "Plan"
    n: int                      # which one (unique among the ends)

    @property
    def at(self) -> int:
        return self.day * DAY + self.time

    @property
    def headcode(self) -> str:
        return self.train.id[:4]


def ends(plans: Iterable, tiplocs: Optional[Set[str]] = None) -> List[End]:
    """Every train's start and end at the locations (all locations when None), on every day it runs."""
    out: List[End] = []
    for plan in plans:
        for day in range(7):
            for t in runs_on(plan, day):
                if not t.calls:
                    continue
                first, last = t.calls[0], t.calls[-1]
                if (tiplocs is None or first.loc in tiplocs) and first.dep is not None:
                    out.append(End("dep", day, first.dep, first.loc, first.plat, t, plan, len(out)))
                if (tiplocs is None or last.loc in tiplocs) and (last.arr is not None or last.dep is not None):
                    out.append(End("arr", day, last.arr if last.arr is not None else last.dep, last.loc, last.plat,
                                   t, plan, len(out)))
    return out


@dataclass
class Link:
    arrive: End
    depart: Optional[End]       # None when no train starts there afterwards within the week
    nights: int                 # 0 = a turnround the same day; 1 = leaves the next day ...


def _plat_key(plat: str) -> str:
    p = (plat or "").strip().upper()
    return p[:-1] if p[:1].isdigit() and p.endswith(("F", "R", "A", "B")) and p[:-1].isdigit() else p


def link(found: Sequence[End]) -> List[Link]:
    """Each arrival paired with the train it forms: the first train starting at the same location afterwards
    (from the same platform or road when both give one), first in first out, over the week and round into the
    next. A pair on different days is an overnight stay of that many nights."""
    by_loc: Dict[str, List[End]] = defaultdict(list)
    for e in found:
        by_loc[e.loc].append(e)
    links: List[Link] = []
    for evs in by_loc.values():
        timeline = sorted([(e.at, e.kind == "arr", e, 0) for e in evs] + [(e.at + WEEK, e.kind == "arr", e, 1)
                                                                          for e in evs],
                          key=lambda x: (x[0], x[1]))       # at the same moment a departure goes first
        waiting: Dict[str, deque] = defaultdict(deque)        # platform -> arrivals waiting, oldest first
        taken: Set[int] = set()
        paired: Dict[int, Tuple[End, int]] = {}
        for at, is_arr, e, lap in timeline:
            if is_arr:
                if lap == 0:
                    waiting[_plat_key(e.plat)].append((e, at))
                continue
            if e.n in taken:
                continue
            key = _plat_key(e.plat)
            queue = None
            if key and waiting.get(key):
                queue = waiting[key]
            elif waiting.get(""):
                queue = waiting[""]
            elif not key:
                queue = min((q for q in waiting.values() if q), key=lambda q: q[0][1], default=None)
            if not queue:
                continue
            arr, arr_at = queue.popleft()
            taken.add(e.n)
            paired[arr.n] = (e, at - arr_at)
        for e in evs:
            if e.kind != "arr":
                continue
            hit = paired.get(e.n)
            if hit is None:
                links.append(Link(e, None, 1))
                continue
            dep, _gap = hit
            nights = (dep.day - e.day) % 7
            if nights == 0 and dep.at + (WEEK if dep.at < e.at else 0) - e.at >= DAY:
                nights = 7
            links.append(Link(e, dep, nights))
    links.sort(key=lambda lk: (lk.arrive.loc, lk.arrive.at))
    return links


def day_code(days: Set[int], cover: Set[int]) -> str:
    """The CWN days code for the days a train runs within the days a CWN covers: '' for all of them, 'MO', 'SuO',
    'MX', 'SX' (Monday to Friday in a CWN without Sunday) or the day letters ('MWO', 'MTWThFO')."""
    from rstools.days import DAY_LETTERS
    days = set(days) & set(cover)
    if not days or days == set(cover):
        return ""
    names = ["MO", "TO", "WO", "ThO", "FO", "SO", "SuO"]
    if len(days) == 1:
        return names[next(iter(days))]
    missing = set(cover) - days
    if len(missing) == 1:
        return names[next(iter(missing))][:-1] + "X"
    return "".join(DAY_LETTERS[d] for d in sorted(days)) + "O"
