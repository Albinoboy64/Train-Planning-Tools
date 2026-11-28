"""The parts of an Attune diagram XML a berthing chart needs: every train version (by its trainKey) with the
platform at each call, and every unit diagram with its moves, coupled units and end-of-diagram notes (the
next-day working, e.g. 'BI8 05+03TO (R)')."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from rstools.days import days_of_mask
from rstools.stationbook import Call, _calls, _unroll


class BerthingError(Exception):
    pass


@dataclass
class Move:
    train: str                  # headcode, e.g. '5H73BV'
    key: str                    # the train version's trainKey (unique within one XML)
    origin: str
    dest: str
    dep: int                    # seconds from the diagram day's midnight (past 24:00 after midnight)
    arr: int
    coupled: List[str]          # every unit on the move, front first, own diagram included ([] alone)


@dataclass
class UnitDiagram:
    key: str                    # depot + number, e.g. 'BI19'
    fleet: str                  # e.g. '387/3', 'MAINT'
    days: Set[int]              # 0 = Monday
    plan: str                   # 'L', 'S', 'D'...
    source: int                 # which XML it came from (0 = the first given)
    moves: List[Move] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    static_loc: str = ""        # where the diagram ends (its last fixed activity)


@dataclass
class TrainVersion:
    id: str
    key: str
    plan: str
    days: Set[int]
    calls: List[Call]


@dataclass
class BerthXML:
    path: str
    start: str                  # the export's date range, 'yyyy-mm-dd'
    end: str
    locations: Dict[str, str]
    trains: Dict[str, TrainVersion]
    diagrams: List[UnitDiagram]


def read_xml(path: str, source: int = 0) -> BerthXML:
    """Read one Attune XML. Raises BerthingError with a plain message for a file that cannot be used."""
    import os

    from rstools import attune_xml as AX
    name = os.path.basename(path)
    locations: Dict[str, str] = {}
    trains: Dict[str, TrainVersion] = {}
    diagrams: List[UnitDiagram] = []
    meta: dict = {}
    cur_train: Optional[dict] = None
    legs: List[dict] = []
    units = AX.UnitDiagramParser()          # the unit diagrams, read as every Attune reader reads them
    try:
        for event, tag, el in AX.walk(path):
            raw = units.feed(event, tag, el)
            if raw is not None:
                cur = UnitDiagram(raw.key, raw.fleet, days_of_mask(raw.days_mask), raw.type, source,
                                  notes=list(raw.static_notes), static_loc=raw.static_loc)
                cur.moves = [Move(m.train, m.key, m.origin, m.dest, m.dep, m.arr, m.coupled) for m in raw.moves
                             if m.dep is not None and m.arr is not None]
                times = _unroll([t for m in cur.moves for t in (m.dep, m.arr)])
                for i, m in enumerate(cur.moves):
                    m.dep, m.arr = int(times[2 * i] or 0), int(times[2 * i + 1] or 0)
                if cur.key and cur.days:
                    diagrams.append(cur)
                continue
            if units.inside:
                continue
            if event == "start":
                if tag == "diagramExchange":
                    meta = dict(el.attrib)
                elif tag == "train":
                    cur_train = {"id": el.get("id", ""), "key": el.get("trainKey", ""), "plan": AX.plan_type(el.attrib),
                                 "days": days_of_mask(el.get("daysRun", ""))}
                    legs = []
                continue
            # end events
            if tag == "leg" and cur_train is not None:
                legs.append(dict(el.attrib))
            elif tag == "train" and cur_train is not None:
                if legs and cur_train["key"]:
                    trains[cur_train["key"]] = TrainVersion(cur_train["id"], cur_train["key"], cur_train["plan"],
                                                            cur_train["days"], _calls(legs))
                cur_train = None
                el.clear()
            elif tag == "location":
                loc = AX.location(el)
                if loc:
                    locations[loc[0]] = loc[1]
                el.clear()
    except ET.ParseError as exc:
        raise BerthingError(f"'{name}' could not be read as XML ({exc}). Check it is a complete Attune export.")
    except OSError as exc:
        raise BerthingError(f"'{name}' could not be opened: {exc}")
    if not meta:
        raise BerthingError(f"'{name}' is not an Attune diagram XML.")
    if not diagrams:
        raise BerthingError(f"'{name}' has no unit diagrams, so it cannot show where units berth. Export the XML "
                            "with its unit diagrams.")
    if not trains:
        raise BerthingError(f"'{name}' has no trains, so the platforms units berth at cannot be found. Export the "
                            "XML with its trains as well as its unit diagrams.")
    return BerthXML(path, meta.get("startdate", ""), meta.get("enddate", ""), locations, trains, diagrams)


def platform(train: Optional[TrainVersion], loc: str, arriving: bool) -> str:
    """The platform (or siding road) a train uses at a location: the last call there when arriving, the first
    when departing. '' if the XML does not give one."""
    if train is None:
        return ""
    calls = [c for c in train.calls if c.loc == loc]
    if not calls:
        return ""
    return (calls[-1] if arriving else calls[0]).plat or ""
