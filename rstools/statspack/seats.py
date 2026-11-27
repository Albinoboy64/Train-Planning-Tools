"""Capacity report: the seats and standing room of passenger trains, per day or for the week, optionally only
trains at a chosen station between two times. Trains are chosen in one of three ways:

* Service group: a headcode group such as 1F, 1W or 2F (the first two characters of the headcode),
  listed from the XML.
* Corridor: a main route, in one direction or both. Each corridor is an ordered list of stations (an
  editable list, groups.csv, with a built-in starting list); a train is on it when it calls at or
  passes at least two of them, and its direction is the order it reaches them in.
* Station to station: trains calling at one station and later at another (every station in the XML).

Seats come from the fleet data for each unit in the formation (First, Standard, standing).
"""
from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, cast

from rstools.days import DAY_NAMES
from .fleet import FleetTable, user_fleet_path
from .model import DayModel, Part, TrainRun
from .units import Report
from rstools.naming import plural

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GROUPS = os.path.join(HERE, "groups_default.csv")
KINDS = ("Service group", "Corridor")
JOURNEY = "Station to station"
# the built-in lists of earlier versions: a user copy still identical to one of them is brought up to date
_OLD_DEFAULTS = {"92aca267c11cc13e",             # 3.6.0 - 3.7.0
                 "619079e8b9dcef30"}             # 3.8.0 - 3.9.x (before the TLGN corridors)
DAY_SECONDS = 86400


class SeatsError(Exception):
    pass


# --------------------------------------------------------------------------- #
# service groups and corridors
# --------------------------------------------------------------------------- #
def user_groups_path() -> str:
    return os.path.join(os.path.dirname(user_fleet_path()), "groups.csv")


def _digest(text: str) -> str:
    import hashlib
    norm = "\n".join(line.rstrip() for line in text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def ensure_user_groups() -> str:
    """The editable corridor list (created from the built-in one on first use, and replaced by the new
    built-in list when it was never edited)."""
    path = user_groups_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                stale = _digest(fh.read()) in _OLD_DEFAULTS
        except (OSError, UnicodeDecodeError):
            stale = False
        if stale:
            try:
                from rstools.fsutil import unique_stem
                folder, name = os.path.split(path)
                os.replace(path, os.path.join(folder, unique_stem(folder, name, (".old",)) + ".old"))
            except OSError:                    # an earlier backup is kept: a new one gets ' (2)'
                pass
    if not os.path.exists(path):
        from rstools.fsutil import copy_default
        if not copy_default(DEFAULT_GROUPS, path):
            return DEFAULT_GROUPS
    return path


def _split(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[;\n]", text or "") if s.strip()]


def shown(spec: str) -> str:
    """A station as written in the corridor list, for display ('A|B' -> 'A')."""
    return spec.split("|")[0].strip()


DIRECTION_WORDS = {"forward": "{a} to {b}", "reverse": "{b} to {a}", "both": "both directions"}


@dataclass
class Group:
    kind: str                   # Service group | Corridor | Station to station
    name: str
    route: List[str]
    also: List[str] = field(default_factory=list)
    not_via: List[str] = field(default_factory=list)
    fleets: List[str] = field(default_factory=list)       # '-387/2' = not this fleet
    minimum: int = 2
    headcodes: List[str] = field(default_factory=list)    # headcode starts, e.g. '1W'; '-2T' = not these
    direction: str = "both"     # corridors: forward (first to last route station) | reverse | both
    journey: Tuple[str, str] = ("", "")                    # station to station: (from, to)

    @property
    def direction_text(self) -> str:
        if self.kind != "Corridor" or len(self.route) < 2:
            return ""
        return DIRECTION_WORDS.get(self.direction, "").format(a=shown(self.route[0]), b=shown(self.route[-1]))

    @property
    def label(self) -> str:
        if self.kind == JOURNEY:
            return f"{self.journey[0]} to {self.journey[1]}"
        if self.kind == "Corridor":
            return f"{self.kind}: {self.name}, {self.direction_text}"
        return f"{self.kind}: {self.name}"

    def with_direction(self, direction: str) -> "Group":
        from dataclasses import replace
        return replace(self, direction=direction if direction in DIRECTION_WORDS else "both")


def headcode_group(code: str) -> Group:
    """A service group of every train whose headcode starts with `code` (e.g. '1F')."""
    return Group("Service group", code.upper(), [], headcodes=[code.upper()], minimum=0)


def default_headcode_groups() -> List[Tuple[str, str]]:
    """[(code, description)] from the built-in list of GTR (SNGX and TLGN) headcode groups, worded as in Network
    Rail's Timetable Planning Rules (headcode tables of the Sussex, Kent, East Midlands and LNE rules); shown
    until an XML is chosen, and used to describe the XML's own groups."""
    import csv
    try:
        with open(os.path.join(HERE, "service_groups_default.csv"), encoding="utf-8-sig") as fh:
            return [(r["Headcode group"].strip(), r["Description"].strip()) for r in csv.DictReader(fh)
                    if (r.get("Headcode group") or "").strip()]
    except (OSError, KeyError):
        return []


def journey_group(origin: str, dest: str) -> Group:
    return Group(JOURNEY, f"{origin} to {dest}", [], minimum=0, journey=(origin.strip(), dest.strip()))


def headcode_groups(attune) -> List[Tuple[str, str]]:
    """[(code, description)] for each passenger headcode group in the XML, e.g. ('1F', 'London Victoria / London
    Bridge and Eastbourne / Hastings / Ore / Seaford (43 trains)'): the built-in description, else the group's
    two commonest routes in the XML. Empty stock (classes 0, 3, 5) is left out."""
    from collections import Counter
    if attune is None:
        return []
    names = attune.locations
    routes: Dict[str, Counter] = defaultdict(Counter)
    seen: Dict[str, set] = defaultdict(set)
    for hc, versions in attune.trains.items():
        if len(hc) < 2 or hc[0] not in "1289":
            continue
        code = hc[:2].upper()
        seen[code].add(hc)
        for t in versions:
            if t.legs:
                a, b = names.get(t.legs[0].origin, t.legs[0].origin), names.get(t.legs[-1].dest, t.legs[-1].dest)
                a, b = (re.sub(r"\s*\(C\)$", "", x) for x in (a, b))
                routes[code][" - ".join(sorted((a, b)))] += 1
    official = dict(default_headcode_groups())       # Network Rail's description of the group, where known
    out = []
    for code in sorted(seen):
        top = [r for r, _n in routes[code].most_common(2)]
        out.append((code, (official.get(code) or "; ".join(top)) + f" ({len(seen[code])} trains)"))
    return out


def network_stations(attune) -> List[str]:
    """Every station in the XML where a train stops for passengers, by name."""
    if attune is None:
        return []
    names = attune.locations
    tips = set()
    for versions in attune.trains.values():
        for t in versions:
            for leg in t.legs:
                if leg.origin_stop and leg.origin_pass_kind != "N":
                    tips.add(leg.origin)
                if leg.dest_stop and leg.dest_pass_kind != "N":
                    tips.add(leg.dest)
    out = set()
    for t in tips:
        name = re.sub(r"\s*\(C\)$", "", names.get(t, t))           # 'London Victoria (C)'
        if name.isupper():
            name = name.title()                                           # 'COULSDON TOWN'
        else:
            name = re.sub(r"^(.*\S)\s+[A-Z]{3,5}$", r"\1", name)        # 'Ashford International ASHF'
        out.add(name)
    return sorted(out, key=str.casefold)


def load_groups(path: Optional[str] = None) -> List[Group]:
    path = path or ensure_user_groups()
    from rstools import limits
    for enc in ("utf-8-sig", "cp1252"):
        try:
            limits.check_size(path, "SETTINGS_CSV_MAX_BYTES", "settings list")
            with open(path, newline="", encoding=enc) as fh:
                rows = list(csv.DictReader(fh))
            break
        except UnicodeDecodeError:
            continue
        except OSError:
            if path != DEFAULT_GROUPS:
                return load_groups(DEFAULT_GROUPS)
            return []
    else:
        return []
    out = []
    for r in rows:
        r = {(k or "").strip().casefold(): (v or "").strip() for k, v in r.items()}
        kind = next((k for k in KINDS if k.casefold() == r.get("type", "").casefold()), "")
        name = r.get("name", "")
        route = _split(r.get("route stations", ""))
        if not kind or not name or not route:
            continue
        try:
            minimum = max(1, int(float(r.get("minimum route stations") or 2)))
        except ValueError:
            minimum = 2
        out.append(Group(kind, name, route, _split(r.get("must also call or pass one of", "")),
                         _split(r.get("not via", "")), _split(r.get("fleets", "")), minimum,
                         [h.upper() for h in _split(r.get("headcodes (start with)", ""))]))
    return out


# --------------------------------------------------------------------------- #
# stations
# --------------------------------------------------------------------------- #
_ABBREV = {"jn": "junction", "jct": "junction", "sq": "square", "rd": "road", "st": "st", "pk": "park",
           "intl": "international"}


def _norm(s: str) -> str:
    s = s.casefold().replace("&", " and ").replace(".", " ").replace("'", "").replace("\u2019", "")
    s = s.replace("(", " ").replace(")", " ")
    return " ".join(_ABBREV.get(w, w) for w in s.split())


def _loose_names(name: str):
    """Looser forms of a station name, most specific first."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    seen = {_norm(name)}
    for cand in (base, re.sub(r"\s+(City|International|Town|Central)$", "", base, flags=re.I),
                 re.split(r"\s+(?:&|and)\s+", base)[0]):
        key = _norm(cand)
        if key and key not in seen:
            seen.add(key)
            yield key


class Stations:
    """Station names (as written in groups.csv, or a TIPLOC) to the XML's TIPLOCs. 'London Victoria'
    finds 'London Victoria' and 'London Victoria (C)'; 'Ashford International' finds 'Ashford
    International ASHF'. Signals and sidings named after a station are not the station."""

    def __init__(self, names: Dict[str, str]):
        self.by_name: Dict[str, Set[str]] = defaultdict(set)
        for tip, desc in names.items():
            for key in self._keys(desc):
                self.by_name[key].add(tip)
        self.tiplocs = {t.upper() for t in names}
        self.desc = dict(names)
        self.missing: Set[str] = set()

    @staticmethod
    def _keys(desc: str):
        d = _norm(desc)
        yield d
        base = re.sub(r"\s*\([^)]*\)$", "", desc).strip()          # 'London Victoria (C)'
        if base != desc:
            yield _norm(base)
            side = re.search(r"\((C|E)\)$", desc.strip())             # ...also 'London Victoria (Central)'
            if side:
                yield _norm(f"{base} {'Central' if side.group(1) == 'C' else 'Eastern'}")
        m = re.match(r"^(.*\S)\s+[A-Z]{3,5}$", desc.strip())        # 'Ashford International ASHF'
        if m:
            yield _norm(m.group(1))

    def find(self, spec: str) -> Set[str]:
        """A name or TIPLOC; 'A|B|C' gives other spellings of the same station (the first found is used)."""
        for alt in (a.strip() for a in spec.split("|") if a.strip()):
            if alt.upper() in self.tiplocs:
                return {alt.upper()}
            hit = self.by_name.get(_norm(alt), set())
            if hit:
                return hit
        # other spellings of the same station: 'London Victoria (Central)' for 'London Victoria (C)', 'St Albans
        # City' for 'St. Albans', 'Elstree & Borehamwood' for 'Elstree' (Network Rail's names against Attune's)
        for alt in (a.strip() for a in spec.split("|") if a.strip()):
            side = re.search(r"\((Central|C|Eastern|E)\)\s*$", alt, re.I)
            other = None if not side else ("(E)" if side.group(1)[0].upper() == "C" else "(C)")
            for loose in _loose_names(alt):
                hit = {t for t in self.by_name.get(loose, set())          # not the other side of the station
                       if not (other and self.desc.get(t, "").strip().upper().endswith(other))}
                if hit:
                    return hit
        self.missing.add(spec)
        return set()


# --------------------------------------------------------------------------- #
# trains
# --------------------------------------------------------------------------- #
@dataclass
class Call:
    tiploc: str
    time: int                   # departure (or arrival where the train ends), seconds
    stops: bool
    part: Part
    arr: Optional[int] = None   # arrival (None at the train's origin)
    last: bool = False          # the train ends here


def calls(train: TrainRun) -> List[Call]:
    """Every location the train calls at or passes, in order, with the formation part working it there."""
    out: List[Call] = []
    prev_arr: Optional[int] = None
    for part in train.parts:
        legs = part.legs
        if not legs:
            out.append(Call(part.origin, part.dep, True, part, prev_arr))
            prev_arr = part.arr
        for leg in legs:
            out.append(Call(leg.origin, leg.dep, leg.origin_stop and leg.origin_pass_kind != "N", part, prev_arr))
            prev_arr = leg.arr
    end = train.parts[-1]
    out.append(Call(end.dest, prev_arr if prev_arr is not None else end.arr, True, end, prev_arr, last=True))
    return out


@dataclass
class Capacity:
    units: int = 0
    vehicles: int = 0
    first: int = 0
    standard: int = 0
    standing: int = 0
    unknown: List[str] = field(default_factory=list)     # fleets without seat data

    @property
    def seats(self) -> int:
        return self.first + self.standard

    @property
    def total(self) -> int:
        return self.seats + self.standing

    def add(self, other: "Capacity"):
        self.units += other.units
        self.vehicles += other.vehicles
        self.first += other.first
        self.standard += other.standard
        self.standing += other.standing

    def figures(self) -> list:
        return [self.units, self.vehicles, self.first, self.standard, self.seats, self.standing, self.total]


FIGURES = ["Units", "Vehicles", "First Class seats", "Standard Class seats", "Total seats", "Standing",
           "Total capacity (seats + standing)"]
SEAT_COLS, STAND_COLS = (2, 3, 4), (5,)          # positions in Capacity.figures()


def figure_columns(seating: bool, standing: bool) -> List[int]:
    """Which of FIGURES to show: units and vehicles always; seats, standing room, and the total of both
    only when both are shown."""
    cols = [0, 1] + (list(SEAT_COLS) if seating else []) + (list(STAND_COLS) if standing else [])
    return cols + ([6] if seating and standing else [])


def hour_figure(cap: "Capacity", seating: bool, standing: bool) -> int:
    return cap.total if seating and standing else cap.standing if standing and not seating else cap.seats


def capacity_words(seating: bool, standing: bool) -> str:
    return "total capacity" if seating and standing else "standing room" if standing and not seating else "seats"


def capacity(part: Part, model: DayModel, fleet: FleetTable) -> Tuple[Capacity, str]:
    """Seats and capacity of one formation, and the formation as text (e.g. '377/4 + 377/4')."""
    cap = Capacity()
    names = []
    for key in part.formation:
        dg = model.all_diagrams.get(key)
        cls = dg.fleet if dg else "?"
        names.append(cls)
        info = fleet.get(cls) if dg else None
        cap.units += 1
        if info is None or info.standard is None:
            cap.unknown.append(cls)
            continue
        cap.vehicles += info.cars or 0
        cap.first += info.first or 0
        cap.standard += info.standard or 0
        cap.standing += info.standing or 0
    return cap, " + ".join(names)


DIRECTIONS = {"both": "arriving or departing", "arriving": "arriving", "departing": "departing"}


@dataclass
class Window:
    station: str                # as chosen
    start: int                  # seconds after midnight
    end: int
    direction: str = "both"     # both | arriving | departing

    def time_of(self, c: "Call") -> Optional[int]:
        """The time that decides whether a call is in the window (None if it does not count)."""
        if self.direction == "arriving":
            return c.arr                                   # not at the train's origin
        if self.direction == "departing":
            return None if c.last else c.time              # not where the train ends
        return c.time
    def contains(self, t: int) -> bool:
        t %= DAY_SECONDS
        if self.start <= self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end          # e.g. 22:00 - 02:00

    @property
    def text(self) -> str:
        verb = {"arriving": "arriving at ", "departing": "departing "}.get(self.direction, "at ")
        end = "24:00" if self.end == DAY_SECONDS else _hhmm(self.end)
        return f"{_hhmm(self.start)}-{end} {verb}{self.station}"


def parse_time(text: str) -> int:
    m = re.fullmatch(r"\s*(\d{1,2})[:.]?(\d{2})\s*", text or "")
    # 24:00 is the end of the day; 24:30 is not a time (it was read as 00:29 before)
    if not m or int(m.group(2)) > 59 or int(m.group(1)) * 60 + int(m.group(2)) > 24 * 60:
        raise SeatsError(f"'{text}' is not a time - use 24-hour HH:MM from 00:00 to 24:00, e.g. 07:00.")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60


def _hhmm(sec: Optional[int]) -> str:
    from rstools.clock import clock
    return clock(sec, ":")


@dataclass
class Matcher:
    group: Group
    route: List[Set[str]]
    also: Set[str]
    not_via: Set[str]
    fleets_in: Set[str]
    fleets_out: Set[str]
    origin: Set[str] = field(default_factory=set)        # station to station
    dest: Set[str] = field(default_factory=set)

    @classmethod
    def build(cls, group: Group, stations: Stations) -> "Matcher":
        route = [stations.find(s) for s in group.route]
        also = set().union(*(stations.find(s) for s in group.also)) if group.also else set()
        not_via = set().union(*(stations.find(s) for s in group.not_via)) if group.not_via else set()
        fin = {f for f in group.fleets if not f.startswith("-")}
        fout = {f[1:].strip() for f in group.fleets if f.startswith("-")}
        origin = stations.find(group.journey[0]) if group.kind == JOURNEY else set()
        dest = stations.find(group.journey[1]) if group.kind == JOURNEY else set()
        return cls(group, route, also, not_via, fin, fout, origin, dest)

    def journey_span(self, cs: List[Call]) -> Optional[Tuple[int, int]]:
        """(index of the call at the 'from' station, index of the later call at the 'to' station), both
        passenger stops, or None."""
        for i, c in enumerate(cs):
            if c.tiploc in self.origin and c.stops and not c.last:
                for j in range(i + 1, len(cs)):
                    if cs[j].tiploc in self.dest and cs[j].stops:
                        return i, j
        return None

    def heading(self, cs: List[Call]) -> str:
        """'forward' when the train reaches the corridor's stations in their listed order, else 'reverse'."""
        order: List[int] = []
        for c in cs:
            for i, tips in enumerate(self.route):
                if c.tiploc in tips and (not order or order[-1] != i):
                    order.append(i)
        return "forward" if len(order) >= 2 and order[-1] > order[0] else "reverse"

    def matches(self, cs: List[Call], fleets: Set[str], headcode: str = "") -> bool:
        heads = self.group.headcodes
        if heads:
            hc = headcode.upper()
            ins = [h for h in heads if not h.startswith("-")]
            if ins and not any(hc.startswith(h) for h in ins):
                return False
            if any(hc.startswith(h[1:].strip()) for h in heads if h.startswith("-")):
                return False
        if self.group.kind == JOURNEY:
            return self.journey_span(cs) is not None
        where = {c.tiploc for c in cs}
        if sum(1 for tips in self.route if tips & where) < min(self.group.minimum, len(self.route)):
            return False
        if self.group.kind == "Corridor" and self.group.direction != "both" and \
                self.heading(cs) != self.group.direction:
            return False
        if self.group.also and not (self.also & where):
            return False
        if self.not_via & where:
            return False
        if self.fleets_in and not (self.fleets_in & fleets):
            return False
        return not (self.fleets_out & fleets)

    def on_route(self, c: Call) -> bool:
        return any(c.tiploc in tips for tips in self.route)


@dataclass
class TrainSeats:
    day: int
    train: TrainRun
    formation: str
    cap: Capacity
    at_time: Optional[int]      # time at the chosen station (or departure from origin)
    stops: Optional[bool]


def seats_for_day(model: DayModel, fleet: FleetTable, matcher: Matcher, window: Optional[Window],
                  window_tips: Set[str]) -> List[TrainSeats]:
    out = []
    for tr in model.trains:
        if tr.stype != "In Service":
            continue
        cs = calls(tr)
        fleets = {model.all_diagrams[k].fleet for p in tr.parts for k in p.formation if k in model.all_diagrams}
        if not matcher.matches(cs, fleets, tr.headcode):
            continue
        if matcher.group.kind == JOURNEY:
            i, j = cast(Tuple[int, int], matcher.journey_span(cs))   # matches() found the journey
            dep = cs[i].time
            if window is not None and not window.contains(dep):
                continue
            # the smallest formation between the two stations limits the seats for the journey
            parts = list({id(c.part): c.part for c in cs[i:j]}.values())
            cap, form = min((capacity(p, model, fleet) for p in parts), key=lambda x: x[0].seats)
            out.append(TrainSeats(model.day, tr, form, cap, dep, True))
            continue
        if window is not None:
            at, when = None, None
            for c in cs:
                if c.tiploc in window_tips:
                    t = window.time_of(c)
                    if t is not None and window.contains(t):
                        at, when = c, t
                        break
            if at is None:
                continue
            cap, form = capacity(at.part, model, fleet)
            out.append(TrainSeats(model.day, tr, form, cap, when, at.stops))
            continue
        # the whole day: the train's largest formation while it is on the route
        parts = [c.part for c in cs if matcher.on_route(c)] or tr.parts
        unique = list({id(p): p for p in parts}.values())
        cap, form = max((capacity(p, model, fleet) for p in unique), key=lambda x: x[0].seats)
        out.append(TrainSeats(model.day, tr, form, cap, tr.dep, None))
    out.sort(key=lambda s: (s.day, (s.at_time or 0) % DAY_SECONDS if window else s.train.dep, s.train.headcode))
    return out


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #
def seats_reports(found: List[TrainSeats], days: Sequence[int], group: Group, window: Optional[Window],
                  week: bool, names: Dict[str, str], stations: Stations, warnings: List[str],
                  seating: bool = True, standing: bool = True) -> List[Report]:
    where = f"{group.label}" + (f", {window.text}" if window else ", all day")
    fig_cols = figure_columns(seating, standing)
    pick = lambda vals: [vals[i] for i in fig_cols]
    names_shown = [FIGURES[i] for i in fig_cols]
    what = capacity_words(seating, standing)
    # summary: one row per day, then the week
    per_day: Dict[int, Capacity] = {d: Capacity() for d in days}
    trains_per_day: Dict[int, int] = defaultdict(int)
    for s in found:
        per_day[s.day].add(s.cap)
        trains_per_day[s.day] += 1
    rows, kinds = [], []
    for d in days:
        rows.append([DAY_NAMES[d], trains_per_day[d]] + pick(per_day[d].figures()))
        kinds.append("body")
    if week and len(days) > 1:
        tot = Capacity()
        for d in days:
            tot.add(per_day[d])
        n = sum(trains_per_day.values())
        rows.append(["Week total", n] + pick(tot.figures()))
        rows.append(["Average per day", round(n / len(days), 1)] + [round(v / len(days), 1)
                                                                     for v in pick(tot.figures())])
        kinds += ["total", "total"]
    summary = Report("Capacity Summary", f"Capacity ({', '.join(n.lower() for n in names_shown[2:])}) - {where}",
                     ["Day", "Trains"] + names_shown, rows, kinds,
                     note="Capacity per train is for the formation " + (
                         "with the fewest seats between the two stations." if group.kind == JOURNEY else
                         f"at {window.station} in the time window." if window else
                         "with the most seats while the train is on this route.")
                     + " Passenger trains only; empty stock moves are not counted.")
    # by hour: total seats / standing / capacity in each hour (at the station, or leaving the origin)
    hours: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for s in found:
        hours[((s.at_time or 0) % DAY_SECONDS) // 3600][s.day] += hour_figure(s.cap, seating, standing)
    hrows = []
    for h in sorted(hours):
        vals = [hours[h].get(d, 0) for d in days]
        hrows.append([f"{h:02d}:00-{h:02d}:59"] + vals + ([sum(vals)] if len(days) > 1 else []))
    if hrows:
        cols = list(zip(*[r[1:] for r in hrows]))
        hrows.append(["Total"] + [sum(c) for c in cols])
    at = group.journey[0] if group.kind == JOURNEY else (window.station if window else "")
    by_hour = Report("Capacity by Hour", f"Total {what} by hour {'at ' + at if at else 'of departure'}"
                     f" - {group.label}", ["Hour"] + [DAY_NAMES[d] for d in days] + (["All days"] if len(days) > 1
                                                                                       else []),
                     hrows, ["body"] * (len(hrows) - 1) + ["total"] if hrows else [])
    # every train
    head = ["Day", "Train", "From", "Departs", "To", "Arrives"]
    if group.kind == JOURNEY:
        head += [f"Departs {group.journey[0]}"]
    elif window:
        head += [f"{'Arrives' if window.direction == 'arriving' else 'Time'} at {window.station}", "Calls or passes"]
    head += ["Formation"] + names_shown[1:]
    trows = []
    for s in found:
        t = s.train
        row = [DAY_NAMES[s.day], t.headcode, names.get(t.origin, t.origin), _hhmm(t.dep), names.get(t.dest, t.dest),
               _hhmm(t.arr)]
        if group.kind == JOURNEY:
            row += [_hhmm(s.at_time)]
        elif window:
            row += [_hhmm(s.at_time), "Calls" if s.stops else "Passes"]
        row += [s.formation] + pick(s.cap.figures())[1:]
        trows.append(row)
    by_train = Report("Capacity by Train", f"Every train - {where}", head, trows, ["body"] * len(trows))
    # notes: how the group is defined
    g = group
    if g.kind == JOURNEY:
        notes = [[f"Trains stopping for passengers at {g.journey[0]} and later at {g.journey[1]}. Seats are for the "
                  "smallest formation between the two stations" + (f"; the time window is the departure from "
                  f"{g.journey[0]}." if window else ".")]]
    elif not g.route:
        about = dict(default_headcode_groups()).get(g.name.upper())
        notes = [[f"Service group {g.name}{f' ({about})' if about else ''}: every passenger train whose headcode "
                  f"starts with {g.name}."]]
    else:
        notes = [[f"{g.kind} '{g.name}'{' (' + g.direction_text + ')' if g.direction_text else ''}: trains calling "
                  f"at or passing at least {min(g.minimum, len(g.route))} of: {'; '.join(map(shown, g.route))}."]]
        if g.kind == "Corridor" and g.direction != "both":
            notes.append([f"...travelling {g.direction_text} (the order in which the train reaches these stations)."])
    if g.also:
        notes.append([f"...and at least one of: {'; '.join(g.also)}."])
    if g.not_via:
        notes.append([f"...and not via: {'; '.join(g.not_via)}."])
    if g.fleets:
        ins = [f for f in g.fleets if not f.startswith("-")]
        outs = [f[1:] for f in g.fleets if f.startswith("-")]
        if ins:
            notes.append([f"...with one of these fleets in the formation: {', '.join(ins)}."])
        if outs:
            notes.append([f"...without these fleets: {', '.join(outs)}."])
    if g.headcodes and g.route:
        notes.append([f"...with headcodes starting: {', '.join(g.headcodes)} ('-' = not these)."])
    notes.append(["Days: " + ", ".join(DAY_NAMES[d] for d in days) + ". Seats and standing capacity come from the "
                  "fleet data (Settings > Fleet data); corridors from Settings > Corridors."])
    if stations.missing:
        notes.append(["Not found in the XML (check the spelling in the corridor list): "
                      + "; ".join(sorted(s.replace("|", " / ") for s in stations.missing)) + "."])
    unknown = sorted({u for s in found for u in s.cap.unknown})
    if unknown:
        notes.append([f"No seat data for fleet(s) {', '.join(unknown)} - their units count as 0 seats. Add them to "
                      "the fleet data."])
    notes += [[w] for w in warnings]
    return [summary, by_hour, by_train, Report("Notes", "How this report was made", ["Note"], notes,
                                               ["body"] * len(notes))]


def run_seats(models: Sequence[DayModel], fleet: FleetTable, group: Group, window: Optional[Window], week: bool,
              names: Dict[str, str], warnings: List[str],
              log: Callable[[str], None] = lambda m: None, seating: bool = True,
              standing: bool = True) -> Tuple[List[Report], List[TrainSeats], List[str]]:
    stations = Stations(names)
    matcher = Matcher.build(group, stations)
    if group.kind == JOURNEY:
        for label, tips in (group.journey[0], matcher.origin), (group.journey[1], matcher.dest):
            if not tips:
                raise SeatsError(f"'{label}' is not a station in the XML.")
        if matcher.origin == matcher.dest:
            raise SeatsError("Choose two different stations.")
    elif group.route and not any(matcher.route):
        raise SeatsError(f"None of the route stations of '{group.name}' are in the XML: "
                         f"{'; '.join(map(shown, group.route))}. Check the names in the corridor list.")
    window_tips: Set[str] = set()
    if window is not None and group.kind != JOURNEY:
        window_tips = stations.find(window.station)
        if not window_tips:
            raise SeatsError(f"'{window.station}' is not a station in the XML.")
    found: List[TrainSeats] = []
    for m in models:
        day = seats_for_day(m, fleet, matcher, window, window_tips)
        log(f"{DAY_NAMES[m.day]}: {plural(len(day), 'train')}, {sum(s.cap.seats for s in day):,} seats")
        found += day
    if stations.missing:
        warnings = warnings + [f"Station(s) not in the XML: {'; '.join(sorted(stations.missing))}"]
    days = [m.day for m in models]
    reports = seats_reports(found, days, group, window, week, names, stations, [], seating, standing)
    return reports, found, warnings
