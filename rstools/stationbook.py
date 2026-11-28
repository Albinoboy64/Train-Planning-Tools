"""Station Working Book in the TRACS-RS layout, made from an Attune diagram XML.

One row for every train departing the station (or a chosen group of its platforms), in departure order,
on one sheet per day type (SX, SO, Su):

  A  inward working(s): headcode, origin time, origin, arrival time - 'Berth' when the unit starts
     the day in the platform, 'RP' / 'FP' when it is the rear / front portion of a train that divides here
  B  outward headcode and the stock, one unit per line from the front: '1C00HA\\n(387/1)\\n(387/1)'
  C  origin time, D origin, E destination of the outward train
  F  departure time and platform: '05 02\\n(9)'
  G  calling points with public times, the destination in capitals ('Empty to ...' for empty stock),
     how the train divides on the way, and 'Runs Monday and Friday only' where a row differs by day

Passenger trains (classes 1, 2, 9) show public times as 'HH MM'; other trains show working times as
'HH+MM'. Everything comes from the XML: trains (times, public times, platforms, stops) and unit diagrams
(which units work each train, front to rear, and the train each unit arrived on).
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, cast

from rstools.fsutil import output_folder
from rstools.days import DAY_NAMES, days_of_mask
from rstools.naming import agree, plural

DAY_GROUPS = {"SX": (0, 1, 2, 3, 4), "SO": (5,), "Su": (6,)}
SINGLE_DAYS = {"MO": (0,), "TO": (1,), "WO": (2,), "ThO": (3,), "FO": (4,), "SO": (5,), "Su": (6,)}
PLAN_PRIORITY = {"S": 3, "STP": 3, "D": 2, "P": 2, "L": 1, "LTP": 1}
PASSENGER_CLASSES = "129"
NBSP = "\xa0"
HEADINGS = ["Train ID    Origin Time\nStation of Origin\nArrival Time", "Train ID\n(Stock)", "Origin Time", "Origin",
            "Destination", "Departure Time (Platform)", ""]
WIDTHS = {"A": 20, "B": 10, "D": 20, "F": 10, "G": 60}          # C and E keep Excel's standard width
LINE_HEIGHT = 17.25                                             # Calibri 13: one line of text
WRAP = {"A": 22, "B": 22, "C": 22, "D": 22, "E": 22, "F": 22, "G": 70}   # characters a line before wrapping
DIVIDE_WINDOW = 3600                                            # a portion leaves within an hour of dividing


class StationBookError(Exception):
    pass


# --------------------------------------------------------------------------- #
# reading the XML
# --------------------------------------------------------------------------- #
def _secs(text: Optional[str]) -> Optional[int]:
    from rstools.attune_xml import secs
    return secs(text)


@dataclass
class Call:
    loc: str
    arr: Optional[int]
    arr_pub: Optional[int]
    dep: Optional[int]
    dep_pub: Optional[int]
    plat: str
    stops: bool                 # the train stops here (not a pass)
    passenger: bool             # ...and the stop is for passengers (not an operational 'N' stop)


@dataclass
class Train:
    id: str
    days: Set[int]
    plan: str
    calls: List[Call] = field(default_factory=list)
    valid_from: str = ""        # 'yyyy-mm-dd', from the XML
    valid_until: str = ""
    rar: str = ""               # how the XML marks it 'runs as required' ('' if it does not)
    operator: str = ""          # another operator's train merged in from its own XML ('' for the book's own)
    lines: Dict[int, str] = field(default_factory=dict)     # VPT only: call index -> line of the leg ending there

    @property
    def passenger(self) -> bool:
        return bool(self.id) and self.id[0] in PASSENGER_CLASSES


@dataclass
class Move:
    train: str
    origin: str
    dest: str
    dep: int
    arr: int
    coupled: List[str]          # diagram keys, front first ([] when the unit runs alone)


@dataclass
class Diagram:
    key: str                    # depot + number, e.g. 'SL611'
    fleet: str
    days: Set[int]
    moves: List[Move] = field(default_factory=list)
    plan: str = ""              # 'L' / 'S': an XML can hold the LTP and STP versions of a diagram for a day


@dataclass
class Plan:
    path: str
    start: str
    locations: Dict[str, str]
    trains: Dict[str, List[Train]]
    diagrams: List[Diagram]
    end: str = ""
    operator: str = ""          # from the XML heading, where it says

    @property
    def diagram_days(self) -> Set[int]:
        return set().union(*(d.days for d in self.diagrams)) if self.diagrams else set()


def _unroll(values: List[Optional[int]]) -> List[Optional[int]]:
    """Times after midnight continue past 24:00 so they always increase."""
    out: List[Optional[int]] = []
    base, last = 0, None
    for v in values:
        if v is None:
            out.append(None)
            continue
        v += base
        while last is not None and v < last - 6 * 3600:
            v += 86400
            base += 86400
        out.append(v)
        last = v
    return out


def read_plan(path: str) -> Plan:
    """Trains, unit diagrams and location names from an Attune diagram XML (or the trains of a VPT export)."""
    if path.lower().endswith(".vpt"):
        from rstools.timetable.vpt import read_plan as read_vpt_plan
        return read_vpt_plan(path)
    if path.lower().endswith((".pdf", ".docx", ".docm")):      # an Attune Single Train Report (F3 print)
        from rstools.fsutil import check_office_file
        from rstools.timetable.attune_print import read_plan as read_print_plan
        from rstools.timetable.prints import PrintError
        try:
            check_office_file(path)
            return read_print_plan(path)
        except (PrintError, OSError) as exc:
            raise StationBookError(str(exc))
    from rstools.timetable.cif import CifError, is_cif
    if path.lower().endswith((".cif", ".mca", ".txt")) or is_cif(path):
        from rstools.timetable.cif import read_plan as read_cif_plan
        try:
            return read_cif_plan(path)
        except CifError as exc:
            raise StationBookError(str(exc))
    from rstools import attune_xml as AX
    locations: Dict[str, str] = {}
    trains: Dict[str, List[Train]] = defaultdict(list)
    diagrams: List[Diagram] = []
    meta: dict = {}
    legs: List[dict] = []
    cur_train: Optional[Train] = None
    cur_diag: Optional[Diagram] = None
    move: Optional[dict] = None
    coupled_ids: List[Tuple[int, str]] = []
    coupled_pos: Optional[int] = None
    coupled_depot = ""
    coupled_num = ""
    try:
        for event, tag, el in AX.walk(path):
            if event == "start":
                if tag == "diagramExchange":
                    meta = dict(el.attrib)
                elif tag == "train":
                    cur_train, legs = Train(el.get("id", ""), days_of_mask(el.get("daysRun", "")),
                                            AX.plan_type(el.attrib),
                                            valid_from=el.get("validFrom", ""),
                                            valid_until=el.get("validUntil", ""),
                                            rar=runs_as_required(el.attrib)), []
                elif tag == "unitDiagram":
                    cur_diag = Diagram("", "", days_of_mask(el.get("daysrun", "")), plan=el.get("type", ""))
                    cur_diag.key = el.get("id", "").strip()          # depot added when its <depot> is read
                elif tag == "journey" and cur_diag is not None:
                    move = dict(el.attrib)
                    move["train"] = ""
                    coupled_ids = []
                elif tag == "coupled":
                    coupled_pos = int(el.get("position", "0") or 0)
                    coupled_depot = coupled_num = ""
                continue
            if tag == "leg" and cur_train is not None:
                legs.append(dict(el.attrib))
            elif tag == "train" and cur_train is not None:
                if legs:
                    cur_train.calls = _calls(legs)
                    trains[cur_train.id].append(cur_train)
                cur_train = None
                el.clear()
            elif tag == "location":
                loc = AX.location(el)
                if loc:
                    locations[loc[0]] = loc[1]
                el.clear()
            elif cur_diag is not None:
                if tag == "depot":
                    if coupled_pos is not None:
                        coupled_depot = el.get("id", "").strip()
                    elif not cur_diag.key.startswith(tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
                        cur_diag.key = el.get("id", "").strip() + cur_diag.key
                elif tag == "res" and not cur_diag.fleet:
                    cur_diag.fleet = el.get("id", "").strip()
                elif tag == "diagram" and coupled_pos is not None:
                    coupled_num = el.get("id", "").strip()
                elif tag == "coupled":
                    coupled_ids.append((coupled_pos or 0, coupled_depot + coupled_num))
                    coupled_pos = None
                elif tag == "activity" and move is not None and el.get("trainid"):
                    move["train"] = el.get("trainid")
                elif tag == "journey" and move is not None:
                    dep, arr = _secs(move.get("dep")), _secs(move.get("arr"))
                    if dep is not None and arr is not None:
                        cur_diag.moves.append(Move(move["train"], move.get("origin", ""), move.get("dest", ""),
                                                   dep, arr, [k for _p, k in sorted(coupled_ids)]))
                    move = None
                elif tag == "unitDiagram":
                    times = _unroll([t for m in cur_diag.moves for t in (m.dep, m.arr)])
                    for i, m in enumerate(cur_diag.moves):     # every move has both times (see above)
                        m.dep, m.arr = cast(int, times[2 * i]), cast(int, times[2 * i + 1])
                    diagrams.append(cur_diag)
                    cur_diag = None
                    el.clear()
    except ET.ParseError as exc:
        raise StationBookError(f"The XML could not be read ({exc}). Check it is a complete Attune export.")
    except OSError as exc:
        raise StationBookError(f"The XML could not be opened: {exc}")
    if not meta:
        raise StationBookError("This is not an Attune diagram XML.")
    if not trains:
        raise StationBookError("The XML contains no trains.")
    plan = Plan(path, meta.get("startdate", ""), locations, dict(trains), diagrams, meta.get("enddate", ""))
    plan.operator = next((meta[k].strip() for k in meta if k.lower() in _OPERATOR_KEYS and meta[k].strip()), "")
    return plan


_OPERATOR_KEYS = ("toc", "operator", "owner", "company", "toccode", "operatorcode")


_RAR_NAMES = ("runsasrequired", "asrequired", "rar", "runasrequired", "asreq")
_RAR_CHAR_NAMES = ("operatingcharacteristics", "operatingchars", "opchars", "characteristics", "opchar")
_RAR_STATUS_NAMES = ("status", "trainstatus", "timingstatus")
_TRUE = ("true", "y", "yes", "1", "q")


def runs_as_required(attrib: Dict[str, str]) -> str:
    """How a <train>'s attributes mark it 'runs as required' (e.g. 'runsAsRequired=true',
    'operatingCharacteristics=Q'), or '' if they do not."""
    for name, value in attrib.items():
        key = name.rsplit("}", 1)[-1].lower().replace("_", "").replace("-", "")
        v = (value or "").strip()
        if key in _RAR_NAMES and v.lower() in _TRUE:
            return f"{name}={v}"
        if key in _RAR_CHAR_NAMES and "Q" in v.upper().replace(" ", ""):
            return f"{name}={v}"
        if key in _RAR_STATUS_NAMES and v.upper() in ("Q", "RAR", "RUNS AS REQUIRED"):
            return f"{name}={v}"
    return ""


def _calls(legs: List[dict]) -> List[Call]:
    raw = []
    for i, leg in enumerate(legs):
        prev = legs[i - 1] if i else None
        kind_arr = (prev or {}).get("arrStopType", "")
        kind_dep = leg.get("depStopType", "")
        kind = kind_arr if prev else kind_dep
        raw.append([leg.get("origin", ""), _secs(prev.get("arr")) if prev else None,
                    _secs(prev.get("arrPub")) if prev else None, _secs(leg.get("dep")), _secs(leg.get("depPub")),
                    leg.get("depPlat") or (prev or {}).get("arrPlat") or "", kind])
    last = legs[-1]
    raw.append([last.get("dest", ""), _secs(last.get("arr")), _secs(last.get("arrPub")), None, None,
                last.get("arrPlat") or "", last.get("arrStopType", "")])
    times = _unroll([t for r in raw for t in r[1:5]])
    out = []
    for i, r in enumerate(raw):
        arr, arr_pub, dep, dep_pub = times[4 * i:4 * i + 4]
        kind = r[6]
        out.append(Call(r[0], arr, arr_pub, dep, dep_pub, r[5], kind != "P", kind not in ("P", "N")))
    return out


# --------------------------------------------------------------------------- #
# times and names as TRACS-RS writes them
# --------------------------------------------------------------------------- #
def _clock(sec: Optional[int], sep: str) -> str:
    """A time missing from the XML is shown blank rather than failing (rstools.clock)."""
    from rstools.clock import clock
    return clock(sec, sep)


def show_dep(train: Train, call: Call) -> str:
    """'05 34' (public, passenger) or '08+09' (working, other trains)."""
    if train.passenger:
        t = call.dep_pub if call.dep_pub is not None else call.dep
        return _clock(t, " ")
    return _clock(call.dep, "+")


def show_arr(train: Train, call: Call) -> str:
    if train.passenger:
        if call.arr_pub is not None:
            return _clock(call.arr_pub, " ")
        return _clock(call.arr + 59 if call.arr is not None else None, " ")   # never shown early
    return _clock(call.arr, "+")


def _hhmm(train: Train, call: Call) -> str:
    """Calling-point time: the public arrival (or the departure at the origin)."""
    if call.arr is None:
        return show_dep(train, call).replace(" ", "").replace("+", "")
    return show_arr(train, call).replace(" ", "").replace("+", "")


def _nb(text: str) -> str:
    return text.replace(" ", NBSP)


def days_phrase(days: Sequence[int]) -> str:
    """'Monday only', 'Monday and Friday only', 'Tuesday to Thursday only', 'Monday, Wednesday and Friday only'."""
    days = sorted(days)
    names = [DAY_NAMES[d] for d in days]
    if len(days) == 1:
        return f"{names[0]} only"
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{names[0]} to {names[-1]} only"
    return (", ".join(names[:-1]) + f" and {names[-1]} only") if len(days) > 2 else f"{names[0]} and {names[1]} only"


# --------------------------------------------------------------------------- #
# building the rows
# --------------------------------------------------------------------------- #
@dataclass
class Row:
    sort: Tuple
    cells: List[str]            # A..G without the day note


class Builder:
    def __init__(self, plan: Plan, station_tips: Set[str], station_name: str, platforms: Optional[Set[str]] = None,
                 names: Optional[Dict[str, str]] = None, cars: Optional[Dict[str, int]] = None):
        self.plan, self.tips, self.station_name = plan, station_tips, station_name
        self.platforms = platforms
        self.names = dict(plan.locations)
        self.names.update(names or {})
        self.cars = cars or {}
        self.by_key = {d.key: d for d in plan.diagrams}
        self.warnings: List[str] = []
        self.keep: Optional[Callable[[Train], bool]] = None        # which trains the book has (None: all)

    def name(self, tip: str) -> str:
        if tip in self.tips:
            return self.station_name
        name = self.names.get(tip, tip)
        return name.title() if name.isupper() and " " in name else name      # 'COULSDON TOWN' -> 'Coulsdon Town'

    def train(self, hc: str, day: int) -> Optional[Train]:
        versions = [t for t in self.plan.trains.get(hc, []) if day in t.days]
        if not versions:
            return None
        return max(versions, key=lambda t: PLAN_PRIORITY.get(t.plan.upper(), 2))

    # ---------------------------------------------------------------- unit diagrams
    def _move_at(self, hc: str, day: int, tip_dep: int, train: Train, call_index: int):
        """The diagrams (with the move) working train hc away from this station: a move starting here, or
        one passing through it (a through train)."""
        dep_mod = tip_dep % 86400
        found = []
        for d, i in self._index[day].get(hc, []):
            m = d.moves[i]
            if m.origin in self.tips and abs(m.dep % 86400 - dep_mod) <= 1800:
                found.append((d, i, False))
            elif m.origin not in self.tips and _covers(m, train, call_index):
                found.append((d, i, True))
        return found

    def build(self, day: int) -> List[Row]:
        """The rows of one stock day. A train belongs to the stock day of the unit diagram that works it, so a
        train running after midnight on the previous day's diagram is at the end of that day (not the start of
        the next), and the day's first train is the first of its diagrams. Trains with no diagram here stay on
        the calendar day they run."""
        nxt, prev = (day + 1) % 7, (day - 1) % 7
        self.day_diagrams = {k: day_diagrams(self.plan.diagrams, k) for k in {day, nxt, prev}}
        self._index: Dict[int, Dict[str, list]] = {}
        for k, ds in self.day_diagrams.items():
            self._index[k] = defaultdict(list)
            for d in ds:
                for i, m in enumerate(d.moves):
                    self._index[k][m.train].append((d, i))
        rows = []
        for hc in self.plan.trains:
            for cal, t in ((day, self.train(hc, day)), (nxt, self.train(hc, nxt))):
                if t is None or (self.keep is not None and not self.keep(t)):
                    continue
                owner = self._stock_day(hc, cal)
                if owner != day:
                    continue
                for i, c in enumerate(t.calls[:-1]):
                    if c.loc not in self.tips or not c.stops or c.dep is None:
                        continue
                    if self.platforms and c.plat not in self.platforms:
                        continue
                    rows.append(self._row(t, i, day))
        rows.sort(key=lambda r: r.sort)
        return rows

    def _stock_day(self, hc: str, cal: int) -> int:
        """The stock day a train running on calendar day `cal` belongs to: the day before when it is worked
        after midnight by that day's diagram (and by no diagram of its own day), else `cal`."""
        if self._index[cal].get(hc) if cal in self._index else False:
            return cal
        before = (cal - 1) % 7
        if before in self._index and any(d.moves[i].dep >= 86400 for d, i in self._index[before].get(hc, [])):
            return before
        return cal

    def _row(self, t: Train, i: int, day: int) -> Row:
        c = t.calls[i]
        dep = cast(int, c.dep)                  # build() only makes rows for calls with a departure
        origin, dest = t.calls[0], t.calls[-1]
        units = self._move_at(t.id, day, dep, t, i)
        formation = self._formation(units)
        inward = self._inward(t, i, day, units, formation)
        stock = "\n".join(f"({self.by_key[k].fleet if k in self.by_key else '?'})" for k in formation)
        b = t.id + (("\n" + stock) if stock else "") + (f"\n[{t.operator}]" if t.operator else "")
        f = show_dep(t, c) + (f"\n({c.plat})" if c.plat else "")
        g = self._calling(t, i, day, units, formation) if t.passenger else f"Empty to {self.name(dest.loc)}"
        cells = [inward, b, show_dep(t, origin), self.name(origin.loc), self.name(dest.loc), f, g]
        return Row((self._day_time(dep, units), t.id), cells)

    @staticmethod
    def _day_time(dep: int, units) -> int:
        """Where the departure falls in the operating day, on the unit diagram's own clock (which carries on
        past 24:00): a trip after midnight at the end of the day's diagrams sorts at the end (24:01), a first
        trip at 01:15 at the start."""
        if not units:
            return dep
        d, i, _through = units[0]
        m = d.moves[i]
        t = m.dep // 86400 * 86400 + dep % 86400
        return t + 86400 if t < m.dep - 6 * 3600 else t          # a through train reaching here after midnight

    def _formation(self, units) -> List[str]:
        for d, i, _through in units:
            if d.moves[i].coupled:
                return list(d.moves[i].coupled)
        return [d.key for d, _i, _t in units]

    def _inward(self, t: Train, i: int, day: int, units, formation: List[str]) -> str:
        """Column A: where each unit came from - in arrival order, one entry per inward train."""
        if not units:
            return ""
        entries: Dict[str, Tuple[int, str]] = {}       # inward train -> (front-most position, text)
        position = {k: n for n, k in enumerate(formation)}
        berth = False
        for d, k, through in units:
            if through or (k and d.moves[k - 1].train == t.id):
                pos = position.get(d.key, 99)
                old = entries.get(t.id)
                entries[t.id] = (min(pos, old[0]) if old else pos, old[1] if old else self._inward_text(t, i))
                continue
            prev = d.moves[k - 1] if k else None
            if prev is None or prev.dest not in self.tips:
                berth = True
                continue
            tin = (self.train(prev.train, day) or self.train(prev.train, (day + 1) % 7)
                   or self.train(prev.train, (day - 1) % 7))
            if tin is None:
                berth = True
                continue
            j = max((n for n, cc in enumerate(tin.calls) if cc.loc in self.tips), default=None)
            if j is None:
                berth = True
                continue
            text = self._inward_text(tin, j)
            portion = self._portion(prev, d, formation)
            if portion:
                text += "\n" + portion
            pos = position.get(d.key, 99)
            old = entries.get(tin.id)
            entries[tin.id] = (min(pos, old[0]) if old else pos, old[1] if old else text)
        texts = [txt for _a, txt in sorted(entries.values())]
        if berth and not texts:
            return "Berth"
        if berth:
            texts.append("Berth")
        return "\n".join(texts)

    def _inward_text(self, tin: Train, j: int) -> str:
        call = tin.calls[j]
        arr = show_arr(tin, call) if call.arr is not None else show_dep(tin, call)
        return f"{tin.id}    {show_dep(tin, tin.calls[0])}\n{self.name(tin.calls[0].loc)}\n{arr}"

    def _portion(self, prev: Move, d: Diagram, formation: List[str]) -> str:
        """'RP' / 'FP' when only the rear / front part of the inward train forms this train."""
        inbound = prev.coupled or [d.key]
        taken = [k for k in inbound if k in formation]
        if not taken or len(taken) == len(inbound):
            return ""
        pos = [inbound.index(k) for k in taken]
        return "RP" if max(pos) == len(inbound) - 1 and min(pos) > 0 else "FP"

    # ---------------------------------------------------------------- calling points
    def _stops_text(self, t: Train, calls: List[Call], last_caps: bool = True) -> str:
        parts = []
        stops = [c for c in calls if c.passenger]
        for n, c in enumerate(stops):
            name = self.name(c.loc)
            if last_caps and n == len(stops) - 1:
                name = name.upper()
            parts.append(f"{_nb(name)}{NBSP}({_hhmm(t, c)})")
        return " ".join(parts)

    def _calling(self, t: Train, i: int, day: int, units, formation: List[str]) -> str:
        after = t.calls[i + 1:]
        split = self._divide(t, i, day, units, formation)
        if split is None:
            return self._stops_text(t, after)
        at, groups = split
        cut = next(n for n, c in enumerate(after) if c.loc == at and c.arr is not None)
        head = self._stops_text(t, after[:cut + 1], last_caps=False)
        lines = [f"{head} The train divides at {_nb(self.name(at)).replace(NBSP, ' ')}"]
        for word, coaches, text in groups:
            lines.append(f"The {word} {coaches} coaches call at: {text}")
        return "\n".join(lines)

    def _divide(self, t: Train, i: int, day: int, units, formation: List[str]):
        """Where the train divides after leaving here, and what each portion does: (location,
        [('front'/'rear', coaches, calling points)]), or None."""
        if len(formation) < 2 or not units:
            return None
        ends = {}
        for d, k, _through in units:
            n = k
            while n + 1 < len(d.moves) and d.moves[n + 1].train == t.id:
                n += 1
            ends[d.key] = (d, n)
        dest = t.calls[-1].loc
        leaving = {key: v for key, v in ends.items() if v[0].moves[v[1]].dest != dest}
        if not leaving or len(leaving) == len(ends):
            return None
        at = next(iter(leaving.values()))[0].moves[next(iter(leaving.values()))[1]].dest
        if not any(c.loc == at and c.arr is not None for c in t.calls[i + 1:]):
            return None         # the unit leaves where the train does not stop after here (e.g. a pass)
        staying = [k for k in formation if k not in leaving]
        groups = []
        for keys, other in ((staying, None), ([k for k in formation if k in leaving], leaving)):
            if not keys:
                continue
            pos = min(formation.index(k) for k in keys)
            word = "front" if pos == 0 else "rear"
            coaches = sum(self.cars.get(self.by_key[k].fleet, 0) if k in self.by_key else 0 for k in keys)
            if other is None:
                cut = next((n for n, c in enumerate(t.calls) if c.loc == at and n > i), None)
                text = self._stops_text(t, t.calls[cut + 1:]) if cut is not None else ""
            else:
                d, n = other[keys[0]]
                nxt = d.moves[n + 1] if n + 1 < len(d.moves) else None
                t2 = (self.train(nxt.train, day) or self.train(nxt.train, (day + 1) % 7)) if nxt is not None else None
                if nxt is None or t2 is None or nxt.origin != at or nxt.dep - d.moves[n].arr > DIVIDE_WINDOW:
                    return None
                text = self._stops_text(t2, t2.calls[1:])
            groups.append((word, coaches or "?", text))
        groups.sort(key=lambda g: g[0] != "front")
        return at, groups


def day_diagrams(diagrams: List[Diagram], day: int) -> List[Diagram]:
    """The unit diagrams running on `day`; where the XML has the LTP and the STP version of a diagram for the
    day, the STP one only (as Attune works it)."""
    best: Dict[str, Diagram] = {}
    for d in diagrams:
        if day not in d.days:
            continue
        old = best.get(d.key)
        if old is None or PLAN_PRIORITY.get(d.plan.upper(), 0) > PLAN_PRIORITY.get(old.plan.upper(), 0):
            best[d.key] = d
    return list(best.values())


def _covers(m: Move, train: Train, call_index: int) -> bool:
    """A diagram move working `train` through the call at `call_index` (it started further back)."""
    c = train.calls[call_index]
    locs = [cc.loc for cc in train.calls]
    try:
        start = locs.index(m.origin)
    except ValueError:
        return False
    end = next((n for n in range(len(locs) - 1, -1, -1) if locs[n] == m.dest), None)
    return end is not None and start < call_index < end and c.dep is not None


# --------------------------------------------------------------------------- #
# the workbook
# --------------------------------------------------------------------------- #
def _lines(text: str, width: int) -> int:
    """Lines a cell needs: its own line breaks, plus wrapping at spaces (names use non-breaking ones)."""
    total = 0
    for para in text.split("\n"):
        cur, lines = 0, 1
        for tok in para.split(" "):
            add = len(tok) + (1 if cur else 0)
            if cur and cur + add > width:
                lines, cur = lines + 1, len(tok)
            else:
                cur += add
        total += lines
    return total


def sheet_rows(builder: Builder, days: Sequence[int]) -> Tuple[List[List[str]], Set[int]]:
    """The rows of one sheet (a day type): each day's rows, merged where identical, with 'Runs ... only'
    added to a row that does not run on every day of the sheet. Returns (rows, days without diagrams)."""
    seen: Dict[tuple, dict] = {}
    no_diagrams = set()
    for d in days:
        built = builder.build(d)
        if built and not any(d in dg.days for dg in builder.plan.diagrams):
            no_diagrams.add(d)                     # trains run, but the XML has no unit diagrams that day
        for r in built:
            key = tuple(r.cells)
            entry = seen.setdefault(key, {"sort": r.sort, "days": set(), "cells": r.cells})
            entry["days"].add(d)
            entry["sort"] = min(entry["sort"], r.sort)
    out = []
    for entry in sorted(seen.values(), key=lambda e: (e["sort"], min(e["days"]))):
        cells = list(entry["cells"])
        if len(days) > 1 and entry["days"] != set(days):
            lines = max(len(cells[0].split("\n")), len(cells[1].split("\n")))
            pad = max(lines - len(cells[6].split("\n")), 1)
            cells[6] = cells[6] + "\n" * pad + "Runs " + days_phrase(sorted(entry["days"]))
        out.append(cells)
    return out, no_diagrams


def write_book(path: str, sheets: List[Tuple[str, List[List[str]]]], header: str):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.properties import PageSetupProperties
    from rstools.fsutil import clean_cell, plain_text, sheet_title
    wb = openpyxl.Workbook()
    wb.properties.creator = wb.properties.lastModifiedBy = "Train Planning Tools"
    wb.remove(wb.active)
    thin = Side(style="thin", color="FF000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    normal, italic = Font(name="Calibri", size=13), Font(name="Calibri", size=13, italic=True)
    centre = Alignment(horizontal="center", vertical="top", wrap_text=True)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    head_fill = PatternFill("solid", fgColor="FF99CCFF")
    for title, rows in sheets:
        ws = wb.create_sheet(sheet_title(title, wb.sheetnames))
        for col, w in WIDTHS.items():
            ws.column_dimensions[col].width = w
        for c, text in enumerate(HEADINGS, start=1):
            cell = ws.cell(1, c, text)
            cell.font, cell.alignment, cell.border, cell.fill = normal, centre, border, head_fill
        ws.row_dimensions[1].height = 3 * LINE_HEIGHT
        for r, cells in enumerate(rows, start=2):
            n = 1
            for c, text in enumerate(cells, start=1):
                cell = ws.cell(r, c, clean_cell(text))
                cell.font = italic if c == 1 else normal
                cell.alignment = left if c == 7 else centre
                cell.border = border
                n = max(n, _lines(text or "", WRAP["ABCDEFG"[c - 1]]))
            ws.row_dimensions[r].height = n * LINE_HEIGHT
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.print_title_rows = "1:1"
        ws.oddHeader.center.text = header
        ws.oddFooter.right.text = "&P/&N"
        plain_text(ws)
    from rstools.xlsave import save_workbook
    save_workbook(wb, path)


# --------------------------------------------------------------------------- #
# the whole book
# --------------------------------------------------------------------------- #
def timetable_name(plan: Plan) -> str:
    """'Dec23' from the plan's start date (2023-12-10)."""
    m = re.match(r"(\d{4})-(\d{2})", plan.start or "")
    if not m:
        return ""
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{months[int(m.group(2)) - 1]}{m.group(1)[2:]}"


def parse_platforms(text: str) -> Optional[Set[str]]:
    """'10-15' -> {'10'..'15'}; '1, 2, 4A' -> {'1', '2', '4A'}; '' -> None (every platform)."""
    out = set()
    for part in re.split(r"[,;\s]+", (text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            out |= {str(n) for n in range(a, b + 1)}
        else:
            out.add(part.upper())
    return out or None


def make_book(xml: str, station: str, out_dir: str = "", out_name: str = "", operator: str = "",
              timetable: str = "", services: str = "", label: str = "", platforms: str = "",
              day_types: Sequence[str] = ("SX", "SO", "Su"),
              log: Callable[[str], None] = lambda m: None,
              progress: Callable[[float, str], None] = lambda f, m: None,
              merge_xml: Sequence[str] = (), book_operator: str = "",
              other_operators: Optional[Sequence[str]] = None) -> Tuple[str, List[str], str]:
    """Write the Station Working Book. Returns (path, warnings, summary). `merge_xml`: other operators' files
    (Attune XML, VPT or F3 print) whose trains are added to the book (marked with their operator).
    `book_operator`: 'TLGN' / 'SNGX' (only that operator's own trains, by unit diagram depot - see train_groups)
    or 'GTR' (all of them); it also gives the operator and services in the heading unless those are given.
    '' keeps every train. `other_operators`: the merged operators to show (None: all of them)."""
    from rstools.statspack.fleet import FleetTable
    from rstools.statspack.seats import Stations
    from rstools.fsutil import unique_stem
    if not xml or not os.path.isfile(xml):
        raise StationBookError("Choose the Attune XML.")
    if not station.strip():
        raise StationBookError("Choose the station.")
    missing = [p for p in merge_xml if not os.path.isfile(p)]
    if missing:
        raise StationBookError("These other operators' file(s) could not be found:\n" + "\n".join(missing))
    group = book_operator_of(book_operator) if book_operator.strip() else ""
    if book_operator.strip() and not group:
        raise StationBookError(f"'{book_operator}' is not an operator choice: use TLGN, SNGX or GTR.")
    day_groups = [(dt, days) for dt, days in ((dt, DAY_GROUPS.get(dt) or SINGLE_DAYS.get(dt)) for dt in day_types)
                  if days]
    if not day_groups:                          # checked before the XML is read
        raise StationBookError("Choose at least one day type (SX, SO or Su).")
    if group:
        operator = operator.strip() or BOOK_OPERATORS[group][0]
        services = services.strip() or BOOK_OPERATORS[group][1]
    log(f"Reading {os.path.basename(xml)}")
    progress(0.03, "Reading the XML...")
    plan = _plan_of(xml)
    if merge_xml:
        others = []
        for p in merge_xml:
            log(f"Merging {os.path.basename(p)}")
            try:
                others.append(_plan_of(p))
            except Exception as exc:                  # a VPT that cannot be read (PrintError)
                if p.lower().endswith((".vpt", ".cif", ".mca")):
                    raise StationBookError(str(exc))
                raise
        plan = merge_plans(plan, others)
    progress(0.45, f"Finding the trains at {station.strip()}...")
    tips = Stations(plan.locations).find(station.strip())
    if not tips:
        raise StationBookError(f"'{station}' is not a location in the XML.")
    plats = parse_platforms(platforms)
    timetable = timetable.strip() or timetable_name(plan)
    label = label.strip() or station.strip() + (f" ({_short(operator)})" if operator.strip() else "")
    fleet = FleetTable.load()
    cars = {r.cls: r.cars for r in fleet.rows if r.cars}
    # the station as the book names it (Origin / Destination columns): the sheet name without '(TLGN)'
    shown = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip() or station.strip()
    builder = Builder(plan, tips, shown, plats, cars=cars)
    groups = train_groups(plan) if group in ("TLGN", "SNGX") else {}
    shown_ops = None if other_operators is None else {o.strip() for o in other_operators}

    def keep(t: Train) -> bool:
        if t.operator:
            return shown_ops is None or t.operator in shown_ops
        return group in ("", "GTR") or group in groups.get(t.id, ())

    builder.keep = keep
    unknown = sorted({t.id for vs in plan.trains.values() for t in vs if not t.operator and t.id not in groups
                      and any(c.loc in tips and c.stops for c in t.calls[:-1])}) if group in ("TLGN", "SNGX") else []
    sheets, warnings, total = [], [], 0
    missing_days: Set[int] = set()
    for n, (dt, days) in enumerate(day_groups):
        progress(0.45 + 0.4 * n / len(day_groups), f"{station.strip()}: {dt} departures...")
        rows, no_diag = sheet_rows(builder, days)
        missing_days |= no_diag
        log(f"{dt}: {len(rows)} row(s)")
        total += len(rows)
        sheets.append((f"{label} {dt}", rows))
    vpts = [os.path.basename(p) for p in merge_xml
            if p.lower().endswith((".vpt", ".cif", ".mca", ".pdf", ".docx", ".docm"))]
    if vpts:
        warnings.append("Trains from " + ", ".join(vpts) + " come from a VPT or CIF file or an F3 print, which has "
                        "no unit diagrams: their stock is blank, and working times are shown where there are no public "
                        "times. An Attune XML gives the stock as well.")
    if unknown:
        warnings.append(f"{plural(len(unknown), 'train')} at {station.strip()} {agree(len(unknown), 'is', 'are')} "
                        "worked by no unit diagram from a TLGN "
                        f"(HE, TB) or SNGX (BI, SU, SL) depot in the XML, so they are left out of the {group} book "
                        "(e.g. "
                        + ", ".join(unknown[:5]) + "). Choose All GTR to include them.")
    if missing_days:
        warnings.append("The XML has no unit diagrams for " + ", ".join(DAY_NAMES[d] for d in sorted(missing_days))
                        + ", so the stock and inward workings are missing on those days. Export the XML with the "
                          "unit diagrams for every day.")
    if not total:
        warnings.append(f"No train departs {station}" + (f" from platform(s) {platforms}" if plats else "")
                        + " in this XML.")
    header = (f"{operator.strip() + ' ' if operator.strip() else ''}{timetable + ' ' if timetable else ''}"
              f"Station Working Book - {station.strip()}" + (f" ({services.strip()})" if services.strip() else ""))
    folder = output_folder(out_dir)
    stem = out_name.strip() or (f"{operator.strip() + ' ' if operator.strip() else ''}"
                                f"{timetable + ' ' if timetable else ''}Station Working Book - {station.strip()}"
                                + (f" {_plat_label(plats)}" if plats else ""))
    path = os.path.join(folder, unique_stem(folder, stem, (".xlsx",)) + ".xlsx")
    progress(0.88, "Saving...")
    from rstools.fsutil import save_output
    save_output(lambda: write_book(path, sheets, header), path, StationBookError)   # plain message if it fails
    log(f"Saved: {path}")
    progress(1.0, "Done")
    summary = f"{plural(total, 'departure row')} on {plural(len(sheets), 'sheet')} for {station.strip()}."
    return path, warnings, summary


def xml_summary(xml: str) -> Tuple[List[str], str, List[int], str]:
    """What the window shows about an XML chosen for a station book: (its stations, its timetable name, the days
    it has unit diagrams for, its start date). The plan read is kept (_plan_of), so making the book does not read
    the XML again."""
    from rstools.statspack.attune import parse_attune_xml
    from rstools.statspack.engine import cached
    from rstools.statspack.seats import network_stations
    plan = _plan_of(xml)
    stations = network_stations(cached(parse_attune_xml, xml))
    return stations, timetable_name(plan), sorted(plan.diagram_days), plan.start


def _plan_of(xml: str) -> Plan:
    """read_plan, kept while the file is unchanged (several books from one XML read it once), in the app's
    shared store of files read (rstools.filecache). A file that fails to read is never kept."""
    from rstools import filecache
    key, stamp = filecache.key_of(_plan_of, xml)
    plan = filecache.get(key, stamp)
    if plan is None:
        plan = read_plan(xml)
        filecache.put(key, stamp, plan)
    return plan


def merge_plans(plan: Plan, others: Sequence[Plan]) -> Plan:
    """The book's own plan with other operators' plans (their own Attune XMLs) added: their trains and unit
    diagrams join the book, each train marked with its operator. A train or diagram whose ID the plan already
    has is renamed 'ID/OPERATOR' so nothing is overwritten. The plans must cover overlapping dates."""
    import copy
    merged = Plan(plan.path, plan.start, dict(plan.locations), {k: list(v) for k, v in plan.trains.items()},
                  list(plan.diagrams), plan.end, plan.operator)
    for other in others:
        op = other.operator or os.path.splitext(os.path.basename(other.path))[0][:12]
        if plan.start and plan.end and other.start and other.end and (other.start[:10] > plan.end[:10]
                                                                      or other.end[:10] < plan.start[:10]):
            raise StationBookError(f"{os.path.basename(other.path)} covers {other.start[:10]} to {other.end[:10]}, "
                                   f"which does not overlap the main XML ({plan.start[:10]} to {plan.end[:10]}).")
        for tip, name in other.locations.items():
            merged.locations.setdefault(tip, name)
        renamed: Dict[str, str] = {}
        for tid, versions in other.trains.items():
            new_id = tid if tid not in merged.trains else f"{tid}/{op}"
            renamed[tid] = new_id
            out = []
            for t in versions:
                t2 = copy.copy(t)
                t2.id, t2.operator = new_id, t.operator or op
                out.append(t2)
            merged.trains[new_id] = out
        keys = {d.key for d in merged.diagrams}
        for d in other.diagrams:
            d2 = copy.deepcopy(d)
            if d2.key in keys:
                d2.key = f"{d.key}/{op}"
            for m in d2.moves:
                m.train = renamed.get(m.train, m.train)
            merged.diagrams.append(d2)
    return merged


def parse_station_list(text: str) -> List[Tuple[str, str]]:
    """'London Kings Cross; London Bridge [10-15]; Cambridge' -> [(station, platforms)]."""
    out = []
    for part in re.split(r"[;\n]", text or ""):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(.*?)\s*\[([^\]]*)\]", part)
        out.append((m.group(1).strip(), m.group(2).strip()) if m else (part, ""))
    return [(s, p) for s, p in out if s]


def _books_job(xml: str, entries: Sequence[Tuple[str, str]], kw: dict) -> List[tuple]:
    """Make several books (in a helper process): [(station, path, warnings, summary, error)]."""
    out = []
    for station, plats in entries:
        try:
            path, warnings, summary = make_book(xml, station, platforms=plats, **kw)
            out.append((station, path, warnings, summary, ""))
        except StationBookError as exc:
            out.append((station, "", [], "", str(exc)))
        except Exception as exc:                # any other failure is this station's alone: the rest are still made
            from rstools import errorlog
            out.append((station, "", [], "", errorlog.file_problem(exc) or errorlog.describe(exc)))
    return out


def make_books(xml: str, entries: Sequence[Tuple[str, str]], out_dir: str = "", operator: str = "",
               timetable: str = "", services: str = "", day_types: Sequence[str] = ("SX", "SO", "Su"),
               log: Callable[[str], None] = lambda m: None,
               progress: Callable[[float, str], None] = lambda f, m: None,
               merge_xml: Sequence[str] = (), book_operator: str = "",
               other_operators: Optional[Sequence[str]] = None) -> List[tuple]:
    """A Station Working Book for each (station, platforms), one file each, shared over the CPU cores (each
    helper reads the XML once). Returns [(station, path, warnings, summary, error)] in the order given; a
    station that cannot be made gives its error, the others are still made."""
    if not xml or not os.path.isfile(xml):
        raise StationBookError("Choose the Attune XML.")
    entries = list(dict.fromkeys((s.strip(), p.strip()) for s, p in entries if s.strip()))   # each book once
    if not entries:
        raise StationBookError("Choose the station(s).")
    kw = dict(out_dir=out_dir, operator=operator, timetable=timetable, services=services, day_types=tuple(day_types),
              merge_xml=tuple(merge_xml), book_operator=book_operator,
              other_operators=None if other_operators is None else tuple(other_operators))
    import multiprocessing
    done: Dict[int, tuple] = {}
    workers = min(max(1, (os.cpu_count() or 1) - 1), len(entries) // 2)
    if workers >= 2 and multiprocessing.parent_process() is None:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from multiprocessing import get_context
        log(f"Making {len(entries)} books on {workers} CPU cores...")
        progress(0.02, f"Making {len(entries)} books...")
        try:                                        # one job per station: each helper reads the XML once (cached)
            from rstools.pools import stoppable
            with stoppable(ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))) as pool:
                jobs = {pool.submit(_books_job, xml, [e], kw): i for i, e in enumerate(entries)}
                for fut in as_completed(jobs):
                    done[jobs[fut]] = fut.result()[0]       # each station's own errors are in its result
                    progress(0.02 + 0.98 * len(done) / len(entries), f"{len(done)} of {len(entries)} books made")
            results = [done[i] for i in range(len(entries))]
            for st, _path, _w, summary, err in results:
                log(f"{st}: {summary or err}")
            return results
        except Exception as exc:                    # helpers unavailable or lost: make the rest here instead
            log(f"(the rest made one at a time: {exc})")
    results = []
    for n, (station, plats) in enumerate(entries):
        if n in done:                               # already made by a helper: never made twice
            results.append(done[n])
            continue
        part = (lambda f, m, n=n: progress((n + f) / len(entries), m))
        res = _books_job(xml, [(station, plats)], dict(kw, log=log, progress=part))[0]
        results.append(res)
    return results


# --------------------------------------------------------------------------- #
# which of GTR's operators (TLGN / SNGX) a train belongs to
# --------------------------------------------------------------------------- #
BOOK_OPERATORS = {"TLGN": ("GTR(TLGN)", "Thameslink and Great Northern services only"),
                  "SNGX": ("GTR(SNGX)", "Southern and Gatwick Express services only"),
                  "GTR": ("GTR", "")}
TOC_GROUP = {"SN": "SNGX", "GX": "SNGX", "SNGX": "SNGX", "TL": "TLGN", "GN": "TLGN", "TLGN": "TLGN"}


def book_operator_of(text: str) -> str:
    """'TLGN' / 'SNGX' / 'GTR' for an operator choice ('GTR(SNGX)', 'sngx', 'All GTR' ...), '' for free text
    that names none of them (the book then has every train)."""
    t = re.sub(r"[^A-Z]", "", (text or "").upper())
    for key in ("TLGN", "SNGX"):
        if t.endswith(key):
            return key
    return "GTR" if t in ("GTR", "ALLGTR") else ""


def train_groups(plan: Plan) -> Dict[str, Set[str]]:
    """{train ID: {'TLGN' and/or 'SNGX'}} for the book's own trains, from the depot of each unit diagram that
    works them (SNGX: BI, SU, SL; TLGN: HE, TB - rstools.statspack.model.OPERATOR_DEPOTS). A train with no such
    diagram takes the operator of its plan where that is a GTR operator (a VPT's header, e.g. 'SN')."""
    from rstools.statspack.model import OPERATOR_DEPOTS, operator_of
    out: Dict[str, Set[str]] = defaultdict(set)
    for d in plan.diagrams:
        m = re.match(r"[A-Z]+", d.key)
        op = operator_of(m.group()) if m else ""
        if op not in OPERATOR_DEPOTS:
            continue
        for mv in d.moves:
            if mv.train:
                out[mv.train].add(op)
    fallback = TOC_GROUP.get(plan.operator.strip().upper(), "")
    if fallback:
        for tid, versions in plan.trains.items():
            if tid not in out and not any(t.operator for t in versions):
                out[tid].add(fallback)
    return dict(out)


def list_operators(paths: Sequence[str]) -> List[str]:
    """The operators of the trains in other operators' files (XML, VPT or F3 print), sorted; a file that
    cannot be read is skipped. Shown in the app so a book can leave some of them out."""
    found: Set[str] = set()
    for p in paths:
        try:
            other = _plan_of(p)
        except Exception:
            continue
        op = other.operator or os.path.splitext(os.path.basename(p))[0][:12]
        found |= {t.operator or op for versions in other.trains.values() for t in versions}
    return sorted(x for x in found if x)


def _short(operator: str) -> str:
    """'GTR(TLGN)' -> 'TLGN' for the sheet names."""
    m = re.search(r"\(([^)]+)\)", operator)
    return m.group(1) if m else operator.strip()


def _plat_label(plats: Optional[Set[str]]) -> str:
    if not plats:
        return ""
    nums = sorted(int(p) for p in plats if p.isdigit())
    if nums and len(nums) == len(plats) and nums == list(range(nums[0], nums[-1] + 1)):
        return f"platforms {nums[0]}-{nums[-1]}" if len(nums) > 1 else f"platform {nums[0]}"
    return "platforms " + ", ".join(sorted(plats))
