"""Putting the units on the track map: which drawn track each platform or road of the XML is (by its label: 'Plat 7',
'WALL SIDING'), which end of it is the stop end, and where each unit is drawn along it at a given time."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .occupancy import Stand, present
from .pdfmap import Label, MapPage, Point, Track, name_codes, norm_place, place_variants

CAR = 9.0                           # page points per car (the diagrams are not to scale: a 12-car platform ~110 pt)
NEAR = 30.0                         # a label names a track within this distance
FAN = 70.0                          # ... and a siding label the roads of its fan of sidings within this


@dataclass
class Road:
    """A platform or road of the XML ((location, platform) key) on the map."""
    key: Tuple[str, str]
    label: str                      # the map's label it was matched by
    pts: List[Point]                # the track, from its stop end
    guessed_end: bool = False       # the stop end could not be told from the drawing
    depot: bool = False             # a depot: only how many units are there is shown, at pts[0]


@dataclass
class UnitDraw:
    stand: Stand
    a: Point                        # from (the end nearer the stop end) ...
    b: Point                        # ... to
    beyond: bool = False            # past the end of the track as drawn (longer than the road on the map)


@dataclass
class Scene:
    t: int
    units: List[UnitDraw] = field(default_factory=list)
    unplaced: Dict[Tuple[str, str], List[Stand]] = field(default_factory=dict)   # not on this page / not matched
    counts: List[Tuple[str, Point, int]] = field(default_factory=list)          # depots: (name, where, units)
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- geometry
def _nearest(pts: Sequence[Point], p: Point) -> Tuple[float, Point]:
    best = (math.inf, pts[0])
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        q = (a[0] + u * dx, a[1] + u * dy)
        d = math.dist(p, q)
        if d < best[0]:
            best = (d, q)
    return best


def _along(pts: Sequence[Point], dist: float) -> Point:
    """The point `dist` along the line from its first point (straight on past its end)."""
    left = dist
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if left <= seg and seg > 0:
            u = left / seg
            return (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
        left -= seg
    a, b = pts[-2], pts[-1]
    seg = math.dist(a, b) or 1.0
    return (b[0] + left * (b[0] - a[0]) / seg, b[1] + left * (b[1] - a[1]) / seg)


def _length(pts: Sequence[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _free_end(track: Track, others: Sequence[Track]) -> Optional[int]:
    """0 or -1: the end of the track that joins no other track (a buffer stop), when exactly one does not."""
    free = []
    for i in (0, -1):
        p = track.pts[i]
        joined = any(o is not track and any(math.dist(p, q) < 2.5 for q in (o.pts[0], o.pts[-1])) or
                     (o is not track and _nearest(o.pts, p)[0] < 1.5) for o in others)
        if not joined:
            free.append(i)
    return free[0] if len(free) == 1 else None


# --------------------------------------------------------------------------- matching the XML's roads to the map
_PLAT = re.compile(r"^(?:p|plat|platform)\.?\s*(\d{1,2}|[a-z]\b)\s*([a-z]?)$", re.I)  # 'P1', 'Plat 7', 'Platform A'
AREA = 260.0                        # a station's platform labels are within this distance of its name


_ABBREV = {"sdg": "siding", "sdgs": "siding", "sidings": "siding", "dn": "down", "nth": "north", "sth": "south",
           "rd": "road", "roads": "road", "rec": "reception", "rev": "reversing", "chs": "siding", "csd": "siding",
           "cs": "siding", "no": "", "the": "", "and": ""}


def _words(text: str) -> List[str]:
    """A name's words as compared: abbreviations written out ('Dn Sdgs' -> 'down siding'), 'C.H.S.' as one word."""
    text = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", text.casefold())          # c.h.s. -> chs.
    text = re.sub(r"\b([a-z])\s(?=[a-z]\b)", r"\1", text) if re.search(r"\b[a-z] [a-z] [a-z]\b", text) else text
    out = []
    for w in re.split(r"[^a-z0-9]+", text):
        w = _ABBREV.get(w, w)
        if w:
            out.append(w)
    return out


def anchor_of(page: MapPage, place: str, tiplocs: Sequence[str] = ()) -> Optional[Point]:
    """Where the page names the place: its TIPLOC code (strip-diagram books), else its name - the largest label
    reading as the place (a heading such as 'BRIGHTON', or 'Moorgate')."""
    for tip in list(tiplocs) + name_codes(place):
        if tip in page.codes:
            return page.codes[tip]
    variants = place_variants(place)
    best = None
    for lb, text in zip(page.labels, page.texts):
        if text in variants or any(text == v + " station" for v in variants):
            if best is None or lb.size > best.size:
                best = lb
    return (best.x, best.y) if best is not None else None


def label_for(key: Tuple[str, str], loc_name: str, place: str, labels: Sequence[Label],
              anchor: Optional[Point] = None) -> Optional[Label]:
    """The map label a platform or road of the XML is: 'Plat 7' for platform 7 (or 7F / 7R, its front or rear
    part) of the place itself - the one nearest where the page names the place, when a page shows several
    stations; for a siding location ('Brighton Wall Siding'), the label naming it ('WALL SIDING')."""
    loc, plat = key
    own = norm_place(loc_name) in place_variants(place)
    m = re.match(r"^(\d+|[A-Z]$)", (plat or "").upper())          # 7, 7F / 7R (its front or rear part), A
    if own and m:
        cands = [lb for lb in labels if (pm := _PLAT.match(lb.text.strip())) and pm.group(1).upper() == m.group(1)]
        if anchor is not None:
            cands = sorted((lb for lb in cands if math.dist((lb.x, lb.y), anchor) <= AREA),
                           key=lambda lb: math.dist((lb.x, lb.y), anchor))
        elif len(cands) > 1:
            cands = []                              # several stations' platform 1 and no way to tell which
        return cands[0] if cands else None
    base = min(place_variants(place) or [""], key=len)      # 'Bognor Sidings' is at 'bognor'
    want = [w for w in _words(norm_place(loc_name)) if w not in _words(base)]
    if not want:
        return None
    named = [(lb, set(_words(lb.text))) for lb in labels if not _PLAT.match(lb.text.strip())]
    if anchor is not None:
        named = [n for n in named if math.dist((n[0].x, n[0].y), anchor) <= 2 * AREA]
        named.sort(key=lambda n: math.dist((n[0].x, n[0].y), anchor))
    for need in (want, [w for w in want if not any(c.isdigit() for c in w)]):    # 'Down Siding 2': 'DOWN SIDING'
        if need:
            hit = next((lb for lb, words in named if all(w in words for w in need)), None)   # every word of
            if hit is not None:                                                             # the name, never
                return hit                                                                  # just 'siding'
    return None


_DEPOT = re.compile(r"depot|t\s*&?\s*r\.?\s*s\.?\s*m\.?\s*d|\btmd\b|e\.?m\.?u\.?d|traincare|\bshed\b|\bc\.?s\.?d\b",
                    re.I)


def depot_label(labels: Sequence[Label], depot: str, place: str, anchor: Optional[Point]) -> Optional[Label]:
    """The label naming a depot: one with its own name ('Cauldwell Depot' for Bedford Cauldwell), else one saying
    'depot' / 'T&RSMD' nearest where the page names its place."""
    base = set(_words(min(place_variants(place) or [""], key=len)))
    own = [w for w in _words(norm_place(depot)) if w not in base and not _DEPOT.fullmatch(w)]
    if own:
        hit = [lb for lb in labels if all(w in _words(lb.text) for w in own)]
        if anchor is not None:
            hit.sort(key=lambda lb: math.dist((lb.x, lb.y), anchor))
        if hit:
            return hit[0]
    found = [lb for lb in labels if _DEPOT.search(lb.text)]
    if anchor is None:
        return found[0] if len(found) == 1 else None
    found = [lb for lb in found if math.dist((lb.x, lb.y), anchor) <= 2 * AREA]
    return min(found, key=lambda lb: math.dist((lb.x, lb.y), anchor)) if found else None


def match_roads(page: MapPage, keys: Sequence[Tuple[str, str]], names: Dict[str, str], place: str,
                tiplocs: Sequence[str] = (), depots: Optional[Dict[str, str]] = None) -> Dict[Tuple[str, str], Road]:
    """The drawn track of each (location, platform) key that the page names. A depot (`depots`: TIPLOC -> the depot
    it is part of) is one spot - its label, else the place's name - where only the number of units is shown."""
    depots = depots or {}
    tracks = [t for t in page.tracks if t.kind in ("running", "siding") and t.length >= 20]
    lines = [t for t in page.tracks if t.kind in ("running", "siding", "points")]
    plat_labels = [lb for lb in page.labels if _PLAT.match(lb.text.strip())]
    anchor = anchor_of(page, place, tiplocs)
    out: Dict[Tuple[str, str], Road] = {}
    used: Dict[str, List[Track]] = {}               # a siding location's roads take its tracks in turn
    for key in sorted(keys):
        name = names.get(key[0], key[0])
        if key[0] in depots:
            group = depots[key[0]] or name
            spot = depot_label(page.labels, group, place, anchor)
            where = (spot.x, spot.y) if spot is not None else page.codes.get(key[0]) or anchor
            if where is not None:
                out[key] = Road(key, group, [where], depot=True)
            continue
        lb = label_for(key, name, place, page.labels, anchor)
        if lb is None:
            continue
        here = (lb.x, lb.y)
        found = sorted(((_nearest(t.pts, here), t) for t in tracks), key=lambda x: x[0][0])
        near: List[Tuple[float, Point, Track]] = [(d, q, t) for (d, q), t in found if d <= NEAR]
        if lb not in plat_labels:                   # a siding or road by name: its own (green) tracks first, each
            sidings = [(d, q, t) for (d, q), t in found if d <= FAN and t.kind == "siding"]   # road of it on the
            if sidings:                                                                     # next one
                taken = used.setdefault(lb.text, [])
                free = [n for n in sidings if n[2] not in taken] or sidings
                near = free + [n for n in near if n not in free]
                taken.append(near[0][2])
        if not near:
            continue
        pick = near[0]
        partner = next((o for o in plat_labels if o is not lb and abs(o.x - lb.x) < 35 and abs(o.y - lb.y) < 8),
                       None) if lb in plat_labels else None
        if partner is not None:                     # two platforms named in one island: the upper label is the
            above = lb.y < partner.y                # track above it, the lower the track below
            side = [n for n in near if (n[1][1] < lb.y) == above]
            pick = side[0] if side else pick
        track = pick[2]
        end = _free_end(track, lines)
        guessed = end is None
        if end is None:                             # the end nearer the label
            end = 0 if math.dist(track.pts[0], here) <= math.dist(track.pts[-1], here) else -1
        pts = list(track.pts) if end == 0 else list(reversed(track.pts))
        out[key] = Road(key, lb.text, pts, guessed)
    return out


# --------------------------------------------------------------------------- the picture at one time
def scene(stands: Sequence[Stand], roads: Dict[Tuple[str, str], Road], t: int, cars: Dict[str, int],
          car: float = CAR) -> Scene:
    """Where each unit present at time t is drawn: along its road from the stop end, in the order units stand."""
    out = Scene(t)
    depot_units: Dict[Tuple[str, Point], int] = {}
    for key, group in present(stands, t).items():
        road = roads.get(key) or (roads.get((key[0], re.sub(r"(?<=\d)[A-Z]$", "", key[1])))  # 7F / 7R: platform 7
                                   if key[1] else None)
        if road is None:
            out.unplaced[key] = group
            continue
        if road.depot:                              # depots are not planned road by road: a total only
            spot = (road.label, road.pts[0])
            depot_units[spot] = depot_units.get(spot, 0) + len(group)
            continue
        pos = 1.0                                   # a little clear of the buffer stop
        length = _length(road.pts)
        for s in group:
            n = cars.get(s.fleet) or 4
            a, b = _along(road.pts, pos), _along(road.pts, pos + n * car - 1.0)
            out.units.append(UnitDraw(s, a, b, beyond=pos + n * car > length + 0.5))
            pos += n * car
        if pos > length + 0.5:
            out.warnings.append(f"{road.label}: {sum(cars.get(s.fleet) or 4 for s in group)} cars - longer than "
                                "the road as drawn (check the formation or the road)")
    out.counts = [(name, where, n) for (name, where), n in sorted(depot_units.items())]
    return out
