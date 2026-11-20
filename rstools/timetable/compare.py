"""Compare a GTR timetable against the Network Rail (NR) timetable (NR is the reference).

Rules (from the agreed comparison method):
* Sections are compared like-for-like (OUT SX with OUT SX ...). Trains are matched only when
  their days overlap (e.g. GTR 'MSX' with NR 'SX', not GTR 'SX' with NR 'FO').
* Operators in scope are the GTR operators in the GTR timetable (normally SN / TL / GX); other
  operators in the NR table (e.g. London Overground) are not assessed.
* Only locations shown in the GTR table are compared; passing / pathing rows, blank layout
  placeholders and GTR-only extra timings are never reported.
* Every train is matched at most once (one-to-one), using timings, roles, headcode, calling
  pattern, end points and chronological position - never headcode alone.
* Confidence: 80%+ confident; 50-79.9% possible (review) unless the evidence is unambiguous;
  below 50% no match. NR trains without a match are 'missing from GTR' (Missing Trains only).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .parse import SECTIONS, Event, Timetable, TTrain

CONFIDENT, POSSIBLE = 80.0, 50.0
GTR_OPERATORS = frozenset({"SN", "TL", "GX"})
STATUS_CONFIDENT = "Confident match"
STATUS_UNAMBIGUOUS = "Confident match (unambiguous)"
STATUS_REVIEW = "Possible match - review"
STATUS_NONE = "Not matched"
ISSUE_TIME = "Time mismatch"
ISSUE_MISSING = "Time/location missing"
ISSUE_ARR_FOR_DEP = "Arrival time shown instead of departure"
ISSUE_DEP_FOR_ARR = "Departure time shown instead of arrival"
OTHERS_MISMATCH = "Time mismatch elsewhere on this train"
OTHERS_MATCH = "All other times present in both timetables match"

_DAYSETS = {
    "SX": {0, 1, 2, 3, 4}, "MF": {0, 1, 2, 3, 4}, "SO": {5}, "SM": {5}, "SU": {6}, "SUO": {6}, "SUN": {6},
    "MO": {0}, "TO": {1}, "WO": {2}, "THO": {3}, "FO": {4}, "MX": {1, 2, 3, 4}, "MSX": {1, 2, 3, 4},
    "FX": {0, 1, 2, 3}, "FSX": {0, 1, 2, 3}, "MFO": {0, 4}, "TTHO": {1, 3}, "TWTHO": {1, 2, 3},
}


_DAY_LETTERS = (("TH", 3), ("SU", 6), ("M", 0), ("T", 1), ("W", 2), ("F", 4), ("S", 5))


def parse_days(code: str) -> Optional[Set[int]]:
    """Days a day code runs (0 = Monday): 'SX', 'MSX', 'FO', 'TThO', 'WFO', 'MWFX'...; None if not a day code."""
    code = (code or "").upper().replace(" ", "")
    if code in _DAYSETS:
        return set(_DAYSETS[code])
    m = re.fullmatch(r"([A-Z]+?)([OX])", code)
    if not m:
        return None
    days, rest = set(), m.group(1)
    while rest:
        for letters, num in _DAY_LETTERS:
            if rest.startswith(letters):
                days.add(num)
                rest = rest[len(letters):]
                break
        else:
            return None
    return days if m.group(2) == "O" else set(range(6)) - days     # 'X': Monday-Saturday except those


def day_set(code: str, section: str) -> Set[int]:
    base = _DAYSETS.get(section.split()[1].upper(), set(range(7)))
    days = parse_days(code)
    return days if days is not None else base


def minutes(hhmm: str) -> float:
    return int(hhmm[:2]) * 60 + int(hhmm[2:4]) + (0.5 if hhmm.endswith("½") else 0)


@dataclass
class Issue:
    location: str
    role: str
    nr_time: str
    gtr_time: str
    summary: str
    others: str = ""


@dataclass
class Match:
    nr: TTrain
    gtr: Optional[TTrain]
    confidence: float
    status: str
    issues: List[Issue] = field(default_factory=list)
    nr_points: int = 0
    gtr_points: int = 0


@dataclass
class GtrGap:
    gtr: TTrain
    group: str


@dataclass
class SectionResult:
    section: str
    nr_trains: List[TTrain]
    gtr_trains: List[TTrain]
    matches: List[Match]             # one per NR train in scope (gtr None = missing)
    gaps: List[GtrGap]
    cells: int = 0                   # NR timing cells in scope
    compared: int = 0
    not_compared: int = 0
    out_of_scope: int = 0            # NR trains of other operators
    not_in_table: int = 0            # NR trains (in scope) not shown at any location of the GTR table

    @property
    def matched(self) -> List[Match]:
        return [m for m in self.matches if m.gtr is not None]

    @property
    def missing(self) -> List[Match]:
        return [m for m in self.matches if m.gtr is None]

    @property
    def headcode_mismatches(self) -> List[Match]:
        return [m for m in self.matched if m.gtr.headcode != m.nr.headcode]


@dataclass
class Comparison:
    nr: Timetable
    gtr: Timetable
    operators: Set[str]
    sections: List[SectionResult]
    warnings: List[str]
    base_label: str = "NR"           # who is the reference (NR timetable, train print, Attune list)
    other_label: str = "GTR"         # the timetable being checked


# --------------------------------------------------------------------------- #
def compare_timetables(gtr: Timetable, nr: Timetable, operators: Optional[Set[str]] = None,
                       base_label: str = "NR", other_label: str = "GTR",
                       base_name: str = "Network Rail timetable", other_name: str = "GTR timetable") -> Comparison:
    """Compare `gtr` (the timetable being checked) with `nr` (the reference: the Network Rail
    timetable, or train prints / an Attune train list turned into a timetable)."""
    from .parse import has_halves, to_public
    halves_g, halves_n = has_halves(gtr), has_halves(nr)
    note = []
    if halves_g != halves_n:            # only one side shows half minutes: compare in public (whole) minutes
        rounded = other_name if halves_g else base_name
        gtr, nr = (to_public(gtr), nr) if halves_g else (gtr, to_public(nr))
        note.append(f"The {rounded} shows half minutes and the other does not, so its times were rounded to whole "
                    "public minutes (departures down, arrivals up) to compare them.")
    elif halves_g:
        note.append("Both use half minutes, so times were compared to the half minute.")
    warnings = list(gtr.warnings) + list(nr.warnings) + note
    if operators is None:                       # GTR's own operators, as shown in its TOC row
        operators = {t.operator for trains in gtr.sections.values() for t in trains} & GTR_OPERATORS
    ops = set(operators) or set(GTR_OPERATORS)
    results, neither = [], []
    for sec in SECTIONS:
        g_trains, n_trains = gtr.sections.get(sec, []), nr.sections.get(sec, [])
        if not g_trains and not n_trains:
            neither.append(sec)
            continue
        if not n_trains:
            warnings.append(f"{sec}: not in the {base_name} - not assessed.")
            continue
        if not g_trains:
            warnings.append(f"{sec}: not in the {other_name} - every {base_label} train in it is reported missing.")
        results.append(_compare_section(sec, g_trains, n_trains, ops, gtr.locations.get(sec, [])))
    if neither:
        warnings.append(f"Not in either file, so not assessed: {', '.join(neither)}.")
    return Comparison(nr, gtr, ops, results, warnings, base_label, other_label)


def _compare_section(sec: str, g_trains: List[TTrain], n_trains: List[TTrain], ops: Set[str],
                     gtr_rows: List[Tuple[str, str]]) -> SectionResult:
    gtr_locs = {loc for loc, _role in gtr_rows}
    gtr_rowset = set(gtr_rows)
    nr_scope = [t for t in n_trains if not t.operator or t.operator in ops]
    out_of_scope = len(n_trains) - len(nr_scope)
    g_scope = [t for t in g_trains if not t.operator or t.operator in ops]
    nr_events = {id(t): _shared_events(t, gtr_locs, gtr_rowset) for t in nr_scope}
    shown = [t for t in nr_scope if nr_events[id(t)]]          # trains not shown at any GTR location are
    not_in_table = len(nr_scope) - len(shown)                  # counted, not compared
    nr_scope = shown
    g_index = {id(g): _index(g) for g in g_scope}
    g_days = {id(g): day_set(g.days, sec) for g in g_scope}
    # only trains sharing a time at a location, or the headcode, can score anything (see _score), so
    # each NR train is scored against those alone rather than against every GTR train
    by_time: Dict[Tuple[str, str], List[TTrain]] = defaultdict(list)
    by_hc: Dict[str, List[TTrain]] = defaultdict(list)
    for g in g_scope:
        for key in {(e.loc, e.time) for e in g.events}:
            by_time[key].append(g)
        if g.headcode:
            by_hc[g.headcode].append(g)
    pairs = []
    for n in nr_scope:
        nd = day_set(n.days, sec)
        events = nr_events[id(n)]
        cands = {id(g): g for e in events for g in by_time.get((e.loc, e.time), ())}
        cands.update((id(g), g) for g in by_hc.get(n.headcode, ()) if n.headcode)
        for g in cands.values():
            overlap = len(nd & g_days[id(g)])
            if not overlap:
                continue
            score = _score(n, events, g, g_index[id(g)], gtr_locs)
            if score is not None and score[0] >= POSSIBLE:
                pairs.append((score + (-overlap,), n, g))           # prefer the closest day variant
    # one-to-one assignment: best confidence first, then closest in time, then table order
    pairs.sort(key=lambda p: (-p[0][0], p[0][1], p[0][4], p[1].column, p[2].column))
    used_n, used_g = set(), set()
    chosen: Dict[int, Tuple[tuple, TTrain]] = {}
    per_nr = defaultdict(int)
    for score, n, g in pairs:
        per_nr[id(n)] += 1
    for score, n, g in pairs:
        if id(n) in used_n or id(g) in used_g:
            continue
        used_n.add(id(n))
        used_g.add(id(g))
        chosen[id(n)] = (score, g)
    matches = []
    cells = compared = 0
    for n in sorted(nr_scope, key=lambda t: (t.column, t.headcode)):
        events = nr_events[id(n)]
        cells += len(events)
        if id(n) not in chosen:
            matches.append(Match(n, None, 0.0, STATUS_NONE, nr_points=len(events)))
            continue
        (conf, *_rest), g = chosen[id(n)]
        compared += len(events)
        unambiguous = (conf >= POSSIBLE and n.headcode and n.headcode == g.headcode and per_nr[id(n)] == 1)
        status = STATUS_CONFIDENT if conf >= CONFIDENT else (STATUS_UNAMBIGUOUS if unambiguous else STATUS_REVIEW)
        issues = _issues(events, g_index[id(g)])
        matches.append(Match(n, g, round(conf, 1), status, issues, len(events),
                             len([e for e in g.events if e.loc in {x.loc for x in n.events} or e.loc in gtr_locs])))
    gaps = _isolated_gaps(sec, g_scope, used_g, matches)
    return SectionResult(sec, nr_scope, g_scope, matches, gaps, cells, compared, cells - compared, out_of_scope,
                         not_in_table)


def _shared_events(t: TTrain, locs: Set[str], rows: Set[Tuple[str, str]]) -> List[Event]:
    """The train's times that the other table can show: at its locations, and in a row of the same kind
    (arrival / departure). Where the other table has no row of that kind at a station, the time is left
    out when the train's other time there is compared instead (a layout difference, not a train
    difference); a train with only that one time there keeps it, so a time shown in the wrong row is
    still found."""
    out = []
    for e in t.events:
        if e.loc not in locs:
            continue
        if (e.loc, e.role) not in rows and any(x.loc == e.loc and x.role != e.role and (x.loc, x.role) in rows
                                               for x in t.events):
            continue
        out.append(e)
    return out


def _index(g: TTrain) -> Dict[Tuple[str, str], Event]:
    out = {}
    for e in g.events:
        out.setdefault((e.loc, e.role), e)
    return out


def _score(n: TTrain, events: List[Event], g: TTrain, gidx, gtr_locs) -> Optional[tuple]:
    """(confidence %, minutes apart, -headcode match, -pattern) for a candidate pair, or None."""
    exact = role_swap = 0
    for e in events:
        same = gidx.get((e.loc, e.role))
        if same is not None and same.time == e.time:
            exact += 1
            continue
        other = gidx.get((e.loc, "dep" if e.role == "arr" else "arr"))
        if other is not None and other.time == e.time:
            role_swap += 1
    time_score = (exact + 0.8 * role_swap) / len(events)
    hc = 1.0 if n.headcode and n.headcode == g.headcode else 0.0
    if time_score == 0 and not hc:
        return None
    n_locs = {e.loc for e in events}
    g_locs = {e.loc for e in g.events if e.loc in gtr_locs}
    pattern = len(n_locs & g_locs) / len(n_locs | g_locs) if (n_locs | g_locs) else 0.0
    ends = 0.5 * (events[0].loc in g_locs) + 0.5 * (events[-1].loc in g_locs)
    conf = 100 * (0.5 * time_score + 0.2 * hc + 0.2 * pattern + 0.1 * ends)
    apart = abs(minutes(events[0].time) - minutes(g.events[0].time))
    apart = min(apart, 1440 - apart)
    return (conf, apart, -hc, -pattern)


def _issues(events: List[Event], gidx) -> List[Issue]:
    issues = []
    for e in events:
        same = gidx.get((e.loc, e.role))
        if same is not None:
            if same.time != e.time:
                issues.append(Issue(e.name, e.role, e.time, same.time, ISSUE_TIME))
            continue
        other_role = "dep" if e.role == "arr" else "arr"
        other = gidx.get((e.loc, other_role))
        own = next((x for x in events if x.loc == e.loc and x.role == other_role), None)
        if other is not None and (own is None or own.time != other.time):
            # GTR shows a time only in the other row here, and it is not that row's own (correct) time
            issues.append(Issue(e.name, e.role, e.time, other.time,
                                ISSUE_ARR_FOR_DEP if e.role == "dep" else ISSUE_DEP_FOR_ARR))
            continue
        issues.append(Issue(e.name, e.role, e.time, "", ISSUE_MISSING))
    n_time = sum(i.summary == ISSUE_TIME for i in issues)
    for i in issues:                       # is there a time mismatch elsewhere on this train?
        elsewhere = n_time - (1 if i.summary == ISSUE_TIME else 0)
        i.others = OTHERS_MISMATCH if elsewhere else OTHERS_MATCH
    return issues


def _isolated_gaps(sec: str, g_scope: List[TTrain], used_g: set, matches: List[Match]) -> List[GtrGap]:
    """A GTR-only train counts as an 'isolated gap in NR' only where it sits exactly in a hole of an
    otherwise matched, regular all-day pattern (same headcode group and calling pattern, at the
    group's usual interval) - a single NR train apparently absent from a clockface service."""
    matched = [m.gtr for m in matches if m.gtr is not None]
    by_key = defaultdict(list)
    for g in matched:
        by_key[_pattern_key(g)].append(minutes(g.events[0].time))
    gaps = []
    for g in g_scope:
        if id(g) in used_g or not g.headcode or day_set(g.days, sec) != day_set("", sec):
            continue
        times = sorted(by_key.get(_pattern_key(g), []))
        if len(times) < 6:
            continue
        steps = Counter(b - a for a, b in zip(times, times[1:]) if b > a)
        headway, seen = steps.most_common(1)[0]
        if headway < 10 or seen < 4:
            continue
        t = minutes(g.events[0].time)
        before = max((x for x in times if x < t), default=None)
        after = min((x for x in times if x > t), default=None)
        if before is None or after is None:
            continue
        if abs((after - before) - 2 * headway) <= 2 and abs((t - before) - headway) <= 3:
            gaps.append(GtrGap(g, g.headcode[:2] + "xx"))
    return gaps


def _pattern_key(t: TTrain) -> tuple:
    return (t.headcode[:2], tuple(e.loc for e in t.events if e.role == "dep") or tuple(e.loc for e in t.events))


# --------------------------------------------------------------------------- #
def service_groups(res: SectionResult) -> List[Tuple[str, int, int, int]]:
    """(group, NR count, GTR count, difference) for headcode groups with NR trains missing from GTR.
    A group ('1Kxx') is used only for 5+ missing trains of a group; otherwise each headcode is listed."""
    missing = Counter(m.nr.headcode[:2] for m in res.missing if m.nr.headcode)
    total = Counter(t.headcode[:2] for t in res.nr_trains if t.headcode)
    rows = []
    for grp, n_missing in sorted(missing.items()):
        if n_missing >= 5:
            rows.append((f"{grp}xx", total[grp], total[grp] - n_missing, n_missing))
            continue
        heads = Counter(m.nr.headcode for m in res.missing if m.nr.headcode[:2] == grp)
        for hc in sorted(heads):
            nr_n = sum(1 for t in res.nr_trains if t.headcode == hc)
            rows.append((hc, nr_n, nr_n - heads[hc], heads[hc]))
    return rows
