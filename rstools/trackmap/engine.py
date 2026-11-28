"""Everything the track map view needs, read once: a page of a kept track map, the units standing at the place on a
day (from an Attune XML), which drawn track each platform or road is, and the cars of each fleet. The window asks
for the picture at a time (`View.at`) and draws it."""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from rstools.days import DAY_NAMES

from .occupancy import END, Stand, place_locations, stands
from .pdfmap import MapPage, TrackMapError, load_map
from .scene import _PLAT, Road, Scene, match_roads, scene


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


ALL_MAPS = "All track maps"


def place_tiplocs(xml_path: str, place: str) -> List[str]:
    """The place's own TIPLOCs in the XML (to find it by code on strip-diagram books); none without an XML."""
    if not xml_path or not os.path.isfile(xml_path):
        return []
    return place_locations(_read_xml(xml_path).locations, place)


def pages_for(map_name: str, place: str, xml_path: str = "") -> List[Tuple[str, MapPage]]:
    """The pages showing a place, best first, as (map, page): in one kept map, or in every one (ALL_MAPS)."""
    from .pdfmap import page_rank, stored_maps
    tips = place_tiplocs(xml_path, place)
    names = stored_maps() if map_name == ALL_MAPS else [map_name]
    found = []
    for name in names:
        for p in load_map(name):
            r = page_rank(p, place, tips)
            if r < 9:
                found.append((r, name, p))
    found.sort(key=lambda x: (x[0], x[1], x[2].index))
    return [(name, p) for _r, name, p in found]


def depot_locations(names: Dict[str, str]) -> Dict[str, str]:
    """Which of these locations are depots (Settings > Depots), each with the depot it is part of: only the total
    of units at each depot is shown."""
    from rstools.statspack.units import Depots
    dep = Depots.load(names)
    return {t: dep.depot_of(t) for t in sorted(names) if dep.depot_of(t)}


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
    depots = depot_locations(names)
    roads = match_roads(page, keys, names, place, tiplocs=locs, depots=depots)
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
    if depots:
        warnings.append("Depots show only how many units are there: "
                        + ", ".join(sorted(set(depots.values()))))
    guessed = sorted(r.label for r in roads.values()        # a platform's label is at its stop end; a siding's
                     if r.guessed_end and not r.depot and not _PLAT.match(r.label.strip()))   # may not be
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


# --------------------------------------------------------------------------- how much of a timetable the maps show
@dataclass
class Cover:
    place: str
    stands: int                         # unit stands at the place on the day
    roads: int                          # its platforms and roads used
    placed: int                         # of those, found on the best page
    map_name: str = ""
    page: str = ""                      # that page's title
    missing: List[str] = field(default_factory=list)


def _places(locations: Dict[str, str], used: Sequence[str]) -> Dict[str, List[str]]:
    """The places units stand at, each with its locations: a siding named after a station ('Brighton Wall Siding')
    is part of that station's place when the station is a location too. Junctions and signals are left out."""
    from .occupancy import part_of
    names = sorted({locations.get(t, t) for t in used}, key=len)
    out: Dict[str, List[str]] = {}
    for tip in used:
        name = locations.get(tip, tip)
        if re.search(r"\bsig(?:nal)?\b", name, re.I):
            continue                                # a signal
        head = next((n for n in names if len(n) < len(name) and part_of(name, n)), name)
        out.setdefault(head, []).append(tip)
    return out


def coverage(xml_path: str, day: int, map_name: str = ALL_MAPS, progress=None) -> List[Cover]:
    """For every place units stand at between trains on `day` (calls on the way are not counted), the kept map page
    that shows most of its platforms and roads, and which of them it does not show (busiest places first)."""
    from .pdfmap import page_rank, stored_maps
    if not os.path.isfile(xml_path):
        raise TrackMapError(f"This file could not be found: {xml_path}")
    xml = _read_xml(xml_path)
    maps = {n: load_map(n) for n in (stored_maps() if map_name == ALL_MAPS else [map_name])}
    if not maps:
        raise TrackMapError("No track map has been added yet (Add track map PDF...).")
    found = [s for s in stands(xml, list(xml.locations), day) if not s.passing]    # standing between trains
    used = sorted({s.loc for s in found})
    places = _places(xml.locations, used)
    depots = depot_locations({t: xml.locations.get(t, t) for t in used})
    rows: List[Cover] = []
    for i, (place, tips) in enumerate(sorted(places.items())):
        if progress:
            progress(i / max(len(places), 1))
        mine = [s for s in found if s.loc in tips]
        keys = sorted({(s.loc, s.plat) for s in mine})
        names = {t: xml.locations.get(t, t) for t in tips}
        ranked = sorted(((page_rank(p, place, tips), n, p) for n, pages in maps.items() for p in pages),
                        key=lambda x: (x[0], x[1], x[2].index))
        best: Optional[Tuple[str, MapPage, Dict]] = None
        for r, n, p in ranked[:4]:
            if r >= 9:
                break
            roads = match_roads(p, keys, names, place, tiplocs=tips,
                                depots={t: g for t, g in depots.items() if t in tips})
            if best is None or len(roads) > len(best[2]):
                best = (n, p, roads)
        got = best[2] if best else {}
        rows.append(Cover(place, len(mine), len(keys), len(got), best[0] if best else "",
                          (best[1].title or f"Page {best[1].index + 1}") if best else "",
                          [f"{names.get(k[0], k[0])}{' ' + k[1] if k[1] else ''}" for k in keys if k not in got]))
    rows.sort(key=lambda c: (-c.stands, c.place))
    return rows


def save_coverage(rows: Sequence[Cover], folder: str = "", day: int = 0) -> str:
    """The coverage list as a workbook in the output folder (never over an existing file); its path."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from rstools.fsutil import clean_cell, output_folder, save_output, unique_stem
    from rstools.xlsave import save_workbook
    out = output_folder(folder)
    path = os.path.join(out, unique_stem(out, f"Track map coverage - {DAY_NAMES[day]}") + ".xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Coverage"
    head = ["Place", "Unit stands", "Platforms / roads", "On the map", "Track map", "Page", "Not found"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([clean_cell(v) for v in (r.place, r.stands, r.roads, r.placed, r.map_name, r.page,
                                           ", ".join(r.missing))])
    for col, width in zip("ABCDEFG", (30, 12, 16, 12, 34, 22, 80)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    save_output(lambda: save_workbook(wb, path), path, TrackMapError)
    return path
