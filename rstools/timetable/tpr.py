"""Network Rail Timetable Planning Rules (TPR) PDFs: every table and paragraph, for comparing two sets.

A route TPR is a numbered document (1 Introduction ... 5 Running Times, Margins and Allowances ... appendices) of
paragraphs and ruled tables, with the tables of a line of route under its title ('LN3340 ALREWAS (INCLUSIVE) TO
WICHNOR JN'). It starts after a covering commentary (Network Rail's own summary of what changed), each page has a
running header and footer, and the contents pages list every heading with a page number.

Reading, page by page (PDFium, text with its size and colour):
* the covering commentary pages, the running header / footer (found by repetition) and the contents pages are left
  out - the header's version and date are kept for the report as information;
* a line in larger type than the body starts a numbered section; text below it is paragraphs until a table;
* a table is the band of horizontal rules with the vertical rules crossing it: each row is cut into cells whose text
  is the runs inside them; a table carried on to the next page under the same heading row is one table;
* wording the issue deleted (green and struck through) is ignored, and the thin change bars Network Rail draws in the
  right margin are not table lines.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .pdfgrid import Run, cluster, find_furniture, line_text, lines_of, segments, text_of_box, text_runs

HEADING_SIZE = 13.5                 # body text is 10 pt; headings are 14, 15 and 16 pt
_LEADER = re.compile(r"\.{3,}\s*\d+\s*$")
_CONTINUED = re.compile(r"\s*\(?continued\W*$", re.I)
TITLE_GAP = 30.0                    # a table's title is the line this close above it


class TPRError(Exception):
    pass


@dataclass
class Table:
    section: str
    title: str
    headers: List[str]
    rows: List[List[str]] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)
    source: str = ""                    # the file it was read from
    refs: List[Tuple] = field(default_factory=list)     # (path, page index, rect) of each row, as rows


@dataclass
class TPRDoc:
    files: List[str] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    paragraphs: List[Tuple[str, str, int]] = field(default_factory=list)    # (section, text, page)
    para_refs: List[List[Tuple]] = field(default_factory=list)              # each paragraph's (path, page index, rect)
    warnings: List[str] = field(default_factory=list)
    info: List[Tuple[str, str]] = field(default_factory=list)               # (file, what its header says)
    skipped: List[str] = field(default_factory=list)                        # pages left out, and why
    deleted: int = 0                                                        # struck-through pieces ignored


def read_tpr(paths: Sequence[str], log=lambda m: None) -> TPRDoc:
    doc = TPRDoc()
    for path in paths:
        log(f"Reading {os.path.basename(path)}")
        before = (len(doc.tables), len(doc.paragraphs))
        _read_pdf(path, doc)
        doc.files.append(path)
        for t in doc.tables[before[0]:]:
            t.source = os.path.basename(path)
        tables, paras = len(doc.tables) - before[0], len(doc.paragraphs) - before[1]
        log(f"  {tables} table(s), {paras} paragraph(s)")
        if not tables and not paras:
            doc.warnings.append(f"Nothing could be read from '{os.path.basename(path)}' (a scanned PDF?).")
    return doc


class _State:
    def __init__(self):
        self.section = ""
        self.path: Dict[int, str] = {}          # heading text at each level (16 pt = 1, 15 pt = 2, 14 pt = 3)
        self.level = 3
        self.heading_y: Optional[float] = None
        self.heading_size = 0.0
        self.last_was_heading = False
        self.last: Optional[Table] = None
        self.para: List[str] = []
        self.para_boxes: Dict[int, List[float]] = {}     # page index -> box of the paragraph's lines on it
        self.file = ""
        self.para_y = 0.0
        self.above = ""                 # the last text line (a table's title when it is close above one)
        self.above_y = 0.0


def _flush(doc: TPRDoc, st: _State, page: int):
    if st.para:
        doc.paragraphs.append((st.section, " ".join(st.para), page))
        doc.para_refs.append([(st.file, pg, tuple(box)) for pg, box in sorted(st.para_boxes.items())])
        st.para.clear()
        st.para_boxes.clear()


def _read_pdf(path: str, doc: TPRDoc):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise TPRError("The PDF reader (pypdfium2) is not available.")
    from rstools import limits
    try:
        limits.check_pdf(path)
    except OSError as exc:
        raise TPRError(str(exc))
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception as exc:
        raise TPRError(f"'{os.path.basename(path)}' could not be opened as a PDF ({exc}).")
    try:
        limits.check_pages(len(pdf), path)
    except limits.TooLargeError as exc:
        pdf.close()
        raise TPRError(str(exc))
    name = os.path.basename(path)
    try:
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            horiz, vert = segments(page)
            width, height = page.get_size()
            pages.append((text_runs(page, horiz), horiz, vert, width, height))
        furniture = find_furniture([lines_of([r for r in runs if not r.deleted]) for runs, *_ in pages],
                                   [p[4] for p in pages])
        if furniture.info:
            doc.info.append((name, "; ".join(f"{k} {v}" for k, v in furniture.info.items() if k != "Header")
                             + (f" ({furniture.info['Header']})" if furniture.info.get("Header") else "")))
        if furniture.start:
            doc.skipped.append(f"{name}: pages 1-{furniture.start} (covering commentary)")
        st = _State()
        st.file = path
        for pno in range(furniture.start, len(pages)):
            _page(doc, st, name, pno, pages[pno], furniture)
        _flush(doc, st, len(pages))
    finally:
        pdf.close()
    for t in doc.tables:
        t.pages = sorted(set(t.pages))


def _page(doc: TPRDoc, st: _State, name: str, pno: int, data, furniture):
    runs, horiz, vert, width, height = data
    live = [r for r in runs if not r.deleted]
    doc.deleted += len(runs) - len(live)
    top, bottom = height, 0.0
    body: List[List[Run]] = []
    content: List[Run] = []
    for line in lines_of(live):
        if furniture.is_furniture(line_text(line), line[0].cy, height):
            if line[0].cy > height / 2:
                top = min(top, min(r.y0 for r in line))
            else:
                bottom = max(bottom, max(r.y1 for r in line))
            continue
        body.append(line)
        content += line
    leaders = sum(1 for line in body if _LEADER.search(line_text(line)))
    if leaders >= 5 and leaders >= 0.35 * len(body):
        doc.skipped.append(f"{name}: page {pno + 1} (contents)")
        return
    # the table lines: not the strike-through lines of deleted text, not the change bars in the margin
    struck = [r for r in runs if r.deleted]
    rules = [(y, x0, x1) for y, x0, x1 in horiz
             if bottom < y < top and not any(r.y0 <= y <= r.y1 and r.x0 - 1 <= (x0 + x1) / 2 <= r.x1 + 1
                                             for r in struck)]
    limit = max((x1 for _y, x0, x1 in rules if x1 - x0 > 40), default=width - 45) + 3
    bars_out = [v for v in vert if v[0] <= limit and bottom < v[1] + 1 and v[2] - 1 < top]
    grids = _grids(rules, bars_out, top, bottom)
    boxes = [(xs[0] - 2, ys[0] - 1, xs[1] + 2, ys[-1] + 1) for ys, xs in grids]
    items: List[Tuple[float, str, Any]] = []
    for line in body:
        cx, cy = line[0].cx, line[0].cy
        if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes):
            continue
        items.append((cy, "line", line))
    for ys, xs in grids:
        items.append((ys[-1], "grid", (ys, xs)))
    items.sort(key=lambda it: -it[0])
    page = pno + 1
    for y, kind, val in items:
        if kind == "line":
            text = line_text(val)
            size = max(r.size for r in val)
            if size >= HEADING_SIZE:
                _flush(doc, st, page)
                continued = (st.heading_y is not None and st.heading_size == size
                             and st.heading_y - y < 1.8 * size and st.last_was_heading)
                if continued:
                    st.path[st.level] += " " + text
                else:
                    st.level = 1 if size >= 15.5 else 2 if size >= 14.5 else 3
                    st.path[st.level] = text
                    for deeper in [k for k in st.path if k > st.level]:
                        del st.path[deeper]
                st.section = " > ".join(st.path[k] for k in sorted(st.path))
                st.heading_y, st.heading_size, st.last_was_heading = y, size, True
                st.above = ""
                continue
            st.last_was_heading = False
            if st.para and st.para_y - y > 1.7 * max(size, 9):
                _flush(doc, st, page)
            st.para.append(text)
            lb = [min(r.x0 for r in val), min(r.y0 for r in val), max(r.x1 for r in val), max(r.y1 for r in val)]
            old = st.para_boxes.get(pno)
            st.para_boxes[pno] = lb if old is None else [min(old[0], lb[0]), min(old[1], lb[1]),
                                                         max(old[2], lb[2]), max(old[3], lb[3])]
            st.para_y, st.above, st.above_y = y, text, y
            continue
        st.last_was_heading = False
        ys, xs = val
        rects: List[Tuple[float, float, float, float]] = []
        rows = _grid_rows(content, ys, xs, bars_out, rects)
        if not rows:
            continue
        refs = [(st.file, pno, r) for r in rects]
        headers, rest = rows[0], rows[1:]
        title = st.above if st.above and st.above_y - ys[-1] <= TITLE_GAP and _is_title(st.above) else ""
        if len(headers) == 1 and rest and max(len(r) for r in rest) > 1:
            # a first row that is one merged cell (a title, with its column names run together) is not a heading
            # row: it names the table, and the columns are numbered
            title, headers, rest = " ".join(x for x in (title, headers[0]) if x), [], rows[1:]
        if title and st.para and st.para[-1] == st.above:
            st.para.pop()                                           # the table's title, not a paragraph
        _flush(doc, st, page)
        last = st.last
        if (last is not None and last.section == st.section and last.headers == headers
                and (not title or _CONTINUED.sub("", title) == _CONTINUED.sub("", last.title))):
            last.rows += rest                                       # carried on from the page before
            last.refs += refs[1:]
            last.pages.append(page)
        elif (last is not None and not title and last.section == st.section and len(headers) == len(last.headers)
              and page - last.pages[-1] <= 1 and _no_header(headers)):
            last.rows += rows                                       # carried on without its heading row
            last.refs += refs
            last.pages.append(page)
        else:
            st.last = Table(st.section, title, headers, rest, [page], refs=refs[1:])
            doc.tables.append(st.last)
        st.above = ""


def _is_title(text: str) -> bool:
    """A line that can name the table under it ('LN3340 ALREWAS TO WICHNOR JN', 'Table 5.2 Headways')."""
    return 0 < len(text) <= 120 and not text.endswith(".")


def _no_header(cells: List[str]) -> bool:
    """A row that is data, not a heading row (digits in most cells)."""
    return sum(1 for c in cells if re.search(r"\d", c)) >= max(1, len(cells) // 2)


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


def _grid_rows(runs: Sequence[Run], ys: List[float], xs: Tuple[float, float], vert,
               rects: Optional[list] = None) -> List[List[str]]:
    """The rows of one table, top first: each band cut at the vertical rules that cross it, its cells' text from the
    text runs inside them."""
    x0, x1 = xs
    out = []
    for lo, hi in reversed(list(zip(ys, ys[1:]))):
        if hi - lo < 4:
            continue
        mid = (lo + hi) / 2
        edges = cluster([vx for vx, vb, vt in vert if vb - 1 <= mid <= vt + 1 and x0 - 4 <= vx <= x1 + 4])
        if len(edges) < 2:
            edges = [x0, x1]
        cells = [text_of_box(runs, a, lo, b, hi) for a, b in zip(edges, edges[1:])]
        if any(cells):
            out.append(cells)
            if rects is not None:
                rects.append((x0, lo, x1, hi))
    return out
