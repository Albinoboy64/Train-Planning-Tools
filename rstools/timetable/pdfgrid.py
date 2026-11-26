"""Reading tables from a PDF's drawn grid lines (PDFium), shared by the Section 4 and TPR readers.

A table's cells are found from the lines drawn on the page rather than from where the text sits, so a cell
spanning several columns or rows (and text that wraps inside a cell) is read as one cell.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

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
