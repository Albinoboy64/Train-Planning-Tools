"""Join the TRENT diagram print (mileage, formations) with the Attune XML (calling points,
seconds, public times, names) into one model for a single day of the week."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, cast

from .attune import AttuneData, Leg, Train
from .fleet import FleetTable
from .trent import TrentData, TrentDiagram, is_empty_headcode
from rstools.naming import agree, plural

OPERATOR_DEPOTS = {"SNGX": ("BI", "SU", "SL"), "TLGN": ("HE", "TB")}
OTHER = "Other"
OPERATORS = ("SNGX", "TLGN", OTHER)
_DEPOT_OPERATOR = {dep: op for op, deps in OPERATOR_DEPOTS.items() for dep in deps}
PLAN_PRIORITY = {"STP": 3, "S": 3, "DFT": 2, "DRAFT": 2, "D": 2, "P": 2, "LTP": 1, "L": 1}


def operator_of(depot: str, fleet_operator: str = "") -> str:
    """Operator by depot (SNGX: BI, SU, SL; TLGN: HE, TB); for any other depot, the operator of
    the stock in the fleet table, else 'Other'."""
    op = _DEPOT_OPERATOR.get(depot.upper())
    if op:
        return op
    return fleet_operator if fleet_operator in OPERATOR_DEPOTS else OTHER


def service_type(headcode: str) -> str:
    """Class 5 / 3 / 0 (ECS) moves are 'Empty'; the rest are 'In Service'."""
    return "Empty" if is_empty_headcode(headcode) else "In Service"


@dataclass
class Move:
    """One unit diagram's working of (part of) a train."""
    headcode: str
    origin: str
    dest: str
    dep: int                 # seconds (may exceed 86400 after midnight)
    arr: int
    dep_pub: Optional[int]
    arr_pub: Optional[int]
    miles: Optional[float]
    formation: Tuple[str, ...]    # diagram keys (depot+number) in position order at departure
    legs: List[Leg]               # matching Attune legs (empty if the train was not found)
    found: bool = True            # False when the train is not in the XML
    stype: str = field(init=False)
    wheel: int = field(init=False)

    def __post_init__(self):
        self.stype = service_type(self.headcode)
        # wheel-turning time: leg running times without dwell at intermediate stops, plus any part
        # of the move not in the XML (the whole move when the train is not in the XML)
        if self.legs:
            self.wheel = (sum(leg.arr - leg.dep for leg in self.legs) + max(0, self.arr - self.legs[-1].arr)
                          + max(0, self.legs[0].dep - self.dep))
        else:
            self.wheel = self.arr - self.dep


@dataclass
class Diagram:
    depot: str
    number: str
    fleet: str
    plan: str
    cars: Optional[int]
    length: Optional[float]
    operator: str = OTHER
    moves: List[Move] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.depot}{self.number}"


@dataclass
class Part:
    """A section of a train with one (ordered) formation - one 'Formation Data' row."""
    headcode: str
    origin: str
    dest: str
    dep: int
    arr: int
    dep_pub: Optional[int]
    arr_pub: Optional[int]
    miles: Optional[float]
    formation: Tuple[str, ...]
    legs: List[Leg]
    ends: str = "End of Service"


@dataclass
class TrainRun:
    headcode: str
    parts: List[Part]
    legs: List[Leg]

    @property
    def origin(self): return self.parts[0].origin

    @property
    def dest(self): return self.parts[-1].dest

    @property
    def dep(self): return self.parts[0].dep

    @property
    def arr(self): return self.parts[-1].arr

    @property
    def miles(self) -> Optional[float]:
        if any(p.miles is None for p in self.parts):
            return None
        return sum(cast(float, p.miles) for p in self.parts)

    @property
    def stype(self): return service_type(self.headcode)


@dataclass
class DayModel:
    day: int
    diagrams: List[Diagram]              # included (operator + fleet filtered)
    all_diagrams: Dict[str, Diagram]     # every diagram running this day (for formation lookups)
    trains: List[TrainRun]
    locations: Dict[str, str]
    fleet: FleetTable
    warnings: List[str]

    def name(self, tiploc: str) -> str:
        if tiploc in self.locations:
            return self.locations[tiploc]
        return tiploc if any(ch.islower() for ch in tiploc) else ""      # a TLGN print gives names


# --------------------------------------------------------------------------- #
def _pick_diagrams(trent: TrentData, day: int) -> Tuple[List[TrentDiagram], List[str]]:
    """Diagrams running on `day`; where LTP and STP/draft versions of the same diagram both
    run, the STP (or draft) version is used."""
    best: Dict[str, TrentDiagram] = {}
    replaced = set()
    for d in trent.diagrams:
        if day not in d.days:
            continue
        old = best.get(d.key)
        if old is not None:
            replaced.add(d.key)
        if old is None or PLAN_PRIORITY.get(d.plan.upper(), 0) > PLAN_PRIORITY.get(old.plan.upper(), 0):
            best[d.key] = d
    notes = [f"{plural(len(replaced), 'diagram')} {agree(len(replaced), 'has', 'have')} more than one version on "
             "this day; the STP (or draft) version "
             f"was used (e.g. {', '.join(sorted(replaced)[:8])})."] if replaced else []
    return list(best.values()), notes


MAX_PAUSE = 120       # minutes: longest stop (e.g. stabled) within one move of the same train
LOC_TOL = 3 * 60      # seconds: TRENT and Attune times at the same location may differ by rounding / public times
TIME_TOL = 60         # seconds: matching on time alone (depot moves where TRENT and Attune use different TIPLOCs)


def _gap(trent_min: int, xml_sec: int) -> int:
    """Seconds between a TRENT time (minutes, may pass 24:00) and an XML time, ignoring the day."""
    d = (trent_min * 60 - xml_sec) % 86400
    return min(d, 86400 - d)


def _best_leg(legs, rng, loc_attr, time_attr, loc, minute):
    """Index of the leg in `rng` best matching location + time; time alone as a fallback. `loc` is a
    TIPLOC or a set of TIPLOCs (a TLGN print names the station)."""
    best, best_gap = None, None
    locs = loc if isinstance(loc, (set, frozenset)) else {loc}
    for k in rng:
        leg = legs[k]
        g = _gap(minute, getattr(leg, time_attr))
        if getattr(leg, loc_attr) in locs and g <= LOC_TOL:
            g -= 1000                        # a location match always wins over time alone
        elif g > TIME_TOL:
            continue
        if best_gap is None or g < best_gap:
            best, best_gap = k, g
    return best, best_gap


def _new_train_here(attune, headcode: str, day: int, loc: str, arr_min: int, dep_min: int) -> bool:
    """A 4-character print headcode (VehicleLayout23 / 11 / 05) that is two trains in the XML: one ending here
    and another, with a different full ID, starting here (e.g. 5Y47GS reversing as 5Y47GT). VehicleLayout29
    shows them as two moves, so they are kept apart."""
    if attune is None or len(headcode) != 4 or not attune.trains:
        return False
    ends, starts = set(), set()
    for hc in _short_index(attune).get(headcode, ()):
        for t in attune.trains[hc]:
            if not t.legs or not ({day, (day + arr_min // 1440) % 7} & t.days):
                continue
            if t.legs[-1].dest == loc and _gap(arr_min, t.legs[-1].arr) <= LOC_TOL:
                ends.add(t.id)
            if t.legs[0].origin == loc and _gap(dep_min, t.legs[0].dep) <= LOC_TOL:
                starts.add(t.id)
    return bool(ends and starts and not ends & starts)


def _short_index(attune) -> Dict[str, List[str]]:
    idx = getattr(attune, "_short", None)
    if idx is None:
        idx = defaultdict(list)
        for hc in attune.trains:
            idx[hc[:4]].append(hc)
        attune._short = idx
    return idx


def _as_set(x):
    return x if isinstance(x, (set, frozenset)) else {x}


def _tiplocs(attune, loc: str):
    """A TRENT location as XML TIPLOC(s): itself, or the TIPLOCs whose name it is (TLGN prints)."""
    if loc in attune.locations:
        return loc
    names = getattr(attune, "_by_name", None)
    if names is None:
        names = defaultdict(set)
        for tip, name in attune.locations.items():
            names[" ".join(name.replace(".", " ").casefold().split())].add(tip)
        attune._by_name = names
    return names.get(" ".join(loc.replace(".", " ").casefold().split())) or loc


def _find_train(attune: Optional[AttuneData], headcode: str, day: int, origin: str, dep_min: int,
                dest: str, arr_min: Optional[int]) -> Tuple[Optional[Train], List[Leg], int]:
    """Locate the Attune train version and the legs from origin (dep) to dest (arr).
    Returns (train, legs, offset) where offset (seconds, whole days) aligns XML times with TRENT.
    Times may differ by a few minutes (TRENT rounds seconds and can show public times), and depot
    moves may use different TIPLOCs in the two systems, so the closest match in time is taken."""
    if attune is None:
        return None, [], 0
    best = None
    origin, dest = _tiplocs(attune, origin), _tiplocs(attune, dest)
    versions = attune.trains.get(headcode, ())
    if not versions and len(headcode) == 4:            # TLGN print: '2L98' for the XML's '2L98GR'
        versions = [t for hc in _short_index(attune).get(headcode, ()) for t in attune.trains[hc]]
    run_day = (day + dep_min // 1440) % 7              # after midnight the XML files the train under the next day
    for t in versions:
        if day not in t.days and run_day not in t.days:
            continue
        legs = t.legs
        i, gi = _best_leg(legs, range(len(legs)), "origin", "dep", origin, dep_min)
        if i is None:
            continue
        offset = round((dep_min * 60 - legs[i].dep) / 86400) * 86400
        if arr_min is None:
            j, gj = len(legs) - 1, 0
        else:
            j, gj = _best_leg(legs, range(i, len(legs)), "dest", "arr", dest, arr_min)
            if j is None:
                # the XML train may end before the TRENT move does (TRENT continues within a depot)
                j = len(legs) - 1
                if arr_min * 60 - (legs[j].arr + offset) < -LOC_TOL:
                    continue
                gj = 500
        # after midnight the version filed under the next day is the one; before it, the diagram's own day
        right_day = (run_day if dep_min >= 1440 else day) in t.days
        score = (PLAN_PRIORITY.get(t.plan.upper(), 0), right_day, -(gi + gj))
        if best is None or score > best[0]:
            best = (score, t, legs[i:j + 1], offset)
    if best is None:
        return None, [], 0
    return best[1], best[2], best[3]


def build_day(trent: TrentData, attune: Optional[AttuneData], fleet: FleetTable, day: int,
              operators: Set[str], fleets: Optional[Set[str]] = None, report_missing: bool = True) -> DayModel:
    warnings: List[str] = []
    picked, notes = _pick_diagrams(trent, day)
    warnings.extend(notes)
    all_diags: Dict[str, Diagram] = {}
    # place names for this run: the XML's, plus print names matched to TIPLOCs below. A copy, so the parsed XML
    # (shared with the file cache and other runs) is never changed and every run gives the same result
    names: Dict[str, str] = dict(attune.locations) if attune else {}
    for td in picked:
        info = fleet.get(td.fleet)
        dg = Diagram(td.depot, td.number, td.fleet, td.plan, info.cars if info else None,
                     info.length if info else None, operator_of(td.depot, info.operator if info else ""))
        all_diags[dg.key] = dg
        _build_moves(dg, td, attune, day, names)
    running = list(all_diags.values())               # before other days' diagrams are added for look-ups
    _resolve_formations(all_diags, trent, fleet)
    included = [d for d in running
                if d.operator in operators and (fleets is None or d.fleet in fleets)]
    if attune is not None and report_missing:
        missing = sorted({m.headcode for d in included for m in d.moves if not m.found})
        if missing:
            warnings.append(f"{plural(len(missing), 'train')} in the TRENT print "
                            f"{agree(len(missing), 'was', 'were')} not found in the XML for this day "
                            f"(e.g. {', '.join(missing[:12])}). Their calling points and seconds come from the "
                            "TRENT print instead - check the XML is from the same plan as the TRENT print.")
    trains = _build_trains(included)
    return DayModel(day=day, diagrams=sorted(included, key=lambda d: (d.fleet, d.depot, _num(d.number))),
                    all_diagrams=all_diags, trains=trains,
                    locations=names, fleet=fleet, warnings=warnings)


def _resolve_formations(all_diags: Dict[str, Diagram], trent: TrentData, fleet: FleetTable):
    """TRENT lists the coupled units by diagram number only ('164(1)\\312(2)'), and the other
    diagrams may be from another depot (e.g. a BI 377/4 coupled to SU312, a 377/3). Each number is
    matched to the diagram that works the same train at the same time - normally the only diagram
    with that number - preferring the diagram's own depot. Diagrams that only run on another day
    (e.g. continuing past midnight) are looked up in the rest of the print."""
    by_num: Dict[str, List[Diagram]] = defaultdict(list)
    for d in all_diags.values():
        by_num[d.number].append(d)
    works = {(d.key, m.headcode, m.dep) for d in all_diags.values() for m in d.moves}
    elsewhere: Dict[str, Diagram] = {}
    for td in trent.diagrams:                         # other days' diagrams, for stock look-ups only
        if td.number not in by_num and td.number not in elsewhere:
            info = fleet.get(td.fleet)
            elsewhere[td.number] = Diagram(td.depot, td.number, td.fleet, td.plan, info.cars if info else None,
                                           info.length if info else None)
    cache: Dict[tuple, str] = {}
    for d in list(all_diags.values()):
        for m in d.moves:
            keys = []
            for num in m.formation:
                ck = (num, d.depot, m.headcode, m.dep)
                key = cache.get(ck)
                if key is None:
                    cands = by_num.get(num, [])
                    if len(cands) > 1:
                        cands = ([c for c in cands if (c.key, m.headcode, m.dep) in works] or cands)
                        cands.sort(key=lambda c: c.depot != d.depot)
                    if cands:
                        key = cands[0].key
                    elif num in elsewhere:
                        key = elsewhere[num].key
                        all_diags.setdefault(key, elsewhere[num])
                    else:
                        key = f"{d.depot}{num}"        # not in the print at all: shown as '?'
                    cache[ck] = key
                keys.append(key)
            m.formation = tuple(keys)


def _num(n: str):
    digits = "".join(ch for ch in n if ch.isdigit())
    return (int(digits) if digits else 0, n)


def _build_moves(dg: Diagram, td: TrentDiagram, attune, day, names: Dict[str, str]):
    rows = td.rows
    i = 0
    while i < len(rows):
        r = rows[i]
        if not r.headcode or r.dep is None:
            i += 1
            continue
        # A move carries on through activity lines (reverse, stable, wash, CET...) while the same
        # train - same headcode, same units - departs again afterwards.
        miles = r.miles
        unknown = r.miles is None
        units = set(r.positions)
        j = i + 1
        end_loc, end_arr = None, None
        while j < len(rows):
            nxt = rows[j]
            if nxt.loc != end_loc or nxt.arr is not None:     # a line without times keeps the arrival
                end_loc = nxt.loc
                end_arr = nxt.arr if nxt.arr is not None else nxt.dep
            if nxt.headcode:
                if nxt.headcode != r.headcode or set(nxt.positions) != units or (
                        nxt.arr is not None and nxt.dep is not None
                        and _new_train_here(attune, r.headcode, day, nxt.loc, nxt.arr, nxt.dep)):
                    break
                miles = None if (unknown or nxt.miles is None) else cast(float, miles) + nxt.miles
                unknown = unknown or nxt.miles is None
                j += 1
                continue
            k = j + 1
            while k < len(rows) and not rows[k].headcode:
                k += 1
            again = rows[k] if k < len(rows) else None
            if (again is None or again.headcode != r.headcode or set(again.positions) != units
                    or again.dep is None or end_arr is None or again.dep - end_arr > MAX_PAUSE
                    or _new_train_here(attune, r.headcode, day, end_loc, end_arr, again.dep)):
                break
            j += 1
        if end_loc is None:
            i = j
            continue
        if end_arr is None:
            end_arr = r.dep
        train, legs, offset = _find_train(attune, r.headcode, day, r.loc, r.dep, end_loc, end_arr)
        if legs:
            dep = legs[0].dep + offset
            arr = legs[-1].arr + offset
            dep_pub = legs[0].dep_pub + offset if legs[0].dep_pub is not None else None
            arr_pub = legs[-1].arr_pub + offset if legs[-1].arr_pub is not None else None
            if end_arr * 60 - arr > LOC_TOL:      # TRENT carries on (in a depot) after the XML train ends
                arr, arr_pub = end_arr * 60, None
            if offset:
                legs = [Leg(l.origin, l.dep + offset, l.dest, l.arr + offset,
                            None if l.dep_pub is None else l.dep_pub + offset,
                            None if l.arr_pub is None else l.arr_pub + offset,
                            l.origin_stop, l.dest_stop, l.origin_pass_kind, l.dest_pass_kind) for l in legs]
        else:
            dep, arr, dep_pub, arr_pub = r.dep * 60, end_arr * 60, None, None
        start_loc, stop_loc = r.loc, end_loc
        if legs and attune is not None:                   # a TLGN print names places: use the XML's TIPLOCs
            # (same name, or - where TRENT and Attune name a place differently - the XML train leaving /
            # arriving within a minute of the print's time there)
            if start_loc not in names and (legs[0].origin in _as_set(_tiplocs(attune, start_loc))
                                           or abs(dep - r.dep * 60) <= 60):
                names.setdefault(legs[0].origin, start_loc)    # e.g. MRGT has no name in the XML
                start_loc = legs[0].origin
            if stop_loc not in names and (legs[-1].dest in _as_set(_tiplocs(attune, stop_loc))
                                          or abs(arr - end_arr * 60) <= 60):
                names.setdefault(legs[-1].dest, stop_loc)
                stop_loc = legs[-1].dest
        formation = tuple(r.positions) or (dg.number,)    # diagram numbers; depots resolved later
        headcode = r.headcode                             # a 4-character print headcode: the XML's full ID
        if train is not None and len(headcode) == 4 and train.id[:4] == headcode:
            headcode = train.id
        dg.moves.append(Move(headcode, start_loc, stop_loc, dep, arr, dep_pub, arr_pub,
                             None if unknown else round(cast(float, miles), 4), formation, legs,
                             found=train is not None))
        i = j


def _build_trains(included: List[Diagram]) -> List[TrainRun]:
    """Group the included diagrams' moves into trains, split into formation parts."""
    by_train: Dict[str, Dict[Tuple[int, str], Move]] = defaultdict(dict)
    for d in included:
        for m in d.moves:
            seg = (m.dep, m.origin)
            prev = by_train[m.headcode].get(seg)
            if prev is None or (prev.miles is None and m.miles is not None):
                by_train[m.headcode][seg] = m
    out = []
    for hc, segs in by_train.items():
        moves = sorted(segs.values(), key=lambda m: m.dep)
        parts: List[Part] = []
        for m in moves:
            if parts and parts[-1].dest == m.origin and set(parts[-1].formation) == set(m.formation) \
                    and parts[-1].arr <= m.dep:
                p = parts[-1]
                p.dest, p.arr, p.arr_pub = m.dest, m.arr, m.arr_pub
                p.miles = None if p.miles is None or m.miles is None else p.miles + m.miles
                p.legs = p.legs + m.legs
                continue
            if parts and parts[-1].arr > m.dep:
                continue        # overlapping section already covered by another unit
            parts.append(Part(hc, m.origin, m.dest, m.dep, m.arr, m.dep_pub, m.arr_pub, m.miles,
                              m.formation, list(m.legs)))
        for k, p in enumerate(parts):
            p.ends = "End of Service" if k == len(parts) - 1 else "Change of Formation"
        legs = [leg for p in parts for leg in p.legs]
        out.append(TrainRun(hc, parts, legs))
    out.sort(key=lambda t: (t.headcode, t.dep))
    return out
