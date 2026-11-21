"""Train prints or an Attune train list as the base (reference) for a timetable comparison.

The base trains are turned into the same timetable form as a Network Rail table, then compared
with the chosen timetable by exactly the same rules as timetable against timetable:

* a print gives each call's *public* arrival / departure (what a timetable shows); passing points,
  working-only stops (signals, sidings) and empty-stock trains have no public times and are not
  compared;
* a train list gives the origin departure and destination arrival; working half minutes become
  public times the usual way (a departure rounds down, an arrival rounds up);
* every train goes into the section(s) its days run in (SX / SO / SuO), in the direction (OUT / RTN)
  whose table lists its stations in the order it calls at them.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from .compare import day_set
from .parse import Event, Timetable, TTrain, norm_headcode, norm_loc

DAY_TYPES = (("SX", {0, 1, 2, 3, 4}), ("SO", {5}), ("SuO", {6}))
TIPLOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiplocs.csv")


def trains_from_prints(atrains, working: bool = False) -> Tuple[List[TTrain], List[str]]:
    """TTrains from Attune Single Train Report trains: public calls only, or with working=True (the
    timetable being checked shows half minutes) the working times, half minutes and passes included."""
    out: list = []
    notes: List[str] = []
    no_public: list = []
    cols = (("arr", "wtt_arr"), ("dep", "wtt_dep"), ("dep", "pass")) if working else (("arr", "pub_arr"),
                                                                                      ("dep", "pub_dep"))
    for t in atrains:
        events = []
        for r in t.rows:
            for role, col in cols:
                hhmm = r.hhmm(col, half=working)
                if hhmm:
                    events.append(Event(norm_loc(r.name), r.name, role, hhmm, r.values[col]))
        if not events:
            no_public.append(t.train_id)
            continue
        tt = TTrain("", t.headcode, t.train_id, t.operator, t.days, "", len(out), events,
                    t.rows[0].name if t.rows else "", t.rows[-1].name if t.rows else "")
        out.append(tt)
    if no_public:
        notes.append(f"{len(no_public)} train(s) in the print have no public times (empty stock or "
                     f"non-passenger) and are not compared: {', '.join(no_public[:12])}"
                     + (" ..." if len(no_public) > 12 else ""))
    return out, notes


def _user_tiplocs() -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), "tiplocs.csv")


def load_tiplocs() -> Dict[str, str]:
    """Location code -> station name: the built-in list, plus every code learnt from train prints read
    on this PC (kept in the settings folder)."""
    table = {}
    for path in (TIPLOCS, _user_tiplocs()):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh.read().splitlines()[1:]:
                    code, _sep, name = line.partition(",")
                    if code.strip() and name.strip():
                        table[code.strip().upper()] = name.strip()
        except OSError:
            pass
    return table


def learn_tiplocs(atrains):
    """Remember the location codes and names seen in an Attune print, for train lists that use codes."""
    known = load_tiplocs()
    new = {r.tiploc: r.name for t in atrains for r in t.rows if r.tiploc not in known and "," not in r.name}
    if not new:
        return
    path = _user_tiplocs()
    try:
        fresh = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as fh:
            if fresh:
                fh.write("TIPLOC,Name\n")
            fh.writelines(f"{k},{v}\n" for k, v in sorted(new.items()))
    except OSError:
        pass


def _public(text: str, role: str, keep_half: bool = False) -> str:
    """'0537' / '0537½' working time -> public HHMM (departures round down, arrivals round up), or with
    keep_half the working time as it is."""
    m = re.fullmatch(r"(\d{2})(\d{2})(½?)", text or "")
    if not m:
        return ""
    if keep_half:
        return text
    mins = int(m.group(1)) * 60 + int(m.group(2)) + (1 if m.group(3) and role == "arr" else 0)
    return f"{mins // 60 % 24:02d}{mins % 60:02d}"


def trains_from_list(lst, working: bool = False) -> Tuple[List[TTrain], List[str]]:
    """TTrains from an Attune train list: origin departure and destination arrival, as public times,
    or with working=True (the timetable being checked shows half minutes) to the half minute."""
    roles = lst.roles
    missing = [r for r in ("origin", "origin_time") if r not in roles] + (
        [] if "destination" in roles and "dest_time" in roles else ["destination / destination time"])
    notes = []
    if len(missing) == 3 or ("origin" not in roles and "destination" not in roles):
        raise ValueError("The train list needs origin and destination columns with their times (e.g. Origin, "
                         "Origin Time, Destination, Destination Time) to be compared with a timetable.")
    codes = load_tiplocs()
    unknown = set()
    out, skipped = [], []
    for r, row in enumerate(lst.rows):
        hc_raw = row[roles["headcode"]] if "headcode" in roles else ""
        cat = row[roles["category"]].upper() if "category" in roles else ""
        if not passenger(norm_headcode(hc_raw), cat):
            skipped.append(hc_raw or f"row {lst.excel_rows[r]}")
            continue
        events = []
        for loc_role, time_role, role in (("origin", "origin_time", "dep"), ("destination", "dest_time", "arr")):
            if loc_role not in roles or time_role not in roles:
                continue
            place, hhmm = row[roles[loc_role]], _public(row[roles[time_role]], role, working)
            if not place or not hhmm:
                continue
            if re.fullmatch(r"[A-Z0-9]{3,7}", place):            # a location code: use its station name
                if place in codes:
                    place = codes[place]
                else:
                    unknown.add(place)
            events.append(Event(norm_loc(place), place, role, hhmm, row[roles[time_role]]))
        hc = norm_headcode(row[roles["headcode"]]) if "headcode" in roles else ""
        if not events:
            continue
        days = row[roles["days"]].upper() if "days" in roles else ""
        op = row[roles["operator"]].upper() if "operator" in roles else ""
        raw = row[roles["headcode"]] if "headcode" in roles else row[roles.get("uid", 0)]
        out.append(TTrain("", hc, raw, op if op in ("SN", "TL", "GX", "GN", "LO") else "", days, "", r, events,
                          events[0].name, events[-1].name))
    if skipped:
        notes.append(f"{len(skipped)} empty-stock / non-passenger train(s) in the list are not compared (a public "
                     f"timetable does not show them): {', '.join(skipped[:12])}"
                     + (" ..." if len(skipped) > 12 else ""))
    if unknown:
        notes.append(f"{len(unknown)} location code(s) in the train list have no known station name, so trains "
                     f"there can only match where the timetable uses the same code: {', '.join(sorted(unknown)[:15])}")
    return out, notes


def passenger(headcode: str, category: str = "") -> bool:
    """A train a public timetable shows: headcode class 1, 2 or 9 (empty stock 5, light engines 0, test and
    freight 3/4/6/7/8 are not), and not an Attune empty-stock category (EE, EL...)."""
    if category[:1] == "E":
        return False
    return not headcode or headcode[0] in "129"


def _order_score(train: TTrain, rows: Sequence[Tuple[str, str]]) -> Tuple[int, int]:
    """(agreement, shared locations): +1 for each pair of the train's stations that the table lists in
    the same order as the train calls at them, -1 for each pair in the opposite order."""
    first: Dict[str, int] = {}
    for i, (loc, _role) in enumerate(rows):
        first.setdefault(loc, i)
    seq: list = []
    for e in train.events:
        if e.loc in first and (not seq or seq[-1] != first[e.loc]):
            seq.append(first[e.loc])
    agree = sum((1 if b > a else -1 if b < a else 0) for i, a in enumerate(seq) for b in seq[i + 1:])
    return agree, len(set(seq))


def _evidence(train: TTrain, candidates: Sequence[TTrain]) -> Tuple[int, int]:
    """How well the best train of one direction's table fits: (times in common, same headcode)."""
    mine = {(e.loc, e.role, e.time) for e in train.events}
    best = (0, 0)
    for g in candidates:
        same = sum(1 for e in g.events if (e.loc, e.role, e.time) in mine)
        best = max(best, (same, int(bool(train.headcode) and g.headcode == train.headcode)))
    return best


def _elsewhere(train: TTrain, other: Timetable, natural: str) -> Optional[str]:
    """Another section of the timetable that clearly holds this train: same headcode and at least two
    identical times (never a weaker resemblance, so a genuinely missing train stays missing)."""
    if not train.headcode:
        return None
    mine = {(e.loc, e.role, e.time) for e in train.events}
    best, best_n = None, 1
    for sec, candidates in other.sections.items():
        if sec == natural:
            continue
        for g in candidates:
            if g.headcode == train.headcode:
                same = sum(1 for e in g.events if (e.loc, e.role, e.time) in mine)
                if same > best_n:
                    best, best_n = sec, same
    return best


def _single_point_direction(train: TTrain, day: str, other: Timetable) -> Optional[str]:
    """Direction for a train sharing only one station with the table: where the timetable has a train
    with the same headcode, or the same time at that station."""
    for direction in ("OUT", "RTN"):
        for g in other.sections.get(f"{direction} {day}", []):
            if train.headcode and g.headcode == train.headcode:
                return direction
    for direction in ("OUT", "RTN"):
        for g in other.sections.get(f"{direction} {day}", []):
            if any((e.loc, e.time) == (x.loc, x.time) for e in train.events for x in g.events):
                return direction
    return None


def build_base(trains: List[TTrain], other: Timetable, path: str, identifier: str,
               notes: Sequence[str] = ()) -> Timetable:
    """Place each base train in the sections it belongs to (days x direction) of the other timetable."""
    sections: Dict[str, List[TTrain]] = defaultdict(list)
    warnings = list(notes)
    unplaced = []
    relocated = []
    for t in trains:
        placed = False
        placed_in = set()
        for day, day_nums in DAY_TYPES:
            if not (day_set(t.days, f"OUT {day}") & day_nums) or (t.days == "" and day != "SX"):
                continue
            scores = {d: _order_score(t, other.locations.get(f"{d} {day}", [])) for d in ("OUT", "RTN")}
            shown = [d for d in scores if scores[d][1]]
            if not shown:                                      # not at any station of this day's tables:
                moved = _elsewhere(t, other, "")               # unless the timetable clearly has it elsewhere
                if moved and moved not in placed_in:
                    relocated.append(f"{t.raw_id or t.headcode} ({t.days}) compared in {moved}, where the "
                                     f"timetable shows it")
                    placed_in.add(moved)
                    sections[moved].append(TTrain(moved, t.headcode, t.raw_id, t.operator, t.days or day, t.notes,
                                                  0, t.events, t.origin, t.destination))
                    placed = True
                continue
            if len(shown) == 2:
                evidence = {d: _evidence(t, other.sections.get(f"{d} {day}", [])) for d in shown}
                if evidence["OUT"] != evidence["RTN"]:          # the timetable has this train one way
                    best = max(shown, key=lambda d: evidence[d])
                elif scores["OUT"][0] != scores["RTN"][0]:      # else: the table that lists its stations in order
                    best = max(shown, key=lambda d: scores[d][0])
                else:
                    best = _single_point_direction(t, day, other) or "OUT"
            else:
                best = shown[0]
            sec = f"{best} {day}"
            if _evidence(t, other.sections.get(sec, []))[0] == 0:
                moved = _elsewhere(t, other, sec)                 # e.g. an after-midnight train shown on the
                if moved and moved not in placed_in:              # next day's sheet of the timetable
                    relocated.append(f"{t.raw_id or t.headcode} ({t.days}) compared in {moved}, where the "
                                     f"timetable shows it")
                    sec = moved
            if sec in placed_in:
                continue
            placed_in.add(sec)
            copy = TTrain(sec, t.headcode, t.raw_id, t.operator, t.days or day, t.notes, len(sections[sec]),
                          t.events, t.origin, t.destination)
            sections[sec].append(copy)
            placed = True
        if not placed:
            unplaced.append(t.raw_id or t.headcode)
    if relocated:
        warnings.append("Shown in another section of the timetable (same headcode and times), so compared there: "
                        + "; ".join(relocated[:10]) + (" ..." if len(relocated) > 10 else ""))
    if unplaced:
        warnings.append(f"{len(unplaced)} base train(s) do not call at any station shown in the timetable, so "
                        f"there is nothing to compare: {', '.join(unplaced[:12])}" + (" ..." if len(unplaced) > 12
                                                                                    else ""))
    for sec in sections:                                        # timetable order: by first time
        sections[sec].sort(key=lambda t: (t.events[0].time, t.headcode))
        for i, t in enumerate(sections[sec]):
            t.column = i
    locations = {sec: list(dict.fromkeys((e.loc, e.role) for t in ts for e in t.events))
                 for sec, ts in sections.items()}
    return Timetable(path, identifier, dict(sections), locations, warnings)
