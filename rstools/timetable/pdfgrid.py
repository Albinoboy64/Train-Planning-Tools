"""Reading tables from a PDF's drawn grid lines (PDFium), shared by the Section 4 and TPR readers.

A table's cells are found from the lines drawn on the page rather than from where the text sits, so a cell
spanning several columns or rows (and text that wraps inside a cell) is read as one cell.
"""
from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

Line = Tuple[float, float, float]           # (position, start, end)


def text_in(tp, x0: float, y0: float, x1: float, y1: float) -> str:
    """The text inside a box on the page, on one line."""
    try:
        text = tp.get_text_bounded(left=x0, bottom=y0, right=x1, top=y1)
    except Exception:
        return ""
    return " ".join(text.replace("￾", "").replace("\x02", "-").split())


def segments(page, rects: bool = False) -> Tuple[List[Line], List[Line]]:
    """The thin drawn lines on a page: (horizontal lines as (y, x0, x1), vertical lines as (x, y0, y1)).
    Thin filled rectangles count as lines; with `rects`, the sides of larger drawn rectangles (cell borders)
    count too."""
    import pypdfium2.raw as R
    horizontal, vertical = [], []
    for obj in page.get_objects():
        if obj.type != R.FPDF_PAGEOBJ_PATH:
            continue
        left, bottom, right, top = obj.get_bounds()
        if top - bottom < 3 and right - left > 3:
            horizontal.append(((bottom + top) / 2, left, right))
        elif right - left < 3 and top - bottom > 3:
            vertical.append(((left + right) / 2, bottom, top))
        elif rects and right - left > 3 and top - bottom > 3:
            # a drawn rectangle (cell border): its four sides
            horizontal += [(bottom, left, right), (top, left, right)]
            vertical += [(left, bottom, top), (right, bottom, top)]
    return horizontal, vertical


def cluster(values: Sequence[float], tol: float = 2.5) -> List[float]:
    """Values within `tol` of each other merged into their average (edges drawn twice, rounding)."""
    out: List[List[float]] = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(g) / len(g) for g in out]


# --------------------------------------------------------------------------- text with its type and colour
@dataclass
class Run:
    """A piece of text as the PDF draws it: where, how big, how heavy and what colour."""
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float
    weight: int
    rgb: Tuple[int, int, int]
    deleted: bool = False           # green and struck through: wording the issue deleted

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _object_text(obj, tp) -> str:
    import pypdfium2.raw as R
    n = R.FPDFTextObj_GetText(obj.raw, tp.raw, None, 0)
    if n <= 2:
        return ""
    buf = (ctypes.c_ushort * (n // 2 + 1))()
    R.FPDFTextObj_GetText(obj.raw, tp.raw, buf, n)
    return "".join(chr(c) for c in buf[: n // 2 - 1]).replace("\ufffe", "").replace("\x02", "-")


def text_runs(page, horizontal: Optional[Sequence[Line]] = None) -> List[Run]:
    """Every piece of text on a page with its size, weight and colour. Green text crossed by a drawn line is
    marked `deleted` (Network Rail's convention for wording an issue removes); `horizontal` are the page's
    thin horizontal lines (from `segments`)."""
    import pypdfium2.raw as R
    tp = page.get_textpage()
    out: List[Run] = []
    for obj in page.get_objects():
        if obj.type != R.FPDF_PAGEOBJ_TEXT:
            continue
        text = _object_text(obj, tp)
        if not text.strip():
            continue
        left, bottom, right, top = obj.get_bounds()
        colour = [ctypes.c_uint() for _ in range(4)]
        R.FPDFPageObj_GetFillColor(obj.raw, *colour)
        size = ctypes.c_float()
        R.FPDFTextObj_GetFontSize(obj.raw, size)
        rgb = (colour[0].value, colour[1].value, colour[2].value)
        run = Run(left, bottom, right, top, text, round(size.value, 1),
                  R.FPDFFont_GetWeight(R.FPDFTextObj_GetFont(obj.raw)), rgb)
        if horizontal and rgb[1] > rgb[0] + 40 and rgb[1] > rgb[2] + 40:
            height = top - bottom
            run.deleted = any(bottom + 0.2 * height <= y <= top - 0.2 * height and x0 - 1 <= run.cx <= x1 + 1
                              for y, x0, x1 in horizontal)
        out.append(run)
    return out


def to_visual(runs: Sequence[Run], page) -> List[Run]:
    """Runs placed as the page is displayed. Section 4's pages are turned through 90 degrees: the text is drawn up
    the page, so it only reads left to right and top to bottom once the page's rotation is applied."""
    rot = page.get_rotation() % 360
    if rot == 0:
        return list(runs)
    out = []
    for r in runs:
        x0, y0, x1, y1 = rect_to_visual(page, r.x0, r.y0, r.x1, r.y1)
        out.append(replace(r, x0=x0, y0=y0, x1=x1, y1=y1))
    return out


def rect_to_visual(page, x0: float, y0: float, x1: float, y1: float) -> Tuple[float, float, float, float]:
    """A box in the page's drawing coordinates as (x0, y0, x1, y1) in the displayed page (origin bottom left)."""
    rot = page.get_rotation() % 360
    vw, vh = page.get_size()                    # the displayed size
    if rot == 90:                               # drawing (x, y) is displayed at (y, vh - x)
        return y0, vh - x1, y1, vh - x0
    if rot == 270:                              # displayed at (vw - y, x)
        return vw - y1, x0, vw - y0, x1
    if rot == 180:
        return vw - x1, vh - y1, vw - x0, vh - y0
    return x0, y0, x1, y1


def rect_from_visual(page, x0: float, y0: float, x1: float, y1: float) -> Tuple[float, float, float, float]:
    """The inverse of rect_to_visual: a box on the displayed page as (left, bottom, right, top) in drawing coordinates
    (what a PDF annotation's /Rect uses)."""
    rot = page.get_rotation() % 360
    vw, vh = page.get_size()
    if rot == 90:
        return vh - y1, x0, vh - y0, x1
    if rot == 270:
        return y0, vw - x1, y1, vw - x0
    if rot == 180:
        return vw - x1, vh - y1, vw - x0, vh - y0
    return x0, y0, x1, y1


def join_runs(runs: Sequence[Run]) -> str:
    """The text of runs on one line, left to right: a space where the PDF has one (or a gap), none where the
    runs only touch (kerning splits a word like 'Ju' 'ne')."""
    out = ""
    prev: Optional[Run] = None
    for r in sorted(runs, key=lambda r: r.x0):
        t = r.text.strip()
        if not t:
            continue
        if prev is not None:
            gap = r.x0 - prev.x1
            if (prev.text.endswith(" ") or r.text.startswith(" ") or gap > 0.2 * max(prev.size, 6)) \
                    and not out.endswith(" "):
                out += " "
        out += t
        prev = r
    return out


def lines_of(runs: Sequence[Run]) -> List[List[Run]]:
    """Runs grouped into lines, top of the page first, each line left to right."""
    out: List[List[Run]] = []
    for r in sorted(runs, key=lambda r: (-r.cy, r.x0)):
        if out and abs(out[-1][0].cy - r.cy) <= max(2.0, 0.45 * r.size):
            out[-1].append(r)
        else:
            out.append([r])
    return [sorted(line, key=lambda r: r.x0) for line in out]


def line_text(line: Sequence[Run]) -> str:
    return " ".join(join_runs(line).split())


def text_of_box(runs: Sequence[Run], x0: float, y0: float, x1: float, y1: float) -> str:
    """The text of the runs whose centre is inside a box (a table cell), lines joined with a space."""
    inside = [r for r in runs if x0 <= r.cx <= x1 and y0 <= r.cy <= y1]
    return " ".join(" ".join(line_text(line) for line in lines_of(inside)).split())


# --------------------------------------------------------------------------- running headers and footers
def _signature(text: str) -> str:
    return " ".join(re.sub(r"\d+", "#", text).lower().split())


def _region(y: float, height: float) -> str:
    return "t" if y > height * 0.85 else "b" if y < height * 0.12 else ""


@dataclass
class Furniture:
    """The running header and footer of a document: lines repeated on most pages in the top or bottom of the page
    (whatever the page's size: a landscape page's header is lower than a portrait page's)."""
    signatures: Set[Tuple[str, str]]        # (text with digits ignored, 't' top / 'b' bottom)
    start: int                              # first page with them (earlier pages are a covering note)
    info: Dict[str, str]                    # what they say: version, date, route...

    def is_furniture(self, text: str, y: float, height: float) -> bool:
        region = _region(y, height)
        return bool(region) and (_signature(text), region) in self.signatures


def find_furniture(pages: Sequence[Sequence[List[Run]]], heights: Sequence[float], share: float = 0.4) -> Furniture:
    """Find the lines that repeat (digits ignored) in the top or bottom of at least `share` of the pages: the running
    header and footer. `pages[i]` are page i's lines (see `lines_of`)."""
    from collections import Counter
    count: Counter = Counter()
    for lines, h in zip(pages, heights):
        seen = set()
        for line in lines:
            region = _region(line[0].cy, h)
            if region:
                seen.add((_signature(line_text(line)), region))
        count.update(seen)
    need = max(2, int(len(pages) * share))
    signatures = {k for k, n in count.items() if n >= need and k[0]}
    found = Furniture(signatures, 0, {})
    start = 0
    for i, (lines, h) in enumerate(zip(pages, heights)):
        # the first page with most of the header and footer lines (a covering note may repeat one line of its own)
        hits = {(_signature(line_text(line)), _region(line[0].cy, h)) for line in lines
                if found.is_furniture(line_text(line), line[0].cy, h)}
        if signatures and len(hits) * 2 >= len(signatures):
            start = i
            break
    info: Dict[str, str] = {}
    if signatures and start < len(pages):
        top = [line_text(line) for line in pages[start]
               if _region(line[0].cy, heights[start]) == "t"
               and found.is_furniture(line_text(line), line[0].cy, heights[start])]
        head = " | ".join(top)
        patterns = (("Version", r"Version\s*:?\s*(\d[\d .]*\d|\d)"),
                    ("Date", r"Date\s*:?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})"))
        for key, pattern in patterns:
            m = re.search(pattern, head)
            if m:
                info[key] = m.group(1).replace(" ", "") if key == "Version" else m.group(1)
        info["Header"] = head
    return Furniture(signatures, start, info)
