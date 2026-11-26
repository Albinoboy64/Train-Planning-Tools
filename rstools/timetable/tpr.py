"""Network Rail Timetable Planning Rules (TPR) PDFs: every table and paragraph, for comparing two sets.

The TPR is mostly tables (sectional running times, headways, junction margins, dwells, platform rules...) under
numbered section headings, with notes and paragraphs between them. Tables are read from their drawn grid lines
(PDFium): each band between two horizontal rules is a row, cut into cells by the vertical rules crossing it. A
table's first row is its heading row; a table continued on the next page under the same heading row and title
carries on as the same table. Text outside the tables is kept as paragraphs under the section it falls in.
Running page headers and footers (the top and bottom strips of each page, 'Page n of m') are dropped.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from .pdfgrid import cluster, segments, text_in

_HEADING = re.compile(r"^(?:\d+(?:\.\d+){0,3}\.?|[A-Z]\d*(?:\.\d+)*)\s+[A-Z][^.]{2,120}$")
_PAGE_NO = re.compile(r"\bpage\s+\d+(?:\s+of\s+\d+)?\b", re.I)
MARGIN = 0.06                   # the top and bottom strips of a page hold the running header and footer


class TPRError(Exception):
    pass


@dataclass
class Table:
    section: str
    title: str
    headers: List[str]
    rows: List[List[str]] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)


@dataclass
class TPRDoc:
    files: List[str] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    paragraphs: List[Tuple[str, str, int]] = field(default_factory=list)    # (section, text, page)
    warnings: List[str] = field(default_factory=list)


def read_tpr(paths: Sequence[str], log=lambda m: None) -> TPRDoc:
    doc = TPRDoc()
    for path in paths:
        log(f"Reading {os.path.basename(path)}")
        before = (len(doc.tables), len(doc.paragraphs))
        _read_pdf(path, doc)
        doc.files.append(path)
        tables, paras = len(doc.tables) - before[0], len(doc.paragraphs) - before[1]
        log(f"  {tables} table(s), {paras} paragraph(s)")
        if not tables and not paras:
            doc.warnings.append(f"Nothing could be read from '{os.path.basename(path)}' (a scanned PDF?).")
    return doc


def _lines_of(tp, page_w: float, y0: float, y1: float) -> List[Tuple[float, str]]:
    """Lines of text between y0 and y1 (top first), as (y, text): PDFium's text runs, joined by line."""
    out: List[Tuple[float, str]] = []
    try:
        n = tp.count_rects()
    except Exception:
        return out
    rows: List[Tuple[float, float, str]] = []           # (y, x, text)
    for i in range(n):
        try:
            left, bottom, right, top = tp.get_rect(i)
        except Exception:
            continue
        cy = (bottom + top) / 2
        if not (y0 <= cy <= y1):
            continue
        text = text_in(tp, left, bottom, right, top)
        if text:
            rows.append((cy, left, text))
    rows.sort(key=lambda r: (-r[0], r[1]))
    line: List[Tuple[float, float, str]] = []
    for r in rows:
        if line and abs(line[0][0] - r[0]) > 3:
            out.append((line[0][0], " ".join(t for _y, _x, t in sorted(line, key=lambda q: q[1]))))
            line = []
        line.append(r)
    if line:
        out.append((line[0][0], " ".join(t for _y, _x, t in sorted(line, key=lambda q: q[1]))))
    return out


def _read_pdf(path: str, doc: TPRDoc):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise TPRError("The PDF reader (pypdfium2) is not available.")
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception as exc:
        raise TPRError(f"'{os.path.basename(path)}' could not be opened as a PDF ({exc}).")
    section = ""
    last: Optional[Table] = None
    name = os.path.basename(path)
    try:
        for pno in range(len(pdf)):
            page = pdf[pno]
            w, h = page.get_size()
            tp = page.get_textpage()
            top, bottom = h * (1 - MARGIN), h * MARGIN
            horiz, vert = segments(page, rects=True)
            grids = _grids(horiz, vert, top, bottom)
            # text outside the tables: headings and paragraphs, in reading order
            boxes = [(g[0][0], g[0][-1], g[1]) for g in grids]          # (lowest y, highest y, x span)
            items: List[Tuple[float, str, Any]] = []
            for y, text in _lines_of(tp, w, bottom, top):
                if any(lo - 1 <= y <= hi + 1 for lo, hi, _x in boxes) or _PAGE_NO.search(text):
                    continue
                items.append((y, "text", text))
            for g in grids:
                items.append((g[0][-1], "grid", g))
            items.sort(key=lambda it: -it[0])
            above = ""
            para: List[str] = []
            for _y, kind, val in items:
                if kind == "text":
                    text = str(val)
                    if _HEADING.match(text) and len(text) < 130:
                        _flush(doc, section, para, pno + 1)
                        section, above = text, ""
                        continue
                    para.append(text)
                    above = text
                    continue
                ys, xs = val
                rows = _grid_rows(tp, ys, xs, vert)
                if not rows:
                    continue
                headers, body = rows[0], rows[1:]
                title = above if above and len(above) < 160 else ""
                if title and para and para[-1] == title:
                    para.pop()                                    # the table's title, not a paragraph
                _flush(doc, section, para, pno + 1)
                if (last is not None and last.headers == headers and (not title or title == last.title)
                        and last.section == section):
                    last.rows += body                             # continued from the page before
                    last.pages.append(pno + 1)
                elif last is not None and not title and len(headers) == len(last.headers) and pno + 1 in (
                        last.pages[-1], last.pages[-1] + 1) and last.section == section and _no_header(headers):
                    last.rows += rows                             # continued without repeating the heading row
                    last.pages.append(pno + 1)
                else:
                    last = Table(section, title, headers, body, [pno + 1])
                    doc.tables.append(last)
                above = ""
            _flush(doc, section, para, pno + 1)
    finally:
        pdf.close()
    for t in doc.tables:
        t.pages = sorted(set(t.pages))
    if not doc.tables and not doc.paragraphs:
        doc.warnings.append(f"{name}: no text found")


def _flush(doc: TPRDoc, section: str, para: List[str], page: int):
    """The paragraph gathered so far, under its section."""
    if para:
        doc.paragraphs.append((section, " ".join(para), page))
        para.clear()


def _no_header(cells: List[str]) -> bool:
    """A row that is data, not a heading row (it has digits in most cells)."""
    digits = sum(1 for c in cells if re.search(r"\d", c))
    return digits >= max(1, len(cells) // 2)


def _grids(horiz, vert, top: float, bottom: float):
    """Each table on the page: (row edge ys from bottom to top, (x0, x1)). Tables are runs of horizontal rules of
    about the same width, close together."""
    raw = [(y, x0, x1) for y, x0, x1 in horiz if bottom <= y <= top]
    # pieces of one rule (a rule drawn cell by cell) joined end to end
    rules = []
    for y in cluster([r[0] for r in raw]):
        spans = sorted((x0, x1) for ry, x0, x1 in raw if abs(ry - y) <= 2.5)
        cur = list(spans[0])
        for x0, x1 in spans[1:]:
            if x0 <= cur[1] + 3:
                cur[1] = max(cur[1], x1)
            else:
                rules.append((y, cur[0], cur[1]))
                cur = [x0, x1]
        rules.append((y, cur[0], cur[1]))
    rules = [r for r in rules if r[2] - r[1] > 20]
    if not rules:
        return []
    # widest rules first: each starts a table or joins the table above / below whose width holds it
    tables: List[List] = []                 # [x0, x1, [ys]]
    for y, x0, x1 in sorted(rules, key=lambda r: -(r[2] - r[1])):
        home = None
        for t in tables:
            if t[0] - 4 <= x0 and x1 <= t[1] + 4 and min(abs(y - v) for v in t[2]) <= 120:
                home = t
                break
        if home is None:
            tables.append([x0, x1, [y]])
        else:
            home[2].append(y)
    grids = []
    for x0, x1, ys in tables:
        ys = cluster(ys)
        # split where the gap is far bigger than a row and no column rule crosses it (two tables)
        run = [ys[0]]
        for y in ys[1:]:
            crossing = any(x0 - 4 <= vx <= x1 + 4 and vb <= run[-1] + 1 and vt >= y - 1 for vx, vb, vt in vert)
            if y - run[-1] > 120 and not crossing:
                if len(run) >= 2:
                    grids.append((run, (x0, x1)))
                run = [y]
            else:
                run.append(y)
        if len(run) >= 2:
            grids.append((run, (x0, x1)))
    return grids


def _grid_rows(tp, ys: List[float], xs: Tuple[float, float], vert) -> List[List[str]]:
    """The rows of one table, top first: each band cut at the vertical rules that cross it."""
    x0, x1 = xs
    out = []
    for lo, hi in reversed(list(zip(ys, ys[1:]))):
        if hi - lo < 4:
            continue
        mid = (lo + hi) / 2
        edges = cluster([vx for vx, vb, vt in vert if vb - 1 <= mid <= vt + 1 and x0 - 4 <= vx <= x1 + 4])
        if len(edges) < 2:
            edges = [x0, x1]
        cells = [text_in(tp, a + 0.5, lo + 0.5, b - 0.5, hi - 0.5) for a, b in zip(edges, edges[1:])]
        if any(cells):
            out.append(cells)
    return out
