"""Putting the stays on a chart: each unit on its berth's rows, night by night, in the layout of a chosen chart.

Each row is one unit's stay: its arrival in the night's FINISH column and its departure in the next START
column, 'Berth' on any day in between. Units that arrive coupled sit on consecutive rows, front first, in
brackets, with the time on the first row; on each berth the latest arrival is at the top."""
from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .layout import NIGHTS, Block, Cell, DepotBlock, DepotSheet, GridSheet, Layout
from .mapping import ANY, Berth, Locations
from .stays import Berthing, End, Stay, Visit

GX_387 = "FF0000"               # Gatwick Express 387/2: red text
SN_387 = "00B050"               # Southern 387/3: green text
FLEET_COLOURS = {"387/2": GX_387, "387/3": SN_387}
STP_FILL = "E4DFEC"             # STP trains: bold on lavender (not one of the round colours)
OTHER_COLOUR = "7F7F7F"         # other operators' units: grey text
NIGHT_ORDER = [4, 5, 6, 0, 1, 2, 3]       # the chart starts with Friday night

# spelling slips copied forward in the old charts
TEXT_FIXES = {"ATTATCH": "ATTACH", "Attatch": "Attach", "FUTHER": "FURTHER", "1s a ": "is a "}


def fix_text(text: str) -> str:
    for old, new in TEXT_FIXES.items():
        text = text.replace(old, new)
    return text


@dataclass
class Fleet:
    """Car count, class and colour of a unit type, from the fleet table."""
    cars: Optional[int]
    cls: str
    colour: str
    suffix: str


class Units:
    def __init__(self, table=None):
        self.table = table
        self.unknown: Set[str] = set()

    def of(self, fleet: str) -> Fleet:
        if fleet.upper() == "MAINT" or not fleet:
            return Fleet(None, "MAINT", "", "")
        info = self.table.get(fleet) if self.table is not None else None
        if info is None or not info.cars:
            self.unknown.add(fleet)
        cls = fleet.split("/")[0]
        return Fleet(info.cars if info is not None else None, cls, FLEET_COLOURS.get(fleet, ""),
                     " TLK" if cls == "700" else "")

    def label(self, fleet: str, bracket: bool) -> str:
        f = self.of(fleet)
        unit = f"{f.cars} {f.cls}" if f.cars else f.cls
        return f"({unit})" if bracket else unit


def clock(sec: int, ecs: bool) -> str:
    """'02+02' for an empty move, '0500' for a passenger train (the CWN convention)."""
    from rstools.clock import clock as _clock
    return _clock(sec, "+" if ecs else "")


def _end_text(end: End) -> str:
    return ("RP" if end.rp else "") + clock(end.time, end.ecs)


@dataclass
class Placed:
    stay: Stay
    block: int                  # index in the sheet's blocks
    row: int


def _nights(stay: Stay) -> List[int]:
    return [(stay.first_night + i) % 7 for i in range(max(1, stay.nights))]


def _pairs(night: int) -> List[int]:
    """The column pairs that show a night (Friday is shown twice: first and last)."""
    return [p for p, n in enumerate(NIGHTS) if n == night]


def _formations(stays: Sequence[Stay]) -> List[List[Stay]]:
    """Stays grouped by the train they arrived on (coupled units together, front first)."""
    groups: Dict[Tuple, List[Stay]] = defaultdict(list)
    for s in stays:
        key = (s.arrive.group, s.first_night) if len(s.arrive.coupled) > 1 else (id(s),)
        groups[key].append(s)
    out = []
    for members in groups.values():
        order = members[0].arrive.coupled
        members.sort(key=lambda s: order.index(s.unit) if s.unit in order else len(order))
        out.append(members)
    out.sort(key=lambda g: (NIGHT_ORDER.index(g[0].first_night), -g[0].arrive.time, g[0].unit))
    return out


def place(layout: Layout, berthing: Berthing, locations: Locations, units: Units,
          warnings: List[str], fleets: Optional[Set[str]] = None) -> Layout:
    """A copy of the layout with every sheet filled from the stays (any units already on it are replaced).
    `fleets`: only units of these types (a TLGN chart); None for every type."""
    out = copy.deepcopy(layout)
    by_loc: Dict[str, List[Stay]] = defaultdict(list)
    charted = [s for s in berthing.stays if s.fleet.upper() != "MAINT"      # maintenance moves are not berthed
               and (fleets is None or s.fleet in fleets or s.other)]
    for s in charted:
        by_loc[s.loc].append(s)
    no_location = []
    placed_locs: Set[str] = set()
    for sheet in out.sheets:
        if isinstance(sheet, DepotSheet):
            _fill_depot(sheet, locations, berthing, units, warnings)
            continue
        berths: List[Optional[Berth]] = [locations.berth(sheet.name, b.label) for b in sheet.blocks]
        no_location += [f"{sheet.name}: {b.label}" for b, br in zip(sheet.blocks, berths)
                        if br is None or not br.tiploc]
        for blk in sheet.blocks:
            blk.units = {}
        tiplocs = {br.tiploc for br in berths if br is not None and br.tiploc}
        placed_locs |= tiplocs
        pools: Dict[Tuple[str, Tuple[str, ...]], List[int]] = defaultdict(list)
        for i, br in enumerate(berths):
            if br is not None and br.tiploc:
                pools[(br.tiploc, br.codes)].append(i)
        wanted: Dict[Tuple[str, Tuple[str, ...]], List[Stay]] = defaultdict(list)
        other: Dict[Tuple[str, str], List[Stay]] = defaultdict(list)
        for loc in sorted(tiplocs):
            for s in by_loc.get(loc, []):
                exact = [k for k in pools if k[0] == loc and ANY not in k[1] and s.plat in k[1]]
                wild = [k for k in pools if k[0] == loc and ANY in k[1]]
                roads = [k for k in pools if k[0] == loc]
                if exact or wild:
                    wanted[(exact or wild)[0]].append(s)
                elif not s.plat and roads:              # no road in the XML: the location's berths in turn
                    every = (loc, ("",))
                    pools[every] = sorted({i for k in roads for i in pools[k]})
                    wanted[every].append(s)
                else:
                    other[(loc, s.plat)].append(s)
        for key, stays in wanted.items():
            _assign(sheet, pools[key], stays, units)
        for (loc, plat), stays in sorted(other.items()):
            blk = Block(f"Other - {loc} {'platform/road ' + plat if plat else '(no platform)'}",
                        section=max([b.section for b in sheet.blocks] + [-1]) + 1)   # its own place, at the bottom
            sheet.blocks.append(blk)
            sheet.sections = list(sheet.sections) + [blk.label]
            _assign(sheet, [len(sheet.blocks) - 1], stays, units)
            warnings.append(f"{sheet.name}: {len(stays)} unit(s) berth at {loc} "
                            f"{'platform/road ' + plat if plat else 'with no platform in the XML'}, which is not a "
                            "berth on this sheet; they are listed at the bottom of the sheet. Add the berth to the "
                            "chart or to the berth list.")
    shown = [s for s in charted if s.loc in placed_locs]
    open_ended = sum(1 for s in shown if s.depart is None)
    if open_ended:
        warnings.append(f"{open_ended} unit(s) on the chart end a diagram without a next-day working in the XML "
                        "(e.g. 'Stabld'), so only their arrival is shown.")
    if no_location:
        warnings.append(f"{len(no_location)} berth(s) have no XML location in the berth list, so they are left "
                        f"empty (e.g. {', '.join(no_location[:5])}). Edit berth locations to add them.")
    if units.unknown:
        warnings.append("No car count in the fleet data for " + ", ".join(sorted(units.unknown)) + "; only the class "
                        "is shown. Add it in Settings > Fleet data.")
    return out


def _assign(sheet: GridSheet, blocks: List[int], stays: List[Stay], units: Units):
    """Give each unit a row on one of the berths (a pool shares rows when the XML gives no road)."""
    taken: Dict[Tuple[int, int], Set[int]] = defaultdict(set)      # (block, row) -> nights used
    placed: List[Placed] = []
    for members in _formations(stays):
        spans = [set(_nights(s)) for s in members]
        done = False
        for b in blocks:
            row = 0
            while not done and row < 400:
                if all(not (taken[(b, row + i)] & spans[i]) for i in range(len(members))):
                    for i, s in enumerate(members):
                        taken[(b, row + i)] |= spans[i]
                        placed.append(Placed(s, b, row + i))
                    done = True
                row += 1
            if done:
                break
    for p in placed:
        _write_stay(sheet.blocks[p.block], p, units, placed)


def _write_stay(blk: Block, p: Placed, units: Units, placed: List[Placed]):
    s = p.stay
    row = blk.units.setdefault(p.row, [None] * 16)
    blk.height = max(blk.height, p.row + 1)
    if s.other:
        colour, suffix = OTHER_COLOUR, ""
    else:
        colour, suffix = units.of(s.fleet).colour, units.of(s.fleet).suffix

    def unit(end: Optional[End], bracket: bool) -> str:
        """The unit type, or for another operator's train with none known, its headcode."""
        if s.by_headcode:
            return ((end or s.arrive).train or s.unit)[:4]
        return units.label(s.fleet, bracket)
    coupled_in = len(s.arrive.coupled) > 1
    # the time goes on the first row of a coupled group (the group's other units show the unit only)
    first_in = not coupled_in or not any(q.stay.arrive.group == s.arrive.group and q.block == p.block
                                         and q.stay.first_night == s.first_night and q.row < p.row for q in placed)
    d = s.depart
    coupled_out = d is not None and len(d.coupled) > 1
    first_out = d is None or not coupled_out or not any(
        q.stay.depart is not None and q.stay.depart.group == d.group and q.stay.depart.day == d.day
        and q.block == p.block and q.row < p.row for q in placed)
    nights = _nights(s)
    for n in nights:
        for pair in _pairs(n):
            fin, sta = 2 * pair, 2 * pair + 1
            if n == s.first_night:
                text = unit(s.arrive, coupled_in) + (f" {clock(s.arrive.time, s.arrive.ecs)}{suffix}"
                                                     if first_in else "")
                row[fin] = Cell(text, colour, s.arrive.stp, STP_FILL if s.arrive.stp else "")
            else:
                row[fin] = Cell(unit(s.arrive, coupled_in) + (" Berth" if first_in else ""), colour)
            if n == nights[-1]:
                # Friday night is shown twice (pairs 0 and 7): a stay that began before Saturday and leaves after
                # Friday night is shown leaving once, in the second Friday pair, not also in the week-opening one
                if d is not None and not (n == 4 and s.first_night != 4 and pair == 0):
                    text = unit(d, coupled_out) + (f" {_end_text(d)}{suffix}" if first_out else "")
                    row[sta] = Cell(text, colour, d.stp, STP_FILL if d.stp else "")
            else:
                row[sta] = Cell(unit(s.arrive, coupled_in) + (" Berth" if first_in else ""), colour)


def _depot_columns() -> List[Tuple[str, int]]:
    """What each of a depot sheet's 16 columns lists: ('finish', Friday), ('start', Saturday)..."""
    cols = []
    for n in NIGHTS:
        cols += [("finish", n), ("start", (n + 1) % 7)]
    return cols


def _matches(title: str, fleet: str, units: Units) -> bool:
    """A depot block title ('4 377', '4 387/2') takes units of that car count and class (and subclass)."""
    parts = title.split()
    if len(parts) != 2 or not fleet or fleet.upper() == "MAINT":
        return False
    cars, cls = parts
    f = units.of(fleet)
    if str(f.cars) != cars:
        return False
    return fleet == cls if "/" in cls else f.cls == cls


def _fill_depot(sheet: DepotSheet, locations: Locations, berthing: Berthing, units: Units, warnings: List[str]):
    berths = locations.sheet(sheet.name)
    loc = next((b.tiploc for b in berths.values() if b.tiploc), "")
    if not loc:
        warnings.append(f"{sheet.name}: no XML location in the berth list, so the depot sheet is left empty.")
        for blk in sheet.blocks:
            blk.cells = []
        return
    cols = _depot_columns()
    finishes, starts = berthing.finishes.get(loc, []), berthing.starts.get(loc, [])
    used: Set[int] = set()
    for blk in sheet.blocks:
        lists: List[List[Visit]] = []
        for kind, day in cols:
            src = finishes if kind == "finish" else starts
            lists.append(sorted((v for v in src if v.day == day and _matches(blk.title, v.fleet, units)),
                                key=lambda v: v.time))
        for v in finishes + starts:
            if _matches(blk.title, v.fleet, units):
                used.add(id(v))
        _depot_rows(blk, lists, units)
    rest = [v for v in finishes + starts if id(v) not in used and v.fleet.upper() != "MAINT"]
    if rest:
        kinds = sorted({v.fleet for v in rest})
        warnings.append(f"{sheet.name}: units of {', '.join(kinds)} also use the depot but have no block on the sheet; "
                        "they are listed in an 'Other units' block.")
        blk = DepotBlock("Other units")
        lists = []
        for kind, day in cols:
            src = finishes if kind == "finish" else starts
            lists.append(sorted((v for v in src if v.day == day and id(v) not in used and v.fleet.upper() != "MAINT"),
                                key=lambda v: v.time))
        _depot_rows(blk, lists, units, with_unit=True)
        sheet.blocks.append(blk)


def _depot_rows(blk: DepotBlock, lists: List[List[Visit]], units: Units, with_unit: bool = False):
    height = max([len(lst) for lst in lists] + [0])
    blk.cells = [[None] * 16 for _ in range(height)]
    for c, lst in enumerate(lists):
        for r, v in enumerate(lst):
            text = (units.label(v.fleet, False) + " " if with_unit else "") + clock(v.time, v.ecs)
            blk.cells[r][c] = Cell(text, units.of(v.fleet).colour, v.stp, STP_FILL if v.stp else "")
    blk.rows = max(blk.rows, height)
