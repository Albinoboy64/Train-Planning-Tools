"""Everything the track map view needs, read once: a page of a kept track map, the units standing at the place on a
day (from an Attune XML), which drawn track each platform or road is, and the cars of each fleet. The window asks
for the picture at a time (`View.at`) and draws it."""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .occupancy import END, Stand, place_locations, stands
from .pdfmap import MapPage, TrackMapError, load_map
from .scene import Road, Scene, match_roads, scene


@dataclass
class View:
    page: MapPage
    place: str
    day: int
    locations: Dict[str, str]           # TIPLOC -> name (the place's own)
    stands: List[Stand]
    roads: Dict[Tuple[str, str], Road]
    cars: Dict[str, int]
    warnings: List[str] = field(default_factory=list)

    def at(self, t: int) -> Scene:
        return scene(self.stands, self.roads, t, self.cars)

    def events(self) -> List[int]:
        """Every time something arrives or leaves (for stepping train by train)."""
        return sorted({s.start for s in self.stands} | {s.end for s in self.stands if s.end < END})


def _read_xml(path: str):
    from rstools import filecache
    from rstools.berthing.xmlread import BerthingError, read_xml
    try:
        return filecache.remember(read_xml, path)
    except BerthingError as exc:
        raise TrackMapError(str(exc))


def busiest_day(xml_path: str) -> int:
    """The day with the most unit diagrams (a one-day test XML is that day)."""
    xml = _read_xml(xml_path)
    count = Counter(d for diag in xml.diagrams for d in diag.days)
    return count.most_common(1)[0][0] if count else 0


def pages_for(map_name: str, place: str) -> List[MapPage]:
    from .pdfmap import find_pages
    return find_pages(load_map(map_name), place)


def build(map_name: str, page_index: int, xml_path: str, place: str, day: int) -> View:
    """The view of `place` (a station or siding name, e.g. 'Brighton') on page `page_index` of the kept map, from the
    XML's diagrams running on `day` (0 = Monday)."""
    pages = load_map(map_name)
    page = next((p for p in pages if p.index == page_index), None)
    if page is None:
        raise TrackMapError(f"The track map '{map_name}' has no page {page_index + 1}.")
    if not os.path.isfile(xml_path):
        raise TrackMapError(f"This file could not be found: {xml_path}")
    xml = _read_xml(xml_path)
    locs = place_locations(xml.locations, place)
    if not locs:
        raise TrackMapError(f"'{place}' is not a location in {os.path.basename(xml_path)}.")
    found = stands(xml, locs, day)
    keys = sorted({(s.loc, s.plat) for s in found})
    names = {tip: xml.locations.get(tip, tip) for tip in locs}
    roads = match_roads(page, keys, names, place)
    from rstools.statspack.fleet import FleetTable
    cars = {r.cls: r.cars for r in FleetTable.load().rows if r.cars}
    warnings = []
    missing = sorted({s.fleet for s in found if s.fleet not in cars})
    if missing:
        warnings.append("No car count in the fleet data for " + ", ".join(missing) + ": drawn as 4 cars.")
    off = sorted({k for k in keys if k not in roads})
    if off:
        warnings.append("Not found on this page (listed beside the map): "
                        + ", ".join(f"{names.get(k[0], k[0])}{' ' + k[1] if k[1] else ''}" for k in off))
    guessed = sorted(r.label for r in roads.values() if r.guessed_end      # a platform's label is at its stop
                     and not r.label.casefold().startswith("plat"))         # end; a siding's may not be
    if guessed:
        warnings.append("Units are drawn from the end of the track nearest its label (the buffer stop could not be "
                        "told from the drawing): " + ", ".join(dict.fromkeys(guessed)))
    return View(page, place, day, names, found, roads, cars, warnings)


def clock(t: int) -> str:
    """'05:34' (times past midnight shown as the next day's: '01:10')."""
    t %= 86400
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}"


def describe(s: Stand, names: Optional[Dict[str, str]] = None) -> str:
    """A unit's stand in words, for the details beside the map."""
    where = (names or {}).get(s.loc, s.loc) + (f" platform / road {s.plat}" if s.plat else "")
    came = f"arrived as {s.arrived_as}" if s.arrived_as else "there from the start of the day"
    goes = f"leaves as {s.leaves_as}" if s.leaves_as else "still there at the end of the day"
    with_ = (" with " + " + ".join(u for u in s.formation if u not in (s.unit, s.was))
             if len(s.formation) > 1 else "")
    was = f" (arrived on diagram {s.was})" if s.was else ""
    return (f"{s.fleet} {s.unit}{was}{with_}: {where}, {clock(s.start)}-{clock(s.end)}; {came}, {goes}")
