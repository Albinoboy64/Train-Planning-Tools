"""Reader for the Attune rolling-stock diagram XML ('diagramExchange', Tracsis TTVP interface).

Only the parts the stats pack needs are kept: trains (legs with times, public times,
platforms and stop/pass flags), location names and unit diagrams (for day checks).
Plan types: 'L' (LTP), 'S' (STP) and drafts (other plan types, or provisional="true") are all
read; where versions overlap, STP is used before a draft, and a draft before LTP.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from rstools.attune_xml import secs
from rstools.days import days_of_mask


class AttuneError(Exception):
    pass




@dataclass
class Leg:
    origin: str
    dep: int
    dest: str
    arr: int
    dep_pub: Optional[int]
    arr_pub: Optional[int]
    origin_stop: bool          # False when the train passes the origin of this leg
    dest_stop: bool
    origin_pass_kind: str      # '', 'P' (pass) or 'N' (non-passenger / operational stop)
    dest_pass_kind: str


@dataclass
class Train:
    id: str
    days: Set[int]
    plan: str
    legs: List[Leg] = field(default_factory=list)


@dataclass
class UnitDiagram:
    """An Attune unit diagram: its depot / number, days, end-of-diagram notes (the next-day
    working, e.g. 'BI20 04+29ThO (F)', or 'Stabld') and its WASH / CET / FUEL activities."""
    depot: str
    number: str
    days: Set[int]
    notes: List[str] = field(default_factory=list)
    activities: Dict[str, int] = field(default_factory=dict)
    plan: str = ""              # 'L' (LTP) / 'S' (STP): an XML can hold both versions of a diagram for a day

    @property
    def key(self) -> str:
        return f"{self.depot}{self.number}"


@dataclass
class AttuneData:
    path: str
    plan: str
    start: str
    end: str
    locations: Dict[str, str]
    trains: Dict[str, List[Train]]          # headcode -> versions (LTP/STP, different days)
    diagram_days: Set[int]
    warnings: List[str]
    unit_diagrams: List[UnitDiagram] = field(default_factory=list)

    def days(self) -> Set[int]:
        if self.diagram_days:
            return set(self.diagram_days)
        out = set()
        for versions in self.trains.values():
            for t in versions:
                out |= t.days
        return out


def parse_attune_xml(path: str) -> AttuneData:
    from rstools import attune_xml as AX
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    warnings: List[str] = []
    locations: Dict[str, str] = {}
    trains: Dict[str, List[Train]] = defaultdict(list)
    diagram_days: Set[int] = set()
    meta = {}
    cur_train: Optional[Train] = None
    units: List[UnitDiagram] = []
    reader = AX.UnitDiagramParser()         # the unit diagrams, read as every Attune reader reads them
    try:
        for event, tag, el in AX.walk(path):
            raw = reader.feed(event, tag, el)
            if raw is not None:
                days = days_of_mask(raw.days_mask)
                diagram_days |= days
                units.append(UnitDiagram(raw.depot, raw.number, days, list(raw.notes),
                                         {a: n for a, n in raw.activities.items() if a in ("WASH", "CET", "FUEL")},
                                         plan=raw.type))
                continue
            if reader.inside:
                continue
            if event == "start":
                if tag == "diagramExchange":
                    meta = dict(el.attrib)
                elif tag == "train":
                    a = el.attrib
                    cur_train = Train(id=a.get("id", ""), days=days_of_mask(a.get("daysRun", "")),
                                      plan=AX.plan_type(a))
                continue
            # end events
            if tag == "leg" and cur_train is not None:
                a = el.attrib
                dep, arr = secs(a.get("dep")), secs(a.get("arr"))
                if dep is None or arr is None:
                    warnings.append(f"Train {cur_train.id}: a leg without times was ignored.")
                else:
                    ok, dk = a.get("depStopType", ""), a.get("arrStopType", "")
                    cur_train.legs.append(Leg(
                        origin=a.get("origin", ""), dep=dep, dest=a.get("dest", ""), arr=arr,
                        dep_pub=secs(a.get("depPub")), arr_pub=secs(a.get("arrPub")),
                        origin_stop=ok != "P", dest_stop=dk != "P", origin_pass_kind=ok, dest_pass_kind=dk))
                el.clear()
            elif tag == "train" and cur_train is not None:
                if cur_train.legs:
                    _unroll(cur_train)
                    trains[cur_train.id].append(cur_train)
                else:
                    warnings.append(f"Train {cur_train.id} has no legs and was ignored.")
                cur_train = None
                el.clear()
            elif tag == "location":
                loc = AX.location(el)
                if loc:
                    locations[loc[0]] = loc[1]
                el.clear()
    except ET.ParseError as exc:
        raise AttuneError(f"The XML file could not be read ({exc}). Check it is a complete Attune export.")
    except OSError as exc:
        raise AttuneError(f"The XML file could not be opened: {exc}")
    if not meta:
        raise AttuneError("This is not an Attune diagram XML (no <diagramExchange> element found).")
    if not trains:
        raise AttuneError("The XML file contains no trains.")
    return AttuneData(path=path, plan=meta.get("plantype", ""), start=meta.get("startdate", ""),
                      end=meta.get("enddate", ""), locations=locations, trains=dict(trains),
                      diagram_days=diagram_days, warnings=warnings, unit_diagrams=units)


def _unroll(t: Train):
    """Leg times after midnight continue past 24:00 so they always increase."""
    last = None
    for leg in t.legs:
        for attr in ("dep", "dep_pub", "arr", "arr_pub"):
            v = getattr(leg, attr)
            if v is None:
                continue
            while last is not None and v < last - 6 * 3600:
                v += 86400
            setattr(leg, attr, v)
            if attr in ("dep", "arr"):
                last = v
