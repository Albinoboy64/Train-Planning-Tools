"""The parts of an Attune diagram XML a berthing chart needs: every train version (by its trainKey) with the
platform at each call, and every unit diagram with its moves, coupled units and end-of-diagram notes (the
next-day working, e.g. 'BI8 05+03TO (R)')."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from rstools.stationbook import Call, _calls, _days, _secs, _unroll


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
    from rstools.fsutil import long_path
    import os
    name = os.path.basename(path)
    locations: Dict[str, str] = {}
    trains: Dict[str, TrainVersion] = {}
    diagrams: List[UnitDiagram] = []
    meta: dict = {}
    cur_train: Optional[dict] = None
    legs: List[dict] = []
    cur: Optional[UnitDiagram] = None
    depot = number = ""
    move: Optional[dict] = None
    coupled: List[Tuple[int, str]] = []
    cpos: Optional[int] = None
    cdepot = cnum = ""
    in_static = False
    try:
        for event, el in ET.iterparse(long_path(path), events=("start", "end")):
            tag = el.tag.rsplit("}", 1)[-1]
            if event == "start":
                if tag == "diagramExchange":
                    meta = dict(el.attrib)
                elif tag == "train":
                    plan = el.get("planType", "")
                    if el.get("provisional", "").lower() == "true" and plan.upper() in ("", "L"):
                        plan = "D"                          # a draft (provisional) version of an LTP train
                    cur_train = {"id": el.get("id", ""), "key": el.get("trainKey", ""), "plan": plan,
                                 "days": _days(el.get("daysRun", ""))}
                    legs = []
                elif tag == "unitDiagram":
                    cur = UnitDiagram("", "", _days(el.get("daysrun", "")), el.get("type", ""), source)
                    number, depot = el.get("id", "").strip(), ""
                elif tag == "journey" and cur is not None:
                    move = dict(el.attrib)
                    move["train"] = move["key"] = ""
                    coupled = []
                elif tag == "coupled":
                    cpos, cdepot, cnum = int(el.get("position", "0") or 0), "", ""
                elif tag == "diagStatic" and cur is not None:
                    in_static = True
                    cur.static_loc = el.get("loc", "") or cur.static_loc
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
                locations[el.get("tiploc", "")] = el.get("longDesc") or el.get("shortDesc") or el.get("tiploc", "")
                el.clear()
            elif cur is not None:
                if tag == "depot":
                    if cpos is not None:
                        cdepot = el.get("id", "").strip()
                    elif not depot:
                        depot = el.get("id", "").strip()
                elif tag == "res" and not cur.fleet:
                    cur.fleet = el.get("id", "").strip()
                elif tag == "diagram" and cpos is not None:
                    cnum = el.get("id", "").strip()
                elif tag == "coupled":
                    coupled.append((cpos or 0, cdepot + cnum))
                    cpos = None
                elif tag == "activity" and move is not None and el.get("trainid"):
                    move["train"], move["key"] = el.get("trainid", ""), el.get("trainKey", "")
                elif tag == "text" and in_static and el.text and el.text.strip():
                    cur.notes.append(el.text.strip())
                elif tag == "diagStatic":
                    in_static = False
                elif tag == "journey" and move is not None:
                    dep, arr = _secs(move.get("dep")), _secs(move.get("arr"))
                    if dep is not None and arr is not None:
                        cur.moves.append(Move(move["train"], move["key"], move.get("origin", ""),
                                              move.get("dest", ""), dep, arr, [k for _p, k in sorted(coupled)]))
                    move = None
                elif tag == "unitDiagram":
                    cur.key = depot + number
                    times = _unroll([t for m in cur.moves for t in (m.dep, m.arr)])
                    for i, m in enumerate(cur.moves):
                        m.dep, m.arr = int(times[2 * i] or 0), int(times[2 * i + 1] or 0)
                    if cur.key and cur.days:
                        diagrams.append(cur)
                    cur = None
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
