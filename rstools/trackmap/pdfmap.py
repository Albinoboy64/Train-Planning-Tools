"""Reading a track diagram PDF (vector drawings such as Network Rail's route track diagrams) into its track layout:
each page's tracks as lines with their kind (running line, siding, crossover, platform edge), and its text labels
with where they are (road and platform names, signal numbers, the page name and station names).

The PDF is read once, in a helper process (PDFium is native code), and what is kept is small: it is saved in the
app's data folder, so the map itself is never copied or shipped. Nothing here assumes one publisher: tracks are
told apart by their colour, which the caller can change (KINDS)."""
from __future__ import annotations

import gzip
import json
import math
import os
import re
from collections import Counter
from functools import cached_property
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]

# colour (r, g, b) -> kind of line, as the route track diagrams draw them
KINDS: Dict[Tuple[int, int, int], str] = {
    (66, 48, 146): "running",        # running lines (blue)
    (106, 109, 110): "running",      # running lines (grey)
    (109, 110, 112): "running",
    (90, 92, 93): "running",         # running lines (dark grey)
    (99, 188, 70): "siding",         # sidings and depot roads (green) - also signal symbols, told apart by length
    (199, 46, 31): "points",         # crossovers and points (red)
    (166, 70, 154): "platform",      # platform edges (purple)
}
MIN_TRACK = 12.0                     # points: shorter lines are symbols (signals, buffer stops), not track


class TrackMapError(Exception):
    pass


@dataclass
class Track:
    kind: str
    pts: List[Point]                 # page points, origin top left

    @property
    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.pts, self.pts[1:]))


@dataclass
class Label:
    text: str
    x: float                         # centre, page points from the top left
    y: float
    size: float = 0.0                # height of the text


@dataclass
class MapPage:
    index: int                       # page in the PDF (0 = first)
    width: float
    height: float
    title: str = ""                  # 'Sussex 25'
    tracks: List[Track] = field(default_factory=list)
    labels: List[Label] = field(default_factory=list)
    codes: Dict[str, Point] = field(default_factory=dict)     # TIPLOC -> where the page names it

    @cached_property
    def texts(self) -> List[str]:
        """Each label's text as place names are compared (norm_place)."""
        return [norm_place(lb.text) for lb in self.labels]

    @cached_property
    def blob(self) -> str:
        """Every label as words between spaces, one per line (to find a name among them quickly)."""
        return "\n".join(" " + " ".join(re.split(r"[^a-z0-9]+", t)) + " " for t in self.texts)

    @cached_property
    def headings(self) -> List[str]:
        """The largest station-style names on the page (e.g. 'BRIGHTON'), largest first."""
        named = [lb for lb in self.labels if any(c.isalpha() for c in lb.text) and len(lb.text) > 3
                 and lb.text != self.title]
        named.sort(key=lambda lb: -lb.size)
        return [lb.text for lb in named[:4]]


def _spine(pts: List[Point]) -> List[Point]:
    """A thin filled band (a line drawn as a narrow shape) as the line along one of its edges."""
    if len(pts) < 4 or math.dist(pts[0], pts[-1]) > 1.0:
        return pts
    far = max(range(len(pts)), key=lambda i: math.dist(pts[0], pts[i]))
    return pts[:far + 1]


def _same_line(a: List[Point], b: List[Point]) -> bool:
    """Two drawings of one track: their ends within a couple of points of each other (either way round)."""
    return ((math.dist(a[0], b[0]) < 2.5 and math.dist(a[-1], b[-1]) < 2.5)
            or (math.dist(a[0], b[-1]) < 2.5 and math.dist(a[-1], b[0]) < 2.5))


def _bounds(pts: List[Point]) -> Tuple[float, float]:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def _colour(get, raw):
    import ctypes
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    return (r.value, g.value, b.value) if get(raw, *(ctypes.byref(v) for v in (r, g, b, a))) else None


def _thick_kind(stroke, width: float, length: float) -> Optional[str]:
    """Track in the strip-diagram books (East Midlands, LNE, Anglia): thick strokes, coloured by track circuit or
    direction. Thick black lines are crossovers when short, the frames of the strips when long."""
    if stroke is None or width < 1.8 or length < MIN_TRACK:
        return None
    r, g, b = stroke
    if min(r, g, b) > 235:
        return None                            # white
    if max(r, g, b) < 70:
        return "points" if length < 120 else None
    if abs(r - g) < 12 and abs(g - b) < 12:
        return None                            # grey: grid and boxes
    return "running"


def _band(fill, pts: List[Point]):
    """A filled shape of the WCML book: ('running' / 'points', its centre line) for a thin band - a track coloured by
    track circuit, or a black crossover - 'block' for a red platform block, else None."""
    if len(pts) < 3 or len(pts) > 2000:
        return None
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2
    ends = {min(pts), max(pts), min(pts, key=lambda p: p[1]), max(pts, key=lambda p: p[1]),
            min(pts, key=lambda p: p[0] + p[1]), max(pts, key=lambda p: p[0] + p[1]),
            min(pts, key=lambda p: p[0] - p[1]), max(pts, key=lambda p: p[0] - p[1])}
    a, b = max(((p, q) for p in ends for q in ends), key=lambda pq: math.dist(*pq))     # its two ends
    length = math.dist(a, b)
    if length < MIN_TRACK:
        return None
    thick = area / length
    r, g, bl = fill
    if (r, g, bl) == (255, 0, 0) and thick >= 4:
        return "block"
    if thick > 3.5 or min(r, g, bl) > 170:
        return None                                # boxes, notes, white, the pale page grid
    dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    if max(abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) for p in pts) > 5.0:      # (an arrow head at an end)
        return None                                # not a band along one line (a frame, an arrow)
    if max(r, g, bl) < 70:
        return ("points", [a, b]) if length < 120 else None
    if max(r, g, bl) - min(r, g, bl) < 40:
        return None                                # grey: grid, tunnels
    return ("running", [a, b])


def _page_point(rotation: int, w0: float, h0: float):
    """The function turning a point of the page's own space into the page as shown (top left origin), for a page
    stored turned (/Rotate 90 in the strip-diagram books)."""
    if rotation == 90:
        return lambda x, y: (y, x)
    if rotation == 180:
        return lambda x, y: (w0 - x, y)
    if rotation == 270:
        return lambda x, y: (h0 - y, w0 - x)
    return lambda x, y: (x, h0 - y)


def read_page_layout(pdf_path: str, index: int) -> dict:
    """One page's layout as plain data (runs in a helper process)."""
    import ctypes
    import re

    import pypdfium2 as pdfium
    import pypdfium2.raw as R
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[index]
        width, height = page.get_size()
        left, bottom, right, top = page.get_mediabox()
        shown = _page_point(page.get_rotation(), right - left, top - bottom)
        tracks: List[dict] = []
        bands: List[dict] = []                 # filled colour bands (the WCML book): used if nothing else is
        blocks: List[Tuple[float, float, float, float]] = []                  # red platform blocks
        for obj in page.get_objects(max_depth=8):
            if obj.type != R.FPDF_PAGEOBJ_PATH:
                continue
            raw = obj.raw
            mode, stroked = ctypes.c_int(), ctypes.c_int()
            R.FPDFPath_GetDrawMode(raw, ctypes.byref(mode), ctypes.byref(stroked))
            fill = _colour(R.FPDFPageObj_GetFillColor, raw) if mode.value else None
            stroke = _colour(R.FPDFPageObj_GetStrokeColor, raw) if stroked.value else None
            kind = (KINDS.get(stroke) if stroke else None) or (KINDS.get(fill) if fill else None)
            lw = ctypes.c_float()
            R.FPDFPageObj_GetStrokeWidth(raw, ctypes.byref(lw))
            plain = bool(fill) and not stroke and not kind
            if not kind and not (stroke and lw.value >= 1.8) and not plain:
                continue
            m = obj.get_matrix()
            pts: List[Point] = []
            for i in range(R.FPDFPath_CountSegments(raw)):
                seg = R.FPDFPath_GetPathSegment(raw, i)
                x, y = ctypes.c_float(), ctypes.c_float()
                R.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y))
                px, py = m.on_point(x.value, y.value)
                sx, sy = shown(px - left, py - bottom)
                pts.append((round(sx, 2), round(sy, 2)))
            length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            if plain:
                band = _band(fill, pts)
                if band == "block":
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    blocks.append((min(xs), min(ys), max(xs), max(ys)))
                elif band:
                    bands.append({"kind": band[0], "pts": band[1]})
                continue
            if not kind:
                kind = _thick_kind(stroke, lw.value, length)
                if not kind:
                    continue
            if fill and not stroke:
                pts = _spine(pts)              # a band drawn filled: its edge is the line
                length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            w, h = _bounds(pts) if pts else (0, 0)
            if len(pts) < 2 or length < MIN_TRACK:
                continue                       # signal heads, arrows, buffer stops
            if kind in ("siding", "running") and min(w, h) > 6 and math.dist(pts[0], pts[-1]) < 0.5:
                continue                       # a closed shape: a symbol or a box, not a road
            if any(t["kind"] == kind and _same_line(t["pts"], pts) for t in tracks):
                continue                       # the same track drawn twice (its outline and its band)
            tracks.append({"kind": kind, "pts": pts})
        labels = _labels(page, shown, left, bottom, page.get_rotation() in (90, 270))
        if not tracks:                         # the WCML book: tracks drawn as filled bands, platforms as red blocks
            upright = Counter(round(abs(b["pts"][1][1] - b["pts"][0][1])) for b in bands          # the mileage grid:
                              if abs(b["pts"][0][0] - b["pts"][1][0]) < 1)                       # four or more
            for b in bands:                    # numbered '1', '2'... (named here as the other books name them)
                (x0, y0), (x1, y1) = b["pts"]                                                   # alike, upright
                if abs(x0 - x1) < 1 and upright[round(abs(y1 - y0))] >= 4:
                    continue
                if not any(t["kind"] == b["kind"] and _same_line(t["pts"], b["pts"]) for t in tracks):
                    tracks.append(b)
            for lb in labels:
                if re.fullmatch(r"\d{1,2}[a-zA-Z]?", lb["text"]) and any(
                        x0 - 1 <= lb["x"] <= x1 + 1 and y0 - 1 <= lb["y"] <= y1 + 1 for x0, y0, x1, y1 in blocks):
                    lb["text"] = "Plat " + lb["text"]
    finally:
        pdf.close()
    title = next((lb["text"] for lb in sorted(labels, key=lambda lb: -lb["size"])      # 'Sussex 25'
                  if re.fullmatch(r"[A-Za-z][A-Za-z ]*\s\d+[A-Za-z]?", lb["text"]) and lb["size"] >= 10), "")
    codes: Dict[str, Point] = {}
    for lb in labels:                          # '54299 : MORGATEGN' (STANOX : TIPLOC) in the strip-diagram books
        for code in re.findall(r"\b\d{5}\s*:\s*([A-Z][A-Z0-9]{2,8})\b", lb["text"]):
            codes.setdefault(code, (lb["x"], lb["y"]))
    return {"index": index, "width": round(width, 1), "height": round(height, 1), "title": title,
            "tracks": tracks, "labels": labels, "codes": codes}


def _labels(page, shown, left: float = 0.0, bottom: float = 0.0, turned: bool = False) -> List[dict]:
    """Every line of text with its centre and height, read character by character (labels at an angle, such as a
    siding's name drawn along it, are kept whole)."""
    tp = page.get_textpage()
    out: List[dict] = []
    word: List[str] = []
    boxes: List[tuple] = []

    def flush():
        text = " ".join("".join(word).split())
        if text and boxes:
            l = min(b[0] for b in boxes)
            r = max(b[2] for b in boxes)
            b_ = min(b[1] for b in boxes)
            t = max(b[3] for b in boxes)
            x, y = shown((l + r) / 2 - left, (b_ + t) / 2 - bottom)
            size = max((bx[2] - bx[0]) if turned else (bx[3] - bx[1]) for bx in boxes)   # a character's height
            out.append({"text": text, "x": round(x, 1), "y": round(y, 1), "size": round(size, 1)})
        word.clear()
        boxes.clear()
    def centre(b):
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    def angle(a, b) -> float:
        (x1, y1), (x2, y2) = centre(a), centre(b)
        return math.degrees(math.atan2(y2 - y1, x2 - x1))
    spaced = False
    for i in range(tp.count_chars()):
        ch = tp.get_text_range(i, 1)
        if ch in ("\r", "\n", ""):
            flush()
            spaced = False
            continue
        if ch == " ":
            spaced = True
            word.append(ch)
            continue
        box = tp.get_charbox(i)
        if boxes:
            far = math.dist(centre(box), centre(boxes[-1])) > 25        # the next character is elsewhere
            level = len(boxes) > 1 and abs(angle(boxes[0], boxes[-1])) < 5      # a word written level...
            turned = spaced and level and abs(box[1] - boxes[0][1]) > 1.5      # ...then text off its line: two
                                                                                # labels side by side ('Plat 1',
                                                                                # 'Plat 2' just above)
            if far or turned:
                flush()
        spaced = False
        word.append(ch)
        boxes.append(box)
    flush()
    return out


def page_count(pdf_path: str) -> int:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        return len(pdf)
    finally:
        pdf.close()


def _read_all(pdf_path: str) -> List[dict]:
    """Every page's layout (in one helper process)."""
    return [read_page_layout(pdf_path, i) for i in range(page_count(pdf_path))]


# --------------------------------------------------------------------------- the map kept in the data folder
def store_dir() -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), "trackmaps")


def import_map(pdf_path: str, log: Callable[[str], None] = lambda m: None) -> str:
    """Read a track diagram PDF and keep its layout in the data folder; returns the name it is kept under. The PDF
    itself is not copied."""
    from rstools import limits
    from rstools.fsutil import atomic_path, safe_stem
    from rstools.isolate import run
    if not os.path.isfile(pdf_path):
        raise TrackMapError(f"This file could not be found: {pdf_path}")
    try:
        limits.check_pdf(pdf_path)
    except OSError as exc:
        raise TrackMapError(str(exc))
    log(f"Reading the track layout from {os.path.basename(pdf_path)}...")
    try:
        pages = run(_read_all, pdf_path, name=os.path.basename(pdf_path))
    except OSError as exc:
        raise TrackMapError(f"'{os.path.basename(pdf_path)}' could not be read as a track diagram PDF ({exc}).")
    except Exception as exc:                  # PDFium's own errors: not a PDF, password protected...
        raise TrackMapError(f"'{os.path.basename(pdf_path)}' could not be read as a track diagram PDF ({exc}).")
    if not any(p["tracks"] for p in pages):
        raise TrackMapError(f"'{os.path.basename(pdf_path)}' has no track drawn as lines that the app can read "
                            "(a scanned or picture-only PDF cannot be used).")
    name = safe_stem(os.path.splitext(os.path.basename(pdf_path))[0])[:80]
    os.makedirs(store_dir(), exist_ok=True)
    path = os.path.join(store_dir(), name + ".json.gz")
    with atomic_path(path) as tmp, gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump({"source": os.path.basename(pdf_path), "pages": pages}, fh, separators=(",", ":"))
    log(f"Track layout of {plural_pages(len(pages))} kept as '{name}'.")
    return name


def plural_pages(n: int) -> str:
    from rstools.naming import plural
    return plural(n, "page")


def stored_maps() -> List[str]:
    """The names of the track maps kept in the data folder."""
    try:
        return sorted(f[:-len(".json.gz")] for f in os.listdir(store_dir()) if f.endswith(".json.gz"))
    except OSError:
        return []


def load_map(name: str) -> List[MapPage]:
    """A kept track map's pages."""
    from rstools import limits
    path = os.path.join(store_dir(), name + ".json.gz")
    try:
        limits.check_size(path, "PDF_MAX_BYTES", "track map")
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, EOFError) as exc:
        raise TrackMapError(f"The track map '{name}' could not be read ({exc}). Add the PDF again.")
    return [page_from_dict(p) for p in data.get("pages", [])]


def page_from_dict(p: dict) -> MapPage:
    return MapPage(int(p["index"]), float(p["width"]), float(p["height"]), str(p.get("title", "")),
                   [Track(str(t["kind"]), [(float(x), float(y)) for x, y in t["pts"]]) for t in p.get("tracks", [])],
                   [Label(str(lb["text"]), float(lb["x"]), float(lb["y"]), float(lb.get("size", 0)))
                    for lb in p.get("labels", [])],
                   {str(k): (float(v[0]), float(v[1])) for k, v in (p.get("codes") or {}).items()})


def page_to_dict(page: MapPage) -> dict:
    return asdict(page)


_SPELL = ((" g c ", " garden city "), (" peterboro ", " peterborough "), (" rd ", " road "), (" jn ", " junction "))


def norm_place(name: str) -> str:
    """A place name as maps write it: no '(C)' / '(E)' part, brackets and apostrophes dropped ('Kensington (Olympia)'
    -> 'kensington olympia', "Shepherd's Bush" -> 'shepherds bush'), 'St.' as 'St', '&' as 'and'."""
    text = re.sub(r"\(\s*[A-Za-z]{1,2}\s*\)", " ", name or "")          # '(C)', '(E)': a part of a station
    text = re.sub(r"[()]", " ", text).replace("'", "").replace("’", "")
    text = text.replace("&", " and ").replace(".", " ")
    text = " " + " ".join(text.split()).casefold() + " "
    for short, full in _SPELL:
        text = text.replace(short, full)
    return text.strip()


# what a siding, depot or yard's name adds to the place it is at ('Selhurst T&R.S.M.D', 'Bognor Sidings',
# 'Letchworth C.S.D'): the place is found on a map by what is left
_STABLING_TAIL = re.compile(r"(?:\s+(?:t\s*and\s*r\s*s\s*m\s*d|t\s*r\s*s\s*m\s*d|tmd|e\s*m\s*u\s*d|emud|"
                            r"depot|traincare|"
                            r"c\s*s\s*d|c\s*h\s*s|c\s*s|carriage\s+sidings?|sidings?|sdgs?|yard|turnback|reception|"
                            r"run\s+round|a/d\s+line|shed|\w*\d\w*))+$")
_GENERIC = {"bridge", "road", "street", "junction", "park", "central", "station"}


def place_variants(name: str) -> List[str]:
    """The ways a map may name a place: 'London Victoria (C)' -> 'london victoria', 'victoria'; a depot or siding
    by the place it is at as well ('Selhurst T&R.S.M.D' -> 'selhurst')."""
    base = norm_place(name)
    out = [base]
    bare = norm_place(re.sub(r"\([^)]*\)", " ", name or ""))      # 'Sutton (Surrey)' is also 'Sutton'
    if bare and bare != base:
        out.append(bare)
    if base.startswith("london ") and base[len("london "):] not in _GENERIC:
        out.append(base[len("london "):])
    for tail in (" station", " low level", " high level"):
        if base.endswith(tail):
            out.append(base[:-len(tail)])
    short = _STABLING_TAIL.sub("", base).strip(" -")
    if short and short != base and short not in _GENERIC:
        out.append(short)
    return [v for v in dict.fromkeys(out) if v]


def name_codes(place: str) -> List[str]:
    """The codes a strip-diagram book may give a place instead of its TIPLOC: its name in capitals without spaces
    ('Old Street' -> 'OLDSTREET')."""
    return [re.sub(r"[^A-Z0-9]", "", v.upper()) for v in place_variants(place)]


def page_rank(p: MapPage, place: str, tiplocs: Sequence[str] = ()) -> int:
    """How surely a page shows a place: 0 its heading or its TIPLOC code, 1 a label naming it, 2 a label containing
    its name, 9 not at all (or an index or key page, with no drawing)."""
    if len(p.tracks) < 4:
        return 9
    variants = place_variants(place)
    if any(t in p.codes for t in list(tiplocs) + name_codes(place)):
        return 0
    if any(norm_place(h) == v or norm_place(h).startswith(v + " ") for h in p.headings for v in variants):
        return 0
    if any(t in variants for t in p.texts):
        return 1
    blob = p.blob
    return 2 if any(" " + " ".join(re.split(r"[^a-z0-9]+", v)) + " " in blob for v in variants) else 9


def find_pages(pages: List[MapPage], place: str, tiplocs: Sequence[str] = ()) -> List[MapPage]:
    """The pages a place is on (by a label naming it, or its TIPLOC code), the page where it is a heading first."""
    ranked = [(page_rank(p, place, tiplocs), p) for p in pages]
    return [p for r, p in sorted(((r, p) for r, p in ranked if r < 9), key=lambda x: (x[0], x[1].index))]


def page_by_title(pages: List[MapPage], title: str) -> Optional[MapPage]:
    return next((p for p in pages if p.title == title), None)
