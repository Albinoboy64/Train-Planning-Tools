"""Putting the units on the track map: which drawn track each platform or road of the XML is (by its label: 'Plat 7',
'WALL SIDING'), which end of it is the stop end, and where each unit is drawn along it at a given time."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .occupancy import Stand, present
from .pdfmap import Label, MapPage, Point, Track

CAR = 9.0                           # page points per car (the diagrams are not to scale: a 12-car platform ~110 pt)
NEAR = 30.0                         # a label names a track within this distance


@dataclass
class Road:
    """A platform or road of the XML ((location, platform) key) on the map."""
    key: Tuple[str, str]
    label: str                      # the map's label it was matched by
    pts: List[Point]                # the track, from its stop end
    guessed_end: bool = False       # the stop end could not be told from the drawing


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
_PLAT = re.compile(r"^(?:plat(?:form)?\.?)\s*(\d+)\s*([a-z]?)$", re.I)


def _words(text: str) -> List[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.casefold()) if w and w not in ("the", "and")]


def label_for(key: Tuple[str, str], loc_name: str, place: str, labels: Sequence[Label]) -> Optional[Label]:
    """The map label a platform or road of the XML is: 'Plat 7' for platform 7 (or 7F / 7R, its front or rear
    part) of the place itself; for a siding location ('Brighton Wall Siding'), the label naming it ('WALL SIDING')."""
    loc, plat = key
    plats = {}
    for lb in labels:
        m = _PLAT.match(lb.text.strip())
        if m:
            plats[m.group(1)] = lb
    name = " ".join(loc_name.split())
    own = name.casefold() == " ".join(place.split()).casefold()
    m = re.match(r"^(\d+)", plat or "")
    if own and m and m.group(1) in plats:
        return plats[m.group(1)]
    want = [w for w in _words(name) if w not in _words(place)]
    if not want:
        return None
    best, score = None, 0.0
    for lb in labels:
        words = _words(lb.text)
        if not words or _PLAT.match(lb.text.strip()):
            continue
        hit = sum(1 for w in want if w in words) / len(want)
        if hit > score and hit > 0.99:              # every word of the name ('wall siding'), never just 'siding'
            best, score = lb, hit
    return best


def match_roads(page: MapPage, keys: Sequence[Tuple[str, str]], names: Dict[str, str], place: str) -> Dict[
        Tuple[str, str], Road]:
    """The drawn track of each (location, platform) key that the page names."""
    tracks = [t for t in page.tracks if t.kind in ("running", "siding") and t.length >= 20]
    lines = [t for t in page.tracks if t.kind in ("running", "siding", "points")]
    plat_labels = [lb for lb in page.labels if _PLAT.match(lb.text.strip())]
    out: Dict[Tuple[str, str], Road] = {}
    used: Dict[str, List[Track]] = {}               # a siding location's roads take its tracks in turn
    for key in sorted(keys):
        lb = label_for(key, names.get(key[0], key[0]), place, page.labels)
        if lb is None:
            continue
        here = (lb.x, lb.y)
        found = sorted(((_nearest(t.pts, here), t) for t in tracks), key=lambda x: x[0][0])
        near: List[Tuple[float, Point, Track]] = [(d, q, t) for (d, q), t in found if d <= NEAR]
        if lb not in plat_labels:                   # a siding or road by name: its own (green) tracks first, each
            sidings = [n for n in near if n[2].kind == "siding"]          # road of it on the next one
            if sidings:
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
    for key, group in present(stands, t).items():
        road = roads.get(key) or (roads.get((key[0], re.sub(r"[A-Z]$", "", key[1])))  # 7F / 7R: platform 7
                                   if key[1] else None)
        if road is None:
            out.unplaced[key] = group
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
    return out
