"""Following units through the week: washes and CETs, depot returns / swaps, captive units.

Each day's diagrams (from the TRENT print: start / end location and its WASH, CET and FUEL
lines) are linked into physical units with the next-day workings in the Attune XML - the note at
the end of each unit diagram, e.g. 'BI20 04+29ThO (F)'. For a day the XML does not cover (or a
diagram that ends 'Stabld'), a unit is matched to a diagram starting where it stabled, on the
same fleet; those links are marked 'inferred' so they can be checked.
"""
from __future__ import annotations

import csv
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Collection, Dict, List, Optional, Sequence, Set, Tuple, cast

from .attune import AttuneData
from .days import DAYS, DAY_NAMES, days_of_code
from .fleet import user_fleet_path
from .model import _pick_diagrams
from .trent import TrentData

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DEPOTS = os.path.join(HERE, "depots_default.csv")
_DEPOT_NAME = re.compile(
    r"^(?P<grp>.+?)\s*(?:T\s*&\s*R\.?\s*S\.?\s*M\.?\s*D\.?|T\.?R\.?S\.?M\.?D\.?|T\.?M\.?D\.?|E\.?M\.?U\.?D\.?|"
    r"Traincare|Depot|(?:Outside\s+|Inside\s+)?Shed)(?:\b|$)", re.IGNORECASE)
_NEXT = re.compile(r"^\s*([A-Z]{1,4})\s*(\d+[A-Z]?)\s+(\d{1,2})[:+.](\d{2})\s*([A-Za-z]*)")


# --------------------------------------------------------------------------- #
# depot locations
# --------------------------------------------------------------------------- #
def user_depots_path() -> str:
    return os.path.join(os.path.dirname(user_fleet_path()), "depots.csv")


def ensure_user_depots() -> str:
    """The editable depot list (created from the built-in one on first use)."""
    path = user_depots_path()
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(DEFAULT_DEPOTS, encoding="utf-8") as src, open(path, "w", encoding="utf-8-sig",
                                                                     newline="") as dst:
                dst.write(src.read())
        except OSError:
            return DEFAULT_DEPOTS
    return path


class Depots:
    """Which locations are depots, grouped so every road of one depot counts as that depot.
    The editable list wins (a blank Depot marks a location as not a depot); otherwise a location
    is a depot when its name says so (T&RSMD, TMD, EMUD, Depot, Shed, Traincare)."""

    def __init__(self, table: Dict[str, str], names: Dict[str, str]):
        self.table, self.names = table, names
        self._cache: Dict[str, str] = {}

    @classmethod
    def load(cls, names: Dict[str, str], path: Optional[str] = None) -> "Depots":
        table: Dict[str, str] = {}
        for p in (DEFAULT_DEPOTS, path or ensure_user_depots()):
            for enc in ("utf-8-sig", "cp1252"):
                try:
                    with open(p, newline="", encoding=enc) as fh:
                        for rec in csv.DictReader(fh):
                            tip = (rec.get("TIPLOC") or "").strip().upper()
                            if tip:
                                table[tip] = (rec.get("Depot") or "").strip()
                    break
                except UnicodeDecodeError:
                    continue
                except OSError:                 # missing / locked list: the name rules still apply
                    break
        return cls(table, names)

    def depot_of(self, tiploc: str) -> str:
        """The depot a location belongs to ('' if it is not a depot). `tiploc` may also be a location name
        (the TLGN unit diagram print names most locations)."""
        hit = self._cache.get(tiploc)
        if hit is None:
            if tiploc.upper() in self.table:
                hit = self.table[tiploc.upper()]
            else:
                m = _DEPOT_NAME.match(self.names.get(tiploc, tiploc))
                hit = " ".join(m.group("grp").split()).strip(" -") if m else ""
            self._cache[tiploc] = hit
        return hit


# --------------------------------------------------------------------------- #
# diagrams per day and the links between days
# --------------------------------------------------------------------------- #
@dataclass
class DayDiagram:
    day: int
    key: str
    fleet: str
    start_loc: str
    start_min: int
    end_loc: str
    end_min: int
    washes: int
    cets: int
    fuels: int
    fuel_times: List[int] = field(default_factory=list)   # minutes after the day's midnight of each FUEL
    next_key: str = ""          # TLGN print: 'Forms (Next Day)' diagram
    prev_key: str = ""          # ...and 'Off (Previous Day)'

    @property
    def label(self) -> str:
        return f"{DAYS[self.day]} {self.key}"


@dataclass
class UnitWeek:
    """One unit followed through the days considered."""
    diagrams: List[DayDiagram]
    links: List[str] = field(default_factory=list)      # how each step was linked: 'XML' / 'TRENT' / 'inferred'

    @property
    def washes(self) -> int:
        return sum(d.washes for d in self.diagrams)

    @property
    def cets(self) -> int:
        return sum(d.cets for d in self.diagrams)


def day_diagrams(trent: TrentData, day: int) -> List[DayDiagram]:
    out = []
    picked, _notes = _pick_diagrams(trent, day)
    for td in picked:
        rows = td.rows
        if not rows:
            continue
        timed = [r for r in rows if (r.dep if r.dep is not None else r.arr) is not None]
        first = next((r for r in rows if r.dep is not None), rows[0])
        last_time = max((cast(int, r.arr if r.arr is not None else r.dep) for r in timed), default=0)
        acts = Counter(r.activity for r in rows if r.activity)
        fuel_times, when = [], first.dep or 0
        for r in rows:                      # a FUEL line has no time of its own: the unit's last arrival
            t = r.arr if r.arr is not None else r.dep
            if t is not None:
                when = t
            if r.activity == "FUEL":
                fuel_times.append(when)
        out.append(DayDiagram(day, td.key, td.fleet, first.loc, first.dep or 0, rows[-1].loc, last_time,
                              acts.get("WASH", 0), acts.get("CET", 0), acts.get("FUEL", 0), fuel_times,
                              f"{td.depot}{td.next_num}" if td.next_num else "",
                              f"{td.depot}{td.prev_num}" if td.prev_num else ""))
    return sorted(out, key=lambda d: (d.fleet, d.key))


def _next_day(day: int, code: str) -> List[int]:
    """Days after `day` (in week order, wrapping) that a next-working day code allows."""
    allowed = days_of_code(code) if code else {(day + 1) % 7}
    return [(day + k) % 7 for k in range(1, 8) if (day + k) % 7 in allowed]


def xml_links(attune: Optional[AttuneData]) -> Tuple[Dict[Tuple[int, str], Tuple[int, str]], set, set]:
    """({(day, diagram): (next day, next diagram)}, {(day, diagram) that end 'Stabld'}, days covered)."""
    links: Dict[Tuple[int, str], Tuple[int, str]] = {}
    stabled: Set[Tuple[int, str]] = set()
    covered: Set[int] = set()
    if attune is None:
        return links, stabled, covered
    from .model import PLAN_PRIORITY
    # where an LTP and an STP version of a diagram both run on a day, the STP one (read last) is used
    for ud in sorted(attune.unit_diagrams, key=lambda u: PLAN_PRIORITY.get(u.plan.upper(), 0)):
        covered |= ud.days
        for day in ud.days:
            for note in ud.notes:
                m = _NEXT.match(note)
                if m:
                    days = _next_day(day, m.group(5))
                    if days:
                        links[(day, ud.key)] = (days[0], f"{m.group(1)}{m.group(2)}")
                    break
                if note.lower().startswith("stab"):
                    stabled.add((day, ud.key))
                    break
    return links, stabled, covered


def _closeness(a: str, b: str, depots: Optional["Depots"]) -> Optional[int]:
    """How well a stabling location matches a start location: 0 same place, 1 same depot,
    2 same station area (e.g. BOGNSID / BOGNORR); None if unrelated."""
    if a == b:
        return 0
    if depots is not None:
        da = depots.depot_of(a)
        if da and da == depots.depot_of(b):
            return 1
    return 2 if len(a) >= 4 and a[:4] == b[:4] else None


def follow_units(trent: TrentData, attune: Optional[AttuneData], days: Sequence[int],
                 depots: Optional["Depots"] = None):
    """Link the chosen days' diagrams into units. Returns ([UnitWeek], {day: [DayDiagram]}, warnings)."""
    days = sorted(days)
    order = {d: i for i, d in enumerate(days)}
    per_day = {d: day_diagrams(trent, d) for d in days}
    node = {(d, x.key): x for d in days for x in per_day[d]}
    links, stabled, covered = xml_links(attune)
    succ: Dict[Tuple[int, str], Tuple[Tuple[int, str], str]] = {}
    pred = set()
    warnings: List[str] = []
    missing = []
    for (d, key), target in links.items():
        if (d, key) in node and d in order:
            if target in node and order.get(target[0], -1) > order[d]:
                succ[(d, key)] = (target, "XML")
                pred.add(target)
            elif target[0] in order and target not in node:
                missing.append(f"{DAYS[d]} {key} -> {DAYS[target[0]]} {target[1]}")
    # the TLGN print names the diagram the units form the next day ('Forms (Next Day) 316')
    trent_links = 0
    for d in days:
        d2 = (d + 1) % 7
        if d2 not in order or order[d2] <= order[d]:
            continue
        pairs = [(x.key, x.next_key) for x in per_day[d] if x.next_key]
        pairs += [(y.prev_key, y.key) for y in per_day[d2] if y.prev_key]
        for a, b in pairs:
            source, target = (d, a), (d2, b)
            if source in node and target in node and source not in succ and target not in pred:
                succ[source] = (target, "TRENT")
                pred.add(target)
                covered.add(d)
                trent_links += 1
    if missing:
        warnings.append(f"{len(missing)} next-day working(s) in the XML point to a diagram that is not in the TRENT "
                        f"print (e.g. {', '.join(missing[:6])}) - those units are not followed further.")
    # days (or diagrams) without an XML link: match where the unit stabled to where a diagram starts
    inferred = 0
    for i, d in enumerate(days[:-1]):
        later = days[i + 1:]
        open_ends = [x for x in per_day[d] if (d, x.key) not in succ
                     and (d not in covered or (d, x.key) in stabled or (d, x.key) not in links)]
        for tier in (0, 1, 2):                      # exact place first, then same depot, then same area
            for x in sorted(open_ends, key=lambda x: x.end_min):
                if (d, x.key) in succ:
                    continue
                for d2 in later if (d, x.key) in stabled else later[:1]:
                    cands = [y for y in per_day[d2] if (d2, y.key) not in pred and y.fleet == x.fleet
                             and _closeness(x.end_loc, y.start_loc, depots) == tier]
                    if cands:
                        y = min(cands, key=lambda y: y.start_min)
                        succ[(d, x.key)] = ((d2, y.key), "inferred")
                        pred.add((d2, y.key))
                        inferred += 1
                        break
    lacking = [DAY_NAMES[d] for d in days[:-1] if d not in covered]
    if lacking and not trent_links and not (attune is not None and attune.path):
        warnings.append(f"{inferred} link(s) were inferred: without an XML, units are followed by matching where "
                        "they stabled to where a diagram starts (marked 'inferred'). Add the Attune XML for exact "
                        "next-day workings.")
    elif lacking and not trent_links:
        warnings.append("The XML has no unit diagrams for " + ", ".join(lacking) + ", so units on those days were "
                        "followed by matching where they stabled to where a diagram starts (marked 'inferred'). "
                        "Use an Attune export covering every day for exact next-day workings.")
    elif inferred:
        warnings.append(f"{inferred} link(s) were inferred from stabling locations (diagrams ending 'Stabld' or "
                        "without a next-day working in the XML or TRENT print).")
    units = []
    for d in days:
        for x in per_day[d]:
            if (d, x.key) in pred and d != days[0]:
                continue                            # picked up by a unit from an earlier day
            chain, how, at = [x], [], (d, x.key)
            while at in succ and len(chain) < len(days):
                at, kind = succ[at]
                chain.append(node[at])
                how.append(kind)
            units.append(UnitWeek(chain, how))
    return units, per_day, warnings


# --------------------------------------------------------------------------- #
# reports
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    name: str                   # tab name (31 characters at most)
    title: str
    headers: List[str]
    rows: List[list]
    kinds: List[str] = field(default_factory=list)     # 'body' / 'total' per row
    note: str = ""              # one line under the title explaining the figures


def _hm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _chain(u: UnitWeek) -> str:
    out = u.diagrams[0].label
    for d, how in zip(u.diagrams[1:], u.links):
        out += (" >? " if how == "inferred" else " > ") + d.label
    return out


def _gap(u: UnitWeek) -> int:
    """Most diagrams in a row without a wash."""
    best = run = 0
    for d in u.diagrams:
        run = 0 if d.washes else run + 1
        best = max(best, run)
    return best


def wash_cet_reports(units: List[UnitWeek], per_day: Dict[int, List[DayDiagram]], week: bool) -> List[Report]:
    if not week:
        rows, kinds = [], []
        for d, diags in per_day.items():
            for x in diags:
                rows.append([DAYS[d], x.key, x.fleet, x.washes, x.cets, x.fuels, x.end_loc])
                kinds.append("body")
        by_fleet = _fleet_totals([(x.fleet, x.washes, x.cets, x.fuels) for diags in per_day.values() for x in diags],
                                 "Diagrams")
        return [Report("Washes and CETs by Diagram", "Washes and CETs by diagram",
                       ["Day", "Diagram", "Fleet", "Washes", "CETs", "Fuel", "Ends at"], rows, kinds,
                       "WASH, CET and FUEL lines on each diagram in the TRENT print."), by_fleet]
    rows = []
    for u in sorted(units, key=lambda u: (u.diagrams[0].fleet, u.diagrams[0].day, u.diagrams[0].key)):
        first = u.diagrams[0]
        rows.append([first.label, first.fleet, len(u.diagrams), u.washes, u.cets,
                     sum(x.fuels for x in u.diagrams), _gap(u), _chain(u),
                     (" + ".join(sorted(set(u.links))) if "inferred" not in u.links
                      else f"{u.links.count('inferred')} inferred")])
    by_fleet = _fleet_totals([(u.diagrams[0].fleet, u.washes, u.cets, sum(x.fuels for x in u.diagrams))
                              for u in units], "Units")
    return [Report("Washes and CETs by Unit", "Washes and CETs per unit",
                   ["Unit (first diagram)", "Fleet", "Days", "Washes", "CETs", "Fuel",
                    "Most diagrams without a wash", "Diagrams worked", "Linked by"],
                   rows, ["body"] * len(rows),
                   "Each unit followed through the week with the next-day workings ('>' from the XML or TRENT "
                   "print, '>?' inferred from where it stabled)."), by_fleet]


def _fleet_totals(items, what: str) -> Report:
    agg: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    for fleet, w, c, f in items:
        a = agg[fleet]
        a[0] += 1
        a[1] += w
        a[2] += c
        a[3] += f
        a[4] += 0 if w else 1
        a[5] += 0 if c else 1
    rows: List[list] = [[fl, a[0], a[1], a[2], a[3], round(a[1] / a[0], 2) if a[0] else 0, a[4], a[5]]
                        for fl, a in sorted(agg.items())]
    tot = [sum(r[i] for r in rows) for i in range(1, 5)]
    rows.append(["Total", *tot, round(tot[1] / tot[0], 2) if tot[0] else 0, sum(r[6] for r in rows),
                 sum(r[7] for r in rows)])
    return Report("Washes and CETs by Fleet", "Washes and CETs by fleet",
                  ["Fleet", what, "Washes", "CETs", "Fuel", f"Washes per {what[:-1].lower()}",
                   f"{what} with no wash", f"{what} with no CET"], rows, ["body"] * (len(rows) - 1) + ["total"])


MOVE_TYPES = ("Return", "Swap", "Leaves depot", "Back to depot", "Away from depot")


def _move_type(a: str, b: str) -> str:
    if a and b:
        return "Return" if a == b else "Swap"
    return "Leaves depot" if a else ("Back to depot" if b else "Away from depot")


def depot_reports(per_day: Dict[int, List[DayDiagram]], depots: Depots, names: Dict[str, str]) -> List[Report]:
    rows: List[list] = []
    counts: Dict[int, Counter] = defaultdict(Counter)
    pairs: Counter = Counter()
    for d, diags in per_day.items():
        for x in diags:
            a, b = depots.depot_of(x.start_loc), depots.depot_of(x.end_loc)
            kind = _move_type(a, b)
            counts[d][kind] += 1
            if kind in ("Return", "Swap"):
                pairs[(a, b)] += 1
            rows.append([DAYS[d], x.key, x.fleet, kind, names.get(x.start_loc, x.start_loc), _hm(x.start_min),
                         a or "-", names.get(x.end_loc, x.end_loc), _hm(x.end_min), b or "-"])
    order = {k: i for i, k in enumerate(MOVE_TYPES)}
    # returns and swaps first, then depot departures / arrivals, diagrams away from any depot last
    rows.sort(key=lambda r: (r[3] == "Away from depot", DAYS.index(r[0]), order[r[3]], r[2], r[1]))
    summary: List[list] = [[DAY_NAMES[d], *[counts[d][k] for k in MOVE_TYPES], sum(counts[d].values())]
                           for d in per_day]
    summary.append(["Total", *[sum(r[i + 1] for r in summary) for i in range(len(MOVE_TYPES) + 1)]])
    pair_rows = [[a, b, "Return" if a == b else "Swap", n] for (a, b), n in sorted(pairs.items())]
    return [
        Report("Depot Moves by Diagram", "Depot returns and swaps by diagram",
               ["Day", "Diagram", "Fleet", "Type", "Starts at", "Departs", "Start depot", "Ends at", "Arrives",
                "End depot"], rows, ["body"] * len(rows),
               "Return: starts and ends at the same depot. Swap: starts at one depot and ends at another."),
        Report("Depot Moves by Day", "Depot returns and swaps - summary", ["Day", *MOVE_TYPES, "Diagrams"],
               summary, ["body"] * (len(summary) - 1) + ["total"]),
        Report("Depot Moves by Depot", "Returns and swaps by depot", ["From depot", "To depot", "Type", "Diagrams"],
               pair_rows, ["body"] * len(pair_rows)),
    ]


def captive_reports(units: List[UnitWeek], per_day: Dict[int, List[DayDiagram]], depots: Depots,
                    names: Dict[str, str], week: bool, days: Sequence[int]) -> List[Report]:
    def at_depot(x: DayDiagram) -> bool:
        return bool(depots.depot_of(x.start_loc) or depots.depot_of(x.end_loc))
    rows: List[list]
    if not week:
        rows = [[DAYS[d], x.key, x.fleet, names.get(x.start_loc, x.start_loc), names.get(x.end_loc, x.end_loc)]
                for d, diags in per_day.items() for x in diags if not at_depot(x)]
        return [Report("Captive Diagrams", "Diagrams that neither start nor end at a depot",
                       ["Day", "Diagram", "Fleet", "Starts at", "Ends at"], rows, ["body"] * len(rows),
                       "A unit on these diagrams does not visit a depot that day; run for the whole week to see "
                       "which units are captive for the entire week.")]
    rows = []
    for u in units:
        if any(at_depot(x) for x in u.diagrams):
            continue
        full = len(u.diagrams) == len(days)
        if not full and len(u.diagrams) < 2:
            continue                                # a single day says nothing about a whole week
        rows.append([u.diagrams[0].label, u.diagrams[0].fleet, len(u.diagrams), "Yes" if full else "Part week",
                     _chain(u), " / ".join(names.get(x.end_loc, x.end_loc) for x in u.diagrams)])
    rows.sort(key=lambda r: (r[3] != "Yes", r[1], r[0]))
    return [Report("Captive Units", "Captive units - never start or end at a depot all week",
                   ["Unit (first diagram)", "Fleet", "Days", "Whole week", "Diagrams worked", "Stables at"],
                   rows, ["body"] * len(rows),
                   "Units followed with the next-day workings that do not start or end any diagram at a depot. "
                   "'Part week': the unit could only be followed for part of the week.")]


FUEL_LIMIT = 48 * 60          # minutes: a diesel unit must be fuelled at least this often
WEEK = 7 * 1440


def _when(minute: int) -> str:
    """'WO 14:20' for a minute of the week."""
    minute %= WEEK
    return f"{DAYS[minute // 1440]} {minute % 1440 // 60:02d}:{minute % 60:02d}"


def fuel_reports(units: List[UnitWeek], diesel: Collection[str], days: Sequence[int]) -> List[Report]:
    """Each diesel unit (e.g. the 171s) followed through the week: is it fuelled at least every 48 hours?
    A unit followed for the whole week is taken to repeat weekly, so the gap from its last fuel to its
    first fuel the next week counts too. For a unit followed for part of the week, the time before its
    first fuel and after its last fuel is measured from the start of its first diagram / to the end of
    its last, and marked 'part week'."""
    full_week = len(days) == 7
    rows, kinds = [], []
    for u in sorted(units, key=lambda u: (u.diagrams[0].fleet, u.diagrams[0].day, u.diagrams[0].key)):
        first = u.diagrams[0]
        if first.fleet not in diesel:
            continue
        fuels = sorted(x.day * 1440 + t for x in u.diagrams for t in x.fuel_times)
        start = first.day * 1440 + first.start_min
        end = u.diagrams[-1].day * 1440 + u.diagrams[-1].end_min
        whole = full_week and len(u.diagrams) == 7
        gaps = []
        if fuels:
            gaps += [(b - a, a, b) for a, b in zip(fuels, fuels[1:])]
            if whole:
                gaps.append((fuels[0] + WEEK - fuels[-1], fuels[-1], fuels[0] + WEEK))
            else:
                gaps.append((fuels[0] - start, start, fuels[0]))
                gaps.append((end - fuels[-1], fuels[-1], end))
        else:
            gaps.append((WEEK if whole else end - start, start, end))
        worst = max(gaps)
        over = [g for g in gaps if g[0] > FUEL_LIMIT]
        result = ("No fuel all week" if not fuels and whole else "No fuel" if not fuels else
                  f"Over 48 hours ({len(over)} gap(s))" if over else "OK")
        rows.append([first.label, first.fleet, len(u.diagrams), "Whole week" if whole else "Part week", len(fuels),
                     f"{worst[0] // 60}:{worst[0] % 60:02d}", _when(worst[1]), _when(worst[2]), result, _chain(u)])
        kinds.append("body")
    rows.sort(key=lambda r: (r[8] == "OK", r[1], r[0]))      # problems first
    bad = sum(1 for r in rows if r[8] != "OK")
    return [Report("Fuel Check (171s)", f"Diesel units fuelled at least every 48 hours - {bad} of {len(rows)} "
                   "unit(s) need checking" if rows else "Diesel units fuelled at least every 48 hours",
                   ["Unit (first diagram)", "Fleet", "Days", "Followed for", "Fuels", "Longest gap (h:mm)",
                    "Gap from", "Gap to", "Result", "Diagrams worked"], rows, kinds,
                   "Fuel times are the arrival before each FUEL line in the TRENT print. Whole week: the unit is "
                   "taken to repeat weekly, so the gap from its last fuel to its first fuel the next week is "
                   "included. Part week: gaps before the first fuel and after the last are measured from the "
                   "start of its first diagram / to the end of its last, so check those units across the "
                   "week boundary.")]
