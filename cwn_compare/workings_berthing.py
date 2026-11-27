"""Berthing arrangements for platform workings.

Platform workings (the Victoria, London Bridge and Brighton books made with the CWNs) have one tab per day.
Each tab should end with '<Day> Berthing Arrangements:-': what stands at each platform and siding at the end of
that day, and the train it works next. The CWN export does not make this section, so it is made here from the
trains on the tab itself:

* Platforms: every unit that berths at a platform (the 'Berth BI151 05.50TO (3)' lines) is added up by platform,
  next train, and class: '12 377 for 05 50 TO'. The tab of the next day is checked: the train must leave that
  platform from 'Berth' (if the berthed unit leaves as the rear portion it is shown 'for RP ...'), and a train
  that leaves a platform from a berth the previous day does not list (a unit berthed for more than one night)
  is added.
* Sidings (Victoria and Battersea Pier carriage sidings, Brighton Wall Siding): units standing there at the end of
  the day are those that arrived and have not left, carried from the days before; each is matched to the next
  train that leaves the siding, on this tab's following days. The road (No 1 / No 2, Rec / 2) comes from an Attune
  XML when one is given, else the roads are filled in order and the log says to check them.

The input workbook is never changed: a copy with the sections written is saved.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from rstools import naming
from rstools.fsutil import clean_cell, output_folder, unique_stem

from .days import tab_day
from .model import Block, CWNModel, SheetModel, parse_workbook, time_minutes
from rstools.days import DAY_CODES, DAY_NAMES

Log = Callable[[str], None]

_CODE_DAY = {"MO": 0, "TO": 1, "WO": 2, "THO": 3, "FO": 4, "SO": 5, "SUO": 6, "SU": 6, "SUN": 6}
_NEXT = re.compile(r"^(?:berth\s+)?[A-Za-z]{1,4}\d{1,4}\s+(\d{1,2})([.+:])(\d{2})\s*([A-Za-z]{1,4})?", re.I)


class WorkingsError(Exception):
    pass


@dataclass
class Siding:
    location: str                      # as written in the From / Destination columns
    tiploc: str                        # the Attune location, for the optional XML
    roads: List[Tuple[str, str]]       # (label in the section, Attune road code)


@dataclass
class Layout:
    """How a station's section looks: its platforms and sidings, the columns the label and text go in."""
    name: str
    platforms: List[str]
    sidings: List[Siding] = field(default_factory=list)
    label_col: int = 1
    text_col: int = 3
    siding_text_col: int = 3
    siding_merge: Optional[Tuple[int, int]] = None   # label merged across columns a-b, text from siding_text_col
    siding_text_to: int = 0                          # merged text spans siding_text_col..siding_text_to
    gap_before_sidings: int = 1
    gap_between_sidings: int = 0
    sunday: str = "SuO"
    tlk: bool = False                                # '8 700 TLK for ...'
    joiner: str = "  "


LAYOUTS: Dict[str, Layout] = {
    "victoria": Layout(
        "Victoria", [str(p) for p in range(9, 20)],
        [Siding("Victoria C.H.S.", "VICTCS", [("NO 1 CARRIAGE SIDING", "S1"), ("NO 2 CARRIAGE SIDING", "S2")]),
         Siding("Battersea Pier C.H.S.", "BATRPHS",
                [("BATTERSEA PIER NO 1 SIDING", "S1"), ("BATTERSEA PIER NO 2 SIDING", "S2")])],
        label_col=1, text_col=3, siding_text_col=5, siding_merge=(1, 4), siding_text_to=10,
        gap_before_sidings=1, gap_between_sidings=1, sunday="SUN"),
    "london bridge": Layout("London Bridge", [str(p) for p in range(10, 16)], tlk=True, joiner=" & "),
    "brighton": Layout(
        "Brighton", [str(p) for p in range(1, 9)],
        [Siding("Brighton Wall Siding", "BRGHWS", [("Wall Sdg Rec", "REC"), ("Wall Sdg 2", "S2")])],
        label_col=2, text_col=4, siding_text_col=4, gap_before_sidings=2),
}


def station_layout(model_title: str, existing: Sequence[str] = (), seen: Sequence[str] = ()) -> Layout:
    """The built-in layout of the station named on the tab, else one made from the platforms found."""
    key = " ".join(str(model_title or "").casefold().replace("london victoria", "victoria").split())
    for name, lay in LAYOUTS.items():
        if key.startswith(name):
            return lay
    plats = sorted({m.group(1) for t in existing for m in [re.match(r"platform\s+(\d+)", t, re.I)] if m}
                   or set(seen), key=lambda p: int(p))
    return Layout(model_title or "Station", plats)


# --------------------------------------------------------------------------- reading the trains
def _plat(text: str) -> str:
    m = re.match(r"\s*(\d+)", text or "")
    return m.group(1) if m else ""


def _cars(text: str) -> int:
    m = re.search(r"\d+", text or "")
    return int(m.group(0)) if m else 0


def _cls(text: str) -> str:
    return re.sub(r"[()\s]", "", text or "")


def _tt(text: str) -> str:
    """Time as written in the section: passenger times 'HH MM', empty moves 'HH+MM'."""
    t = (text or "").strip()
    m = re.match(r"^(\d{1,2})\.(\d{2})(.*)$", t)
    return f"{int(m.group(1)):02d} {m.group(2)}{m.group(3)}" if m else t


def _minutes(text: str) -> int:
    n = time_minutes(text or "")
    if n is None:
        return 0
    return n + (1440 if "+1" in (text or "").replace(" ", "")[5:] else 0)


@dataclass
class Unit:
    cars: int
    cls: str
    op: str
    time: str = ""        # departure time of the train it works next ('05.50')
    day: int = -1         # the day that train runs
    minutes: int = 0
    rp: bool = False
    source: str = ""


def _next_working(text: str) -> Optional[Tuple[str, int]]:
    m = _NEXT.match((text or "").strip())
    if not m:
        return None
    day = _CODE_DAY.get((m.group(4) or "").upper())
    if day is None:
        return None
    return f"{int(m.group(1)):02d}{m.group(2)}{m.group(3)}", day


def _effective_from(b: Block) -> List[Tuple[str, str]]:
    """(from, departure) of each unit row; a row that leaves them blank works with the row above."""
    out, cur = [], ("", "")
    for u in b.units:
        f = (u.raw.get("from") or "").strip()
        if f:
            cur = (" ".join(f.split()).casefold(), u.raw.get("dep") or "")
        out.append(cur)
    return out


def platform_units(sm: SheetModel) -> Tuple[Dict[Tuple[str, str, str, str, int], int], List[str]]:
    """{(platform, class, operator, time, day): cars} berthed at the platforms on this tab, and problems."""
    out: Dict[Tuple[str, str, str, str, int], int] = defaultdict(int)
    problems: List[str] = []
    for b in sm.blocks:
        if not b.is_berth:
            continue
        plat = _plat(b.raw.get("plat", ""))
        by_row = {r: _next_working(d) for r, _k, d in b.nw}
        only = next(iter(by_row.values())) if len(by_row) == 1 else None
        for u in b.units:
            nxt = by_row.get(u.row, only)
            if not plat or nxt is None or not u.cars:
                problems.append(f"{sm.title.strip()}: a berthed unit ({b.raw.get('dest', '')}) has no platform, "
                                "cars or next working and is left out - check it")
                continue
            out[(plat, _cls(u.raw.get("unit", "")), (u.raw.get("op") or b.raw.get("op") or "").upper(),
                 nxt[0], nxt[1])] += _cars(u.raw.get("cars", ""))
    return out, problems


def berth_departures(sm: SheetModel) -> Dict[Tuple[str, str], List[Tuple[int, str, str, bool, str]]]:
    """{(platform, time 'HH.MM'): [(cars, class, operator, rear portion, train)]}: trains that leave a platform
    with a unit that was berthed there."""
    out: Dict[Tuple[str, str], List[Tuple[int, str, str, bool, str]]] = defaultdict(list)
    for b in sm.blocks:
        if b.is_berth:
            continue
        eff = _effective_from(b)
        berthed = [i for i, (f, _d) in enumerate(eff) if f == "berth"]
        if not berthed:
            continue
        rear = eff[0][0] != "berth"
        by: Dict[Tuple[str, str], int] = defaultdict(int)
        for i in berthed:
            u = b.units[i]
            by[(_cls(u.raw.get("unit", "")), (u.raw.get("op") or b.raw.get("op") or "").upper())] += _cars(
                u.raw.get("cars", ""))
        for (cls, op), cars in by.items():
            out[(_plat(b.raw.get("plat", "")), b.raw.get("time", ""))].append(
                (cars, cls, op, rear, (b.raw.get("id") or b.base_id).upper()))
    return out


@dataclass
class Move:
    """A move into ('arr') or out of ('dep') a siding."""
    minutes: int
    kind: str
    siding: int
    cls: str
    op: str
    cars: int
    time: str


def siding_events(sm: SheetModel, locations: Dict[str, int]) -> List[Move]:
    """The moves into and out of the sidings on this tab, in time order."""
    out: List[Move] = []
    for b in sm.blocks:
        if b.is_berth:
            continue
        dest = " ".join((b.raw.get("dest") or "").split()).casefold()
        if dest in locations:
            for u in b.units:
                if u.portion or not u.cars:
                    continue
                out.append(Move(_minutes(b.raw.get("time", "")), "arr", locations[dest], _cls(u.raw.get("unit", "")),
                                (u.raw.get("op") or b.raw.get("op") or "").upper(), _cars(u.raw.get("cars", "")),
                                b.raw.get("time", "")))
        for u, (frm, dep) in zip(b.units, _effective_from(b)):
            if frm in locations and u.cars:
                out.append(Move(_minutes(dep), "dep", locations[frm], _cls(u.raw.get("unit", "")),
                                (u.raw.get("op") or b.raw.get("op") or "").upper(), _cars(u.raw.get("cars", "")),
                                dep))
    out.sort(key=lambda e: (e.minutes, e.kind == "arr"))
    return out


# --------------------------------------------------------------------------- the section's content
def _text(lay: Layout, cars: int, cls: str, op: str, time: str, day: int, rp: bool) -> str:
    code = lay.sunday if day == 6 else DAY_CODES[day]
    label = f"{cls} TLK" if lay.tlk and op == "TLK" else cls
    return f"{cars} {label} for {'RP ' if rp else ''}{_tt(time)} {code}"


def _join(lay: Layout, units: List[Unit]) -> str:
    if not units:
        return "EMPTY"
    merged: Dict[Tuple[str, str, str, int, bool], Unit] = {}
    for u in units:
        k = (u.cls, u.op, u.time, u.day, u.rp)
        if k in merged:
            merged[k].cars += u.cars
        else:
            merged[k] = Unit(u.cars, u.cls, u.op, u.time, u.day, u.minutes, u.rp, u.source)
    ordered = sorted(merged.values(), key=lambda u: (u.minutes, u.cls), reverse=True)
    return lay.joiner.join(_text(lay, u.cars, u.cls, u.op, u.time, u.day, u.rp) for u in ordered)


def _stamp(day_from: int, nxt: int, minutes: int) -> int:
    """Sort key of a departure: how long after the start of `day_from` it is."""
    return ((nxt - day_from) % 7) * 2880 + minutes


def day_tabs(model: CWNModel) -> Dict[int, SheetModel]:
    """{day: tab} of the workings' day tabs, named 'MO' ... 'SuO' with or without a date after the code."""
    tabs: Dict[int, SheetModel] = {}
    for k, sm in model.sheets.items():
        d = tab_day(k)
        if d is not None:
            tabs.setdefault(d, sm)
    return tabs


def build_sections(model: CWNModel, lay: Layout, roads: Optional[Dict[Tuple[int, int, str, int, int], int]] = None,
                   log: Log = lambda _m: None) -> Dict[int, List[Tuple[str, str]]]:
    """{day: [(label, text), ...]} for each day tab of the workings (the lines of its section, in order)."""
    tabs = day_tabs(model)
    if not tabs:
        raise WorkingsError("No day tabs (MO, TO, WO, ThO, FO, SO, SuO) were found in these platform workings.")
    platform_by_day, departs = {}, {}
    for d, sm in tabs.items():
        got, problems = platform_units(sm)
        platform_by_day[d] = got
        departs[d] = berth_departures(sm)
        for p in problems:
            log("CHECK: " + p)

    # platforms: the berth lines, checked against the train that leaves on the next day's tab
    units_at: Dict[int, Dict[str, List[Unit]]] = {d: defaultdict(list) for d in tabs}
    for d, got in platform_by_day.items():
        for (plat, cls, op, time, nd), cars in got.items():
            u = Unit(cars, cls, op, time, nd, _stamp(d, nd, _minutes(time)))
            nxt = tabs.get(nd)
            if nxt is None:
                log(f"CHECK: {DAY_NAMES[d]} platform {plat}: {cars} {cls} for {_tt(time)} {DAY_CODES[nd]}, but "
                    f"the {DAY_CODES[nd]} tab is not in these workings, so it could not be checked")
            else:
                found = departs[nd].get((plat, time), [])
                found = [f for f in found if f[1] == cls]
                if found:
                    u.rp = any(f[3] for f in found)
                    there = sum(f[0] for f in found)
                    if there != cars:
                        log(f"CHECK: {DAY_NAMES[d]} platform {plat}: {cars} {cls} berthed for {_tt(time)} "
                            f"{DAY_CODES[nd]}, but {there} leave on that train ({found[0][4]})")
                else:
                    anywhere = [(p, f) for (p, t), fs in departs[nd].items() if t == time for f in fs if f[1] == cls]
                    if anywhere:
                        log(f"CHECK: {DAY_NAMES[d]} platform {plat}: the {_tt(time)} {DAY_CODES[nd]} train "
                            f"({anywhere[0][1][4]}) leaves from platform {anywhere[0][0]}, not {plat}")
                    else:
                        log(f"CHECK: {DAY_NAMES[d]} platform {plat}: no train leaves a berth at {_tt(time)} on "
                            f"{DAY_CODES[nd]}")
            units_at[d][plat].append(u)
    for nd, deps in departs.items():           # units berthed for more than a night are on the tab before only
        d = (nd - 1) % 7
        if d not in tabs:
            continue
        for (plat, time), fs in deps.items():
            for cars, cls, op, rear, train in fs:
                have = [u for u in units_at[d].get(plat, []) if u.time == time and u.day == nd and u.cls == cls]
                if not have and cars:
                    units_at[d][plat].append(Unit(cars, cls, op, time, nd, _stamp(d, nd, _minutes(time)), rear,
                                                  "next day"))
                    log(f"NOTE: {DAY_NAMES[d]} platform {plat}: {cars} {cls} for {_tt(time)} {DAY_CODES[nd]} "
                        f"added from the {DAY_CODES[nd]} tab ({train} leaves a berth there)")

    # sidings: stock carried through the week, matched to the next trains out
    siding_lines = _siding_units(tabs, lay, roads, log)
    out: Dict[int, List[Tuple[str, str]]] = {}
    for d in tabs:
        rows: List[Tuple[str, str]] = []
        for p in lay.platforms:
            rows.append((f"Platform {p}", _join(lay, units_at[d].get(p, []))))
        for plat in sorted(set(units_at[d]) - set(lay.platforms), key=lambda p: int(p)):
            rows.append((f"Platform {plat}", _join(lay, units_at[d][plat])))
            log(f"NOTE: {DAY_NAMES[d]} platform {plat} is not in the {lay.name} layout; it is added at the end of "
                "the platforms")
        for lab, text in siding_lines.get(d, []):
            rows.append((lab, text))
        out[d] = rows
    return out


def _siding_units(tabs: Dict[int, SheetModel], lay: Layout, roads, log: Log) -> Dict[int, List[Tuple[str, str]]]:
    if not lay.sidings:
        return {}
    locations = {" ".join(s.location.split()).casefold(): i for i, s in enumerate(lay.sidings)}
    events = {d: siding_events(sm, locations) for d, sm in tabs.items()}
    result: Dict[int, List[Tuple[str, str]]] = defaultdict(list)
    order = [d for d in range(7) if d in tabs]
    for si, siding in enumerate(lay.sidings):
        classes = {(e.cls, e.op) for d in order for e in events[d] if e.siding == si}
        end_stock: Dict[int, Dict[Tuple[str, str], int]] = {d: {} for d in order}
        for key in classes:
            flow, run, low = [], 0, 0
            for d in order:
                for e in events[d]:
                    if e.siding == si and (e.cls, e.op) == key:
                        run += e.cars if e.kind == "arr" else -e.cars
                        low = min(low, run)
                flow.append(run)
            if run != 0:
                log(f"CHECK: {siding.location}: {key[0]} cars arriving and leaving over the week differ by {run}; "
                    "the siding lines may be wrong - check them")
            for d, r in zip(order, flow):
                end_stock[d][key] = r - low
        for d in order:
            groups = _next_out(d, events, end_stock[d], si)
            result[d].extend(_assign_roads(d, siding, groups, roads, lay, log))
    return result


def _next_out(d: int, events: Dict[int, List[Move]], stock: Dict[Tuple[str, str], int], si: int) -> List[Unit]:
    """The units standing in the siding at the end of day d, each with the first train that takes it out."""
    groups: List[Unit] = []
    for key, cars in stock.items():
        if cars <= 0:
            continue
        queue = [[cars, True]]                        # [cars, stood there since before the end of day d]
        for k in range(1, 8):
            x = (d + k) % 7
            for e in events.get(x, []):
                if e.siding != si or (e.cls, e.op) != key:
                    continue
                if e.kind == "arr":
                    queue.append([e.cars, False])
                    continue
                n = e.cars
                while n and queue:
                    take = min(n, queue[0][0])
                    if queue[0][1]:
                        groups.append(Unit(take, key[0], key[1], e.time, x, _stamp(d, x, e.minutes)))
                    queue[0][0] -= take
                    n -= take
                    if queue[0][0] == 0:
                        queue.pop(0)
            if not any(q[1] for q in queue):
                break
        if any(q[1] for q in queue):
            log_left = sum(q[0] for q in queue if q[1])
            groups.append(Unit(log_left, key[0], key[1], "", d, 0, False, "no train"))
    return groups


def _assign_roads(d: int, siding: Siding, groups: List[Unit], roads, lay: Layout, log: Log) -> List[Tuple[str, str]]:
    by_road: Dict[int, List[Unit]] = defaultdict(list)
    one: Dict[Tuple[str, str, str, int, str], Unit] = {}          # units leaving on the same train stand together
    for u in groups:
        k = (u.cls, u.op, u.time, u.day, u.source)
        if k in one:
            one[k].cars += u.cars
        else:
            one[k] = Unit(u.cars, u.cls, u.op, u.time, u.day, u.minutes, u.rp, u.source)
    for i, u in enumerate(sorted(one.values(), key=lambda u: u.minutes)):
        if u.source == "no train":
            log(f"CHECK: {DAY_NAMES[d]} {siding.location}: {u.cars} {u.cls} stand there at the end of the day but "
                "no train takes them out within the week")
            continue
        road = roads.get((d, u.day, u.cls.split("/")[0], u.minutes % 1440, 0)) if roads else None
        if road is None:
            road = min(i, len(siding.roads) - 1)
            log(f"CHECK: {DAY_NAMES[d]} {siding.location}: {u.cars} {u.cls} for {_tt(u.time)} {DAY_CODES[u.day]} "
                f"is put on {siding.roads[road][0]} - check the road"
                + ("" if roads is None else " (the XML does not give it)"))
        by_road[road].append(u)
    return [(label, _join(lay, by_road.get(i, []))) for i, (label, _code) in enumerate(siding.roads)]


def roads_from_xml(paths: Sequence[str], lay: Layout, log: Log) -> Dict[Tuple[int, int, str, int, int], int]:
    """{(day, next day, class, minutes of the departure, 0): road index}: which siding road each unit stands on,
    from the Attune XML's overnight stays."""
    from rstools.berthing.stays import build
    from rstools.berthing.xmlread import BerthingError, read_xml
    xmls = []
    for i, p in enumerate(paths):
        log(f"Reading {os.path.basename(p)}")
        try:
            xmls.append(read_xml(p, i))
        except BerthingError as exc:
            raise WorkingsError(str(exc))
    berthing = build(xmls)
    found: Dict[Tuple[int, int, str, int, int], int] = {}
    for s in berthing.stays:
        for siding in lay.sidings:
            if s.loc != siding.tiploc or s.depart is None:
                continue
            code = next((i for i, (_l, c) in enumerate(siding.roads) if s.plat.upper().startswith(c)), None)
            if code is None:
                continue
            for k in range(s.nights):
                found.setdefault(((s.first_night + k) % 7, s.depart.day, s.fleet.split("/")[0],
                                  (s.depart.time // 60) % 1440, 0), code)
    return found


# --------------------------------------------------------------------------- writing
def _section_rows(lay: Layout, lines: List[Tuple[str, str]]) -> int:
    """How many rows a section takes: the heading, its lines and the gaps before and between sidings."""
    road_of = {label: ri for sid in lay.sidings for ri, (label, _c) in enumerate(sid.roads)}
    rows, seen = 1, False
    for label, _text in lines:
        rows += 1
        if label in road_of:
            rows += lay.gap_between_sidings if seen and road_of[label] == 0 else (0 if seen else lay.gap_before_sidings)
            seen = True
    return rows


def _write(ws, sm: SheetModel, lay: Layout, day: int, lines: List[Tuple[str, str]], log: Log) -> int:
    """Write one tab's section in place of the one it has (if any). Returns the number of lines that differ
    from the old section."""
    from openpyxl.styles import Alignment, Font
    last = max((b.end_row for b in sm.blocks), default=sm.header_row)
    old = {e["label"].casefold(): e["text"] for e in sm.footer}
    start = sm.footer[0]["r"] if sm.footer else last + 4
    end = sm.footer[-1]["r"] if sm.footer else start - 1
    width = max(sm.max_col, 12)
    for m in [m for m in ws.merged_cells.ranges if start <= m.min_row <= end]:
        ws.unmerge_cells(str(m))               # only the old section's own merged cells
    for r in range(start, end + 1):
        for c in range(1, width + 1):
            ws.cell(row=r, column=c).value = None
    need = _section_rows(lay, lines)
    below = next((r for r in range(end + 1, ws.max_row + 1)
                  if any(ws.cell(row=r, column=c).value not in (None, "") for c in range(1, width + 1))), None)
    if below is not None and start + need > below:    # never write over what follows the section
        more = start + need - below + 1
        ws.insert_rows(below, more)
        for m in list(ws.merged_cells.ranges):
            if m.min_row >= below:
                m.shift(0, more)
    base = ws.cell(row=sm.blocks[0].start_row if sm.blocks else sm.header_row + 1, column=1).font
    size = base.sz or 11
    bold = Font(name="Arial", size=size, bold=True)
    title = Font(name="Arial", size=size, bold=True, underline="single")
    top = Alignment(vertical="top")
    r = start
    c = ws.cell(row=r, column=lay.label_col, value=f"{DAY_NAMES[day]} Berthing Arrangements:-")
    c.font, c.alignment = title, top
    differ = 0
    road_of = {label: (si, ri) for si, sid in enumerate(lay.sidings) for ri, (label, _c) in enumerate(sid.roads)}
    seen_siding = False
    for label, text in lines:
        r += 1
        siding = label in road_of
        if siding:
            si, ri = road_of[label]
            if not seen_siding:
                r += lay.gap_before_sidings
            elif ri == 0:
                r += lay.gap_between_sidings
            seen_siding = True
        tc = lay.siding_text_col if siding else lay.text_col
        a = ws.cell(row=r, column=lay.label_col, value=clean_cell(label))
        b = ws.cell(row=r, column=tc, value=clean_cell(text))
        for cell in (a, b):
            cell.font, cell.alignment = bold, top
        if siding and lay.siding_merge:
            ws.merge_cells(start_row=r, start_column=lay.siding_merge[0], end_row=r, end_column=lay.siding_merge[1])
            ws.merge_cells(start_row=r, start_column=tc, end_row=r, end_column=lay.siding_text_to or tc)
        if sm.footer:
            was = old.get(label.casefold())
            if was is not None and " ".join(was.split()).casefold() != " ".join(text.split()).casefold():
                differ += 1
                log(f"DIFFERENT: {DAY_NAMES[day]} {label}: was '{was}', now '{text}'")
    return differ


def add_berthing(path: str, xml_paths: Sequence[str] = (), out_dir: str = "", name: str = "",
                 log: Log = lambda _m: None):
    """Save a copy of the platform workings with each day's berthing arrangements made from its trains."""
    from rstools.berthing.engine import Result
    from .loader import LoadError, load_any
    from .xlsxfix import save_workbook
    if not path or not os.path.isfile(path):
        raise WorkingsError(f"This file could not be found:\n{path}")
    for x in xml_paths:
        if not os.path.isfile(x):
            raise WorkingsError(f"This file could not be found:\n{x}")
    log(f"Reading {os.path.basename(path)}")
    try:
        wb = load_any(path)
    except (LoadError, OSError) as exc:
        raise WorkingsError(str(exc))
    try:
        model = parse_workbook(wb)
    except Exception as exc:                   # an unexpected layout: a message, not a traceback
        raise WorkingsError(f"{os.path.basename(path)} could not be read as platform workings ({exc}).")
    tabs = day_tabs(model)
    if not tabs:
        raise WorkingsError("No platform workings day tabs (MO, TO, WO, ThO, FO, SO, SuO) were found in "
                            f"{os.path.basename(path)}.")
    first = next(iter(tabs.values()))
    seen = sorted({_plat(b.raw.get("plat", "")) for sm in tabs.values() for b in sm.blocks if b.is_berth} - {""})
    lay = station_layout(str(wb[first.title]["A1"].value or ""), [e["label"] for e in first.footer], seen)
    log(f"Station: {lay.name}")
    roads = roads_from_xml(xml_paths, lay, log) if (xml_paths and lay.sidings) else None
    if xml_paths and not lay.sidings:
        log(f"NOTE: {lay.name} has no sidings in its section, so the XML is not needed")
    sections = build_sections(model, lay, roads, log)
    diffs = 0
    for day, sm in tabs.items():
        diffs += _write(wb[sm.title], sm, lay, day, sections[day], log)
    folder = output_folder(out_dir)
    stem = naming.clip(name or f"{os.path.splitext(os.path.basename(path))[0]} (berthing added)")
    stem = unique_stem(folder, stem)
    out = os.path.join(folder, stem + ".xlsx")
    from rstools.fsutil import save_output
    save_output(lambda: save_workbook(wb, out, trim="data"), out, WorkingsError)
    summary = (f"Berthing arrangements added to {len(sections)} day tab(s) of the {lay.name} workings"
               + (f"; {diffs} line(s) differ from the section that was there (see the log)." if diffs else "."))
    log(f"Saved: {out}")
    return Result(out, "", summary, [])
