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
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

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

    @property
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


def read_page_layout(pdf_path: str, index: int) -> dict:
    """One page's layout as plain data (runs in a helper process)."""
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as R
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[index]
        width, height = page.get_size()
        tracks: List[dict] = []
        for obj in page.get_objects(max_depth=8):
            if obj.type != R.FPDF_PAGEOBJ_PATH:
                continue
            raw = obj.raw
            mode, stroked = ctypes.c_int(), ctypes.c_int()
            R.FPDFPath_GetDrawMode(raw, ctypes.byref(mode), ctypes.byref(stroked))

            fill = _colour(R.FPDFPageObj_GetFillColor, raw) if mode.value else None
            stroke = _colour(R.FPDFPageObj_GetStrokeColor, raw) if stroked.value else None
            kind = (KINDS.get(stroke) if stroke else None) or (KINDS.get(fill) if fill else None)
            if not kind:
                continue
            m = obj.get_matrix()
            pts: List[Point] = []
            for i in range(R.FPDFPath_CountSegments(raw)):
                seg = R.FPDFPath_GetPathSegment(raw, i)
                x, y = ctypes.c_float(), ctypes.c_float()
                R.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y))
                px, py = m.on_point(x.value, y.value)
                pts.append((round(px, 2), round(height - py, 2)))
            if fill and not stroke:
                pts = _spine(pts)              # a band drawn filled: its edge is the line
            w, h = _bounds(pts) if pts else (0, 0)
            if len(pts) < 2 or sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) < MIN_TRACK:
                continue                       # signal heads, arrows, buffer stops
            if kind in ("siding", "running") and min(w, h) > 6 and math.dist(pts[0], pts[-1]) < 0.5:
                continue                       # a closed shape: a symbol or a box, not a road
            if any(t["kind"] == kind and _same_line(t["pts"], pts) for t in tracks):
                continue                       # the same track drawn twice (its outline and its band)
            tracks.append({"kind": kind, "pts": pts})
        labels = _labels(page, height)
    finally:
        pdf.close()
    import re
    title = next((lb["text"] for lb in sorted(labels, key=lambda lb: -lb["size"])      # 'Sussex 25'
                  if re.fullmatch(r"[A-Za-z][A-Za-z ]*\s\d+[A-Za-z]?", lb["text"]) and lb["size"] >= 10), "")
    return {"index": index, "width": round(width, 1), "height": round(height, 1), "title": title,
            "tracks": tracks, "labels": labels}


def _labels(page, height: float) -> List[dict]:
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
            out.append({"text": text, "x": round((l + r) / 2, 1), "y": round(height - (b_ + t) / 2, 1),
                        "size": round(max(bx[3] - bx[1] for bx in boxes), 1)})
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
                    for lb in p.get("labels", [])])


def page_to_dict(page: MapPage) -> dict:
    return asdict(page)


def find_pages(pages: List[MapPage], place: str) -> List[MapPage]:
    """The pages a place is on (by a label naming it), the page where it is a heading first."""
    want = " ".join(place.split()).casefold()

    def rank(p: MapPage) -> int:
        if len(p.tracks) < 4:
            return 9                                  # an index or key page, not a drawing
        if any(h.casefold() == want or h.casefold().startswith(want + " ") for h in p.headings):
            return 0                                  # the place is the page's heading
        if any(lb.text.casefold() == want for lb in p.labels):
            return 1
        return 2 if any(want in lb.text.casefold() for lb in p.labels) else 9
    return sorted((p for p in pages if rank(p) < 9), key=lambda p: (rank(p), p.index))


def page_by_title(pages: List[MapPage], title: str) -> Optional[MapPage]:
    return next((p for p in pages if p.title == title), None)
