"""Network Rail Engineering Access Statement, Section 4 (Standard Possession Opportunities): reader and the check of
a timetable (Attune XML) against it.

The Section 4 PDF is a table per line of route ('SO110 VICTORIA EASTERN TO RAMSGATE'): one row group per section
('Shepherds Lane Jn and Herne Hill 110.3') with a row for each kind of night (WEEK END, SUN/MON, MID WEEK), a column
for each timetable period (e.g. Periods A and B 13.12.2026 to 14.02.2027) and a REMARKS column. A possession that
applies to several periods is one cell spanning their columns, so the cells are found from the table's drawn grid
lines, not from where the text sits. Each cell holds one or more windows ('0140 T-F to 0350 T-F') and what is
blocked ('Down and Up Chatham Main BLOCKED').

The check finds the trains in the XML that run over a section (they call at or pass both of its ends) at a time
inside one of its possession windows, on a day and in a period both apply to.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from rstools.days import DAY_LABELS as DAY_SHORT

from . import s4lines as S4L
from .s4lines import line_codes, verdict as line_verdict
from .prints import PrintError
from .s4remarks import EXEMPT as R_EXEMPT
from .pdfgrid import (cluster, find_furniture, line_text, lines_of, rect_from_visual, rect_to_visual, segments,
                      text_in, text_runs, to_visual)

DAY_CODES = {"m": 0, "mo": 0, "mon": 0, "t": 1, "tu": 1, "tue": 1, "tues": 1, "w": 2, "we": 2, "wed": 2,
             "th": 3, "thu": 3, "thur": 3, "thurs": 3, "f": 4, "fr": 4, "fri": 4, "s": 5, "sa": 5, "sat": 5,
             "su": 6, "sun": 6}
WEEK = 7 * 1440
_WINDOW = re.compile(r"(\d{2})[.:]?(\d{2})\s*([A-Za-z]{1,5}(?:\s*[-/]\s*[A-Za-z]{1,5})?)\s+to\s+"
                     r"(\d{2})[.:]?(\d{2})\s*([A-Za-z]{1,5}(?:\s*[-/]\s*[A-Za-z]{1,5})?)\b")
_SECTION_NO = re.compile(r"\b(\d{2,4}\.\d{1,3}[a-z]?)\b")
_LINE_WORDS = re.compile(r"\b(fast|slow|main|relief|local|suburban|electric|loop|platforms?|reversible|goods|chatham|"
                         r"thameslink|quarry|hendon|bay|siding|no\.?\s*\d|[a-f]\s*&\s*[a-f]|[a-f] lines?)\b", re.I)
_ROUTE = re.compile(r"^\s*([A-Z]{2}\d{3,4}[A-Z]?(?:\s*/\s*[A-Z]{2}\d{3,4}[A-Z]?)*)\s+(.+?)\s*$")
_DATES = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})\s*to\s*(\d{1,2})[./](\d{1,2})[./](\d{4})")


class Section4Error(Exception):
    pass


@dataclass
class Period:
    name: str                   # 'Periods A and B'
    start: date
    end: date


@dataclass
class Window:
    start: int                  # minutes from Monday 00:00
    end: int
    text: str                   # '0140 Tue to 0350 Tue'


@dataclass
class Possession:
    route: str                  # 'SO110 VICTORIA EASTERN TO RAMSGATE'
    section: str                # 'Shepherds Lane Jn and Herne Hill'
    number: str                 # '110.3'
    ends: Tuple[str, ...]       # ('Shepherds Lane Jn', 'Herne Hill'), or one place
    night: str                  # 'WEEK END' / 'SUN/MON' / 'MID WEEK'
    periods: List[Period]
    windows: List[Window]
    blocked: str                # 'Down and Up Chatham Main BLOCKED'
    remarks: str
    source: str                 # file and page
    refs: List[Tuple] = field(default_factory=list)     # (path, page index, (left, bottom, right, top)) in the PDF

    @property
    def available(self) -> str:
        """'8 weeks a year' where the possession is not every week ('8 w.p.a'), else 'Every week'."""
        m = re.search(r"(\d+)\s*w\.?\s*p\.?\s*a\b", self.blocked + " " + self.remarks, re.I)
        return f"{m.group(1)} weeks a year" if m else "Every week"

    @property
    def every_line(self) -> bool:
        """The possession blocks every line of the section (not only, say, the slow lines)."""
        b = self.blocked.lower()
        return bool(re.search(r"\ball\b", b)) or not _LINE_WORDS.search(b)

    @property
    def direction(self) -> str:
        """'Down' / 'Up' when only that line is blocked, else ''."""
        b = self.blocked.lower()
        down, up = bool(re.search(r"\b(down|dn)\b", b)), bool(re.search(r"\bup\b", b))
        if re.search(r"\ball\b|\bboth\b|reversible", b) or down == up:
            return ""
        return "Down" if down else "Up"


@dataclass
class RouteNote:
    """Text outside the possession tables: a route's timetable construction notes or its NOTES."""
    route: str                  # 'LN101 KING’S CROSS TO SHAFTHOLME JN'
    kind: str                   # 'Notes' / 'Timetable construction notes' / 'Other text'
    scope: str                  # construction notes: the stretch of line they are for
    text: str
    source: str                 # file and page
    refs: List[Tuple] = field(default_factory=list)


@dataclass
class Statement:
    possessions: List[Possession] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[RouteNote] = field(default_factory=list)            # read from PDFs (saved rule sets have none)
    info: List[Tuple[str, str]] = field(default_factory=list)       # (file, what its page header says)


# --------------------------------------------------------------------------- reading the PDF
def _days(code: str) -> List[int]:
    """'T-F' -> [1, 2, 3, 4]; 'Sun' -> [6]; 'Th-S' -> [3, 4, 5]; '' / unknown -> []."""
    parts = [p.strip().lower() for p in re.split(r"\s*[-/]\s*", code.strip()) if p.strip()]
    found = [DAY_CODES.get(p) for p in parts]
    if not found or any(n is None for n in found):
        return []
    nums = [n for n in found if n is not None]
    if len(nums) == 1:
        return nums
    a, b = nums[0], nums[-1]
    return list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))


def parse_windows(text: str) -> List[Window]:
    """Every '0140 T-F to 0350 T-F' in a cell as windows (one per day: Tue, Wed, Thu, Fri)."""
    out = []
    for m in _WINDOW.finditer(text):
        h1, m1, d1, h2, m2, d2 = m.groups()
        t1, t2 = int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)
        a, b = _days(d1), _days(d2)
        if not a or not b or t1 >= 1440 or t2 >= 1440:
            continue
        if len(a) == len(b):                                  # 'T-F to T-F', 'Sun to Sun', 'T to W'
            pairs = list(zip(a, b))
        else:
            pairs = [(x, x) for x in a]
        for x, y in pairs:
            start = x * 1440 + t1
            end = y * 1440 + t2
            if end <= start:
                end += WEEK if y == x else (WEEK if end + WEEK - start < 1440 * 2 else 0)
            if end <= start:
                continue
            out.append(Window(start, end, f"{h1}{m1} {DAY_SHORT[x]} to {h2}{m2} {DAY_SHORT[y]}"))
    return out


_text_in = text_in              # the shared grid reader (pdfgrid), under the names used here
_segments = segments
_cluster = cluster


def read_statement(paths: Sequence[str], log=lambda m: None) -> Statement:
    st = Statement()
    for path in paths:
        log(f"Reading {os.path.basename(path)}")
        before = len(st.possessions)
        _read_isolated(path, st)
        st.files.append(path)
        found = len(st.possessions) - before
        if not found:
            st.warnings.append(f"No Section 4 possessions were found in '{os.path.basename(path)}'. Use Network "
                               "Rail's Engineering Access Statement Section 4 (Standard Possession Opportunities) PDF.")
        else:
            log(f"  {found} possession row(s)")
    return st


def _read_one(path: str, limit_values=None) -> Statement:
    from rstools import limits
    limits.use(limit_values)                     # the same limits as the app (a helper process starts afresh)
    one = Statement()
    _read_pdf(path, one)
    return one


def _read_isolated(path: str, st: Statement):
    """_read_pdf in a helper process (PDFium is native code: see rstools.isolate)."""
    from rstools.isolate import ReaderCrashed, run
    try:
        from rstools import limits
        one = run(_read_one, path, limits.current(), name=f"'{os.path.basename(path)}'")
    except ReaderCrashed as exc:
        raise Section4Error(str(exc))
    st.possessions += one.possessions
    st.warnings += one.warnings
    st.notes += one.notes
    st.info += one.info


def _read_pdf(path: str, st: Statement):
    boxes: Dict[int, Tuple[float, float, float, float]] = {}
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise Section4Error("The PDF reader (pypdfium2) is not available.")
    from rstools import limits
    try:
        limits.check_pdf(path)
    except OSError as exc:
        raise Section4Error(str(exc))
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception as exc:
        raise Section4Error(f"'{os.path.basename(path)}' could not be opened as a PDF ({exc}).")
    try:
        limits.check_pages(len(pdf), path)
    except limits.TooLargeError as exc:
        pdf.close()
        raise Section4Error(str(exc))
    route, section, number = "", "", ""
    ends: Tuple[str, ...] = ()
    known: Dict[str, str] = {}             # route number ('1110') -> its title, for tables that start mid-page
    try:
        for pno in range(len(pdf)):
            page = pdf[pno]
            tp = page.get_textpage()
            cols, rows = _segments(page)
            if not cols or not rows:
                continue
            # the header row: the band holding 'Period'
            row_x = _cluster([x for x, _b, _t in rows])
            header = None
            for x0, x1 in zip(row_x, row_x[1:]):
                txt = _text_in(tp, x0, 0, x1, 2000)
                if re.search(r"\bPeriods?\b", txt) and "SECTION" in txt.upper():
                    header = (x0, x1)
                    break
            if header is None:
                continue
            hx0, hx1 = header
            mid = (hx0 + hx1) / 2
            edges = _cluster([y for y, l, r in cols if l - 1 <= mid <= r + 1])
            if len(edges) < 4:
                continue
            cells = list(zip(edges, edges[1:]))
            titles = [_text_in(tp, hx0, a, hx1, b) for a, b in cells]
            try:
                first = next(i for i, t in enumerate(titles) if re.search(r"Period", t))
                last = next(i for i, t in enumerate(titles) if re.search(r"REMARKS", t, re.I))
            except StopIteration:
                continue
            periods: List[Tuple[Period, float, float]] = []
            for (a, b), t in zip(cells[first:last], titles[first:last]):
                m = _DATES.search(t)
                if not m:
                    continue
                d = [int(v) for v in m.groups()]
                name = re.sub(r"\s+", " ", t[:m.start()]).strip() or "Period"
                if name.upper().startswith("SECTION"):
                    name = name[7:].strip()
                periods.append((Period(name, date(d[2], d[1], d[0]), date(d[5], d[4], d[3])), a, b))
            if not periods:
                continue
            p_lo, p_hi = periods[0][1], periods[-1][2]
            sec_lo, sec_hi = cells[0][0], cells[0][1]           # SECTION column
            day_lo, day_hi = cells[first - 1] if first >= 2 else (cells[0][1], p_lo)
            if first < 2:            # the header's SECTION cell also covers the night column: split from the body
                inner = _cluster([y for y, l, r in cols if l > hx1 - 1 and sec_lo + 5 < y < p_lo - 5])
                if inner:
                    sec_hi, day_lo, day_hi = inner[0], inner[0], p_lo
            rem_lo, rem_hi = cells[last]
            # the route title above the table
            route = _route_title(tp, hx0) or route         # a table without its own title continues the last
            try:
                _by_number(_titles(tp.get_text_range()), known)     # titles further down the page too
            except Exception:
                pass
            # body rows: bands between row edges that cross the period columns
            body = sorted({round(x, 1) for x, b, t in rows if b <= (p_lo + p_hi) / 2 <= t and x > hx1 - 1})
            body = _cluster(body)
            sec_edges = _cluster([x for x, b, t in rows if b <= (sec_lo + sec_hi) / 2 <= t and x > hx1 - 1])
            rem_edges = _cluster([x for x, b, t in rows if b <= (rem_lo + rem_hi) / 2 <= t and x > hx1 - 1])
            day_edges = _cluster([x for x, b, t in rows if b <= (day_lo + day_hi) / 2 <= t and x > hx1 - 1])
            if body:
                boxes[pno] = (min(hx0, body[0]) - 2, edges[0] - 2, max(hx1, body[-1]) + 2, edges[-1] + 2)
            for x0, x1 in zip(body, body[1:]):
                if x1 - x0 < 4:
                    continue
                xm = (x0 + x1) / 2
                s_cell = next(((a, b) for a, b in zip(sec_edges, sec_edges[1:]) if a <= xm <= b), None)
                if s_cell:
                    stext = _text_in(tp, s_cell[0], sec_lo, s_cell[1], sec_hi)
                    if stext:
                        section, number, ends = _section(stext)
                r_cell = next(((a, b) for a, b in zip(rem_edges, rem_edges[1:]) if a <= xm <= b), None)
                remarks = _text_in(tp, r_cell[0], rem_lo, r_cell[1], rem_hi) if r_cell else ""
                d_cell = next(((a, b) for a, b in zip(day_edges, day_edges[1:]) if a <= xm <= b), (x0, x1))
                night = _night(_text_in(tp, d_cell[0], day_lo, d_cell[1], day_hi))     # can span two rows
                if not section or not night:
                    continue
                splits = _cluster([y for y, l, r in cols if l - 1 <= xm <= r + 1 and p_lo + 2 < y < p_hi - 2])
                bounds = [p_lo] + splits + [p_hi]
                for a, b in zip(bounds, bounds[1:]):
                    text = _text_in(tp, x0, a, x1, b)
                    covered = [p for p, pa, pb in periods if min(b, pb) - max(a, pa) > (pb - pa) / 2]
                    if not covered:
                        continue
                    for windows, blocked in _segments_of(text):
                        line_of_route = known.get(number.split(".")[0].lstrip("0"), route)
                        st.possessions.append(Possession(line_of_route, section, number, ends, night, covered, windows,
                                                         blocked, remarks, f"{os.path.basename(path)} p{pno + 1}",
                                                         [(path, pno, (x0, min(sec_lo, rem_lo), x1,
                                                                       max(sec_hi, rem_hi)))]))
        try:
            _read_notes(pdf, path, boxes, st)
        except Exception as exc:                    # the notes are extra: never lose the possessions over them
            st.warnings.append(f"The notes in '{os.path.basename(path)}' could not be read ({exc}).")
    finally:
        pdf.close()


_SCOPE = re.compile(r"\s*Timetable Construction Notes\s*$", re.I)


def _read_notes(pdf, path: str, boxes: Dict[int, Tuple[float, float, float, float]], st: Statement):
    """Each route's NOTES and Timetable Construction Notes: the text outside the possession tables, with the page
    header and footer (found by repetition) left out and kept as information."""
    name = os.path.basename(path)
    pages, lines, heights = [], [], []
    for i in range(len(pdf)):
        page = pdf[i]
        runs = [r for r in to_visual(text_runs(page), page)]
        pages.append(page)
        lines.append(lines_of(runs))
        heights.append(page.get_size()[1])
    furniture = find_furniture(lines, heights)
    if furniture.info.get("Header"):
        head = "; ".join(f"{k} {v}" for k, v in furniture.info.items() if k != "Header")
        st.info.append((name, (head + " - " if head else "") + furniture.info["Header"]))
    route, scope, kind = "", "", "Other text"
    para: List[str] = []
    para_box: List[float] = []                  # the paragraph's box on the displayed page: x0, y0, x1, y1
    last_y, last_size = 0.0, 10.0

    def flush(page_no: int):
        if para:
            refs = []
            if para_box:
                refs = [(path, page_no - 1, rect_from_visual(pages[page_no - 1], *para_box))]
            st.notes.append(RouteNote(route, kind, scope, " ".join(para), f"{name} p{page_no}", refs))
            para.clear()
        para_box.clear()
    for pno, page_lines in enumerate(lines):
        box = rect_to_visual(pages[pno], *boxes[pno]) if pno in boxes else None
        for line in page_lines:
            cx, cy = (line[0].x0 + line[-1].x1) / 2, line[0].cy
            text = line_text(line)
            if furniture.is_furniture(text, cy, heights[pno]):
                continue
            if box and box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                continue                                    # a possession table's own text
            size = max(r.size for r in line)
            title = _titles(text)
            if title and len(text) < 140:
                flush(pno + 1)
                if not re.search(r"Continued\W*$", text):          # 'Continued....' is the same route's next page
                    route, scope, kind = title[-1][1], "", "Other text"
                continue
            if _SCOPE.search(text):
                flush(pno + 1)
                scope, kind = _SCOPE.sub("", text), "Timetable construction notes"
                continue
            m = re.match(r"^NOTES?\b\s*:?\s*(.*)$", text)
            if m:
                flush(pno + 1)
                scope, kind = "", "Notes"
                text = m.group(1)
            elif para and last_y - cy > 1.8 * max(size, last_size):
                flush(pno + 1)
            if text:
                para.append(text)
                box_now = [min(r.x0 for r in line), min(r.y0 for r in line), max(r.x1 for r in line),
                           max(r.y1 for r in line)]
                para_box[:] = box_now if not para_box else [min(para_box[0], box_now[0]), min(para_box[1], box_now[1]),
                                                           max(para_box[2], box_now[2]), max(para_box[3], box_now[3])]
            last_y, last_size = cy, size
        flush(pno + 1)


def _titles(raw: str) -> List[Tuple[str, str]]:
    """The line of route titles in some PDF text, in order: (codes, title), e.g. ('SO110', 'SO110 VICTORIA
    EASTERN TO RAMSGATE'). A title starts with the route code and goes on in capitals; notes after it on the same
    line ('Published on behalf of ...', '(see also SW183)') are left off, and signal numbers and 'see LN3222 in
    ...' notes are not titles."""
    raw = raw.replace("\ufffe", "").replace("\x02", "-")
    # lines the PDF runs together with no break: 'RETFORDNOTES: ...', '... documentLN235 ...', 'STRATFORDIncludes'
    raw = re.sub(r"(?<=[A-Z]{2})(?=NOTES:)|(?<=[a-z.])(?=[A-Z]{2}\d{3})|(?<=[A-Z]{2})(?=[A-Z][a-z])", "\n", raw)
    lines = [" ".join(x.split()) for x in raw.splitlines()]
    out = []
    for k, line in enumerate(lines):
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if re.fullmatch(r"[A-Z]{1,2}", nxt):                   # a title wrapped by one letter or two ('EAST J' 'N')
            line += nxt
        for piece in re.split(r"(?<=\s)(?=[A-Z]{2}\d{3,4}[A-Z]?\s)", line):      # two titles on one line
            m = _ROUTE.match(piece)
            if not m:
                continue
            name = re.sub(r"\s*\((?:see|refer)\b[^)]*\)?", "", m.group(2), flags=re.I)      # '(see also SW183)'
            words = []
            for w in name.split():
                if any(c.islower() for c in w):               # a note starts: 'Published ...', 'cont', 'in ...'
                    break
                words.append(w)
            name = re.sub(r"\s+SECTION$", "", " ".join(words)).strip(" .…-–")
            if sum(c.isalpha() for c in name) >= 3:
                out.append((m.group(1), f"{m.group(1)} {name}"))
    return out


def _route_title(tp, hx0: float) -> str:
    """The line of route title above a page's (first) table, or '' when there is none."""
    try:
        found = _titles(tp.get_text_bounded(left=0, bottom=0, right=hx0 - 1, top=2000))
    except Exception:
        return ""
    return found[-1][1] if found else ""


def _by_number(titles: Sequence[Tuple[str, str]], known: Dict[str, str]):
    """Remember each title under its route number ('SO511/EA1325' -> '511' and '1325')."""
    for codes, title in titles:
        for code in re.findall(r"[A-Z]{2}(\d{3,4})", codes):
            known[code.lstrip("0")] = title


def _segments_of(text: str) -> List[Tuple[List[Window], str]]:
    """A cell can hold several possessions, each a window (or a run of windows) then what it blocks:
    '2350 Sat to 0750 Sun Fast Lines BLOCKED or 0150 Sun to 0750 Sun Slow Lines BLOCKED'."""
    found = list(_WINDOW.finditer(text))
    out: List[Tuple[List[Window], str]] = []
    pending: List[Window] = []
    for i, m in enumerate(found):
        pending += parse_windows(m.group(0))
        after = text[m.end():found[i + 1].start() if i + 1 < len(found) else len(text)]
        after = " ".join(re.sub(r"^\s*(or|and|/)\s+|\s+(or|and)\s*$", " ", after, flags=re.I).split())
        if after.strip(" ,;/") or i + 1 == len(found):      # its own blocked text: one possession
            if pending:
                out.append((pending, after.strip(" ,;/")))
            pending = []
    return out


def _night(text: str) -> str:
    t = re.sub(r"[^A-Z/]", "", text.upper())
    if "WEEKEND" in t:
        return "WEEK END"
    if "SUN/MON" in t or "SUNMON" in t:
        return "SUN/MON"
    if "MIDWEEK" in t:
        return "MID WEEK"
    if t.startswith("SAT"):
        return "SAT"
    return " ".join(text.split())[:20]


def _section(text: str) -> Tuple[str, str, Tuple[str, ...]]:
    """'Shepherds Lane Jn and Herne Hill 110.3' -> ('Shepherds Lane Jn and Herne Hill', '110.3', ends)."""
    text = " ".join(text.split())
    m = _SECTION_NO.search(text)
    number = m.group(1) if m else ""
    where = text[:m.start()].strip() if m else text
    extra = text[m.end():].strip() if m else ""                  # e.g. 'Thameslink Lines'
    name = where + (f" ({extra})" if extra else "")
    parts = re.split(r"\s+(?:and|to)\s+", where)
    ends = tuple(p.strip(" ,") for p in parts if p.strip(" ,"))
    if len(ends) > 2:                                            # 'A and B and C': the outer two
        ends = (ends[0], ends[-1])
    return name, number, ends


# --------------------------------------------------------------------------- the check
@dataclass
class Clash:
    possession: Possession
    period: Period
    window: Window
    train: str
    day: int                    # the day the train runs (0 = Monday)
    at_a: str                   # time at each end
    at_b: str
    direction: str
    remark: str = ""            # what the remarks mean for this train ('' when there are none)
    outcome: str = ""           # s4remarks.STANDS / CHECK / EXEMPT
    every_line: Optional[bool] = None   # the remarks leave some lines open (else the Blocked text decides)
    line: str = ""              # the line(s) the train runs on through the section, from a VPT
    line_verdict: str = ""      # s4lines.BLOCKED / OPEN / UNKNOWN ('' when no VPT line was found)
    line_why: str = ""
    operator: str = ""          # another operator's train (from its VPT)

    @property
    def all_lines(self) -> bool:
        return self.possession.every_line if self.every_line is None else self.every_line


@dataclass
class CheckResult:
    clashes: List[Clash]
    not_found: Dict[str, List[str]]          # place name -> sections it ends
    checked: int                             # possession rows checked
    trains: int
    periods: List[Period]
    warnings: List[str]
    exempt: List[Clash] = field(default_factory=list)          # clashes the remarks lift
    skipped: List[Tuple[str, str]] = field(default_factory=list)   # (train, why it was not checked)
    by_line: int = 0                         # clashes a VPT's running lines settled (blocked or open)
    other_trains: int = 0                    # trains of other operators checked


def maint_trains(plan) -> Set[str]:
    """Trains worked by a MAINT (maintenance) unit diagram."""
    return {m.train for d in getattr(plan, "diagrams", []) if (d.fleet or "").upper() == "MAINT"
            for m in d.moves if m.train}


def skip_reason(t, maint: Set[str]) -> str:
    """Why a train is left out of the check ('' if it is checked): runs as required and not a passenger train,
    or worked by a MAINT diagram."""
    if t.id in maint:
        return "On a MAINT diagram"
    if getattr(t, "rar", "") and not t.passenger:
        return f"Runs as required, not a passenger train ({t.rar})"
    return ""


def _alternatives(name: str) -> List[str]:
    """Names to try for an EAS place: 'Battersea Pier Jn (Grosvenor Bridge Jn)' -> both names;
    'Victoria Eastern' -> 'London Victoria (Eastern)'."""
    out = [name]
    name = re.sub(r"\s*\((?:excl?|exc|inc|incl)\.?\)", "", name, flags=re.I).strip()    # '(Excl.)', '(inc.)'
    out.append(name)
    inner = re.findall(r"\(([^)]+)\)", name)
    base = re.sub(r"\s*\([^)]*\)", "", name).strip()
    if base and base != name:
        out.append(base)
    out += inner
    for n in list(out):
        m = re.match(r"^(.*?)\s+(Eastern|Central)$", n, re.I)
        if m:
            out += [f"London {m.group(1)} ({m.group(2).title()})", f"{m.group(1)} ({m.group(2).title()})"]
        if not n.lower().startswith("london "):
            out.append("London " + n)
        out.append(re.sub(r"(\s+(station|stn|area|sidings?|platforms?))+$", "", n, flags=re.I))
        out.append(re.sub(r"\bJunction\b", "Jn", n))
    return list(dict.fromkeys(o for o in out if o))


def _times_of(t) -> Dict[str, List[Tuple[int, int]]]:
    times: Dict[str, List[Tuple[int, int]]] = {}
    for n, c in enumerate(t.calls):
        tm = c.dep if c.dep is not None else c.arr
        if tm is not None:
            times.setdefault(c.loc, []).append((n, tm // 60))
    return times


def _lines_between(vt, tips_a: Set[str], tips_b: Set[str], minute: int, day: int) -> Optional[List[str]]:
    """The line codes of the legs of VPT train `vt` between the section's ends, or None when the train is not at
    the first end at `minute` on `day`."""
    if day not in vt.days:
        return None
    times = _times_of(vt)
    hit_a = [x for tip in tips_a for x in times.get(tip, []) if (x[1] - minute) % 1440 == 0]
    hit_b = [x for tip in tips_b for x in times.get(tip, [])]
    if not hit_a or not hit_b:
        return None
    ia = min(hit_a)[0]
    ib = min(hit_b, key=lambda x: abs(x[0] - ia))[0]
    return list(line_codes(vt, ia, ib).values())


def check(plan, statement: Statement, lines=None, others=()) -> CheckResult:
    """The trains in `plan` (stationbook.read_plan) running over a Section 4 section in one of its windows.
    `lines`: the same timetable as a VPT plan, whose running lines settle the clashes where only some lines are
    blocked. `others`: other operators' VPT plans, whose trains are checked too (marked with their operator)."""
    from rstools.statspack.seats import Stations
    stations = Stations(plan.locations)
    cache: Dict[str, Set[str]] = {}

    def tips(name: str) -> Set[str]:
        if name not in cache:
            found: Set[str] = set()
            for alt in _alternatives(name):
                found = stations.find(alt)
                if found:
                    break
            cache[name] = found
        return cache[name]

    start, end = _plan_dates(plan)
    periods = {}
    for p in statement.possessions:
        for per in p.periods:
            periods[(per.name, per.start)] = per
    used = [per for per in sorted(periods.values(), key=lambda x: x.start)
            if not start or not end or (per.start <= end and per.end >= start)]
    used_keys = {(p.name, p.start) for p in used}
    # each train version: the times it reaches each place, by day
    versions = []
    maint = maint_trains(plan)
    skipped: Dict[str, str] = {}
    for vs in plan.trains.values():
        for t in vs:
            why = skip_reason(t, maint)
            if why:
                skipped[t.id] = why
                continue
            versions.append((t, _times_of(t)))
    for other in others:                                   # other operators: nothing says RAR or MAINT, all checked
        op = other.operator or os.path.splitext(os.path.basename(other.path))[0][:12]
        for vs in other.trains.values():
            for t in vs:
                t.operator = op
                versions.append((t, _times_of(t)))
    by_id: Dict[str, List[Any]] = {}
    for vs in (lines.trains.values() if lines is not None else ()):
        for vt in vs:
            by_id.setdefault(vt.id, []).append(vt)
    clashes: List[Clash] = []
    found: List[Tuple[int, Any, int]] = []
    not_found: Dict[str, List[str]] = {}
    checked = 0
    for p in statement.possessions:
        pers = [per for per in p.periods if (per.name, per.start) in used_keys]
        if not pers:
            continue
        ends = [tips(e) for e in p.ends]
        missing = [e for e, f in zip(p.ends, ends) if not f]
        if missing:
            for e in missing:
                not_found.setdefault(e, []).append(f"{p.number} {p.section}")
            continue
        checked += 1
        want = p.direction
        for t, times in versions:
            hit_a = [x for tip in ends[0] for x in times.get(tip, [])]
            hit_b = [x for tip in ends[-1] for x in times.get(tip, [])] if len(ends) > 1 else hit_a
            if not hit_a or not hit_b:
                continue
            (ia, ta), (ib, tb) = min(hit_a), min(hit_b)
            direction = "" if len(ends) == 1 or ia == ib else ("Down" if ia < ib else "Up")
            if want and direction and direction != want:
                continue
            lo, hi = min(ta, tb), max(ta, tb)
            for day in t.days:
                for w in p.windows:
                    s, e = day * 1440 + lo, day * 1440 + hi
                    if not any(s < w.end + k and e > w.start + k for k in (-WEEK, 0, WEEK)):
                        continue
                    for per in pers:
                        if not _valid_in(t, per, start, end):
                            continue
                        c = Clash(p, per, w, t.id, day, _when(day, ta), _when(day, tb), direction, operator=t.operator)
                        if not p.every_line:
                            codes = _vpt_lines(t, by_id, ends, ta, day) if t.operator == "" else \
                                [x for _i, x in sorted(line_codes(t, ia, ib).items())]
                            if codes is not None:
                                c.line_verdict, c.line_why = line_verdict(p.blocked, codes)
                                c.line = ", ".join(dict.fromkeys(codes))
                        clashes.append(c)
                        found.append((len(clashes) - 1, t, lo))
    # one row per train, day, possession and period (a train in two windows of the same night once)
    seen, unique = set(), []
    for i, c in enumerate(clashes):
        key = (id(c.possession), c.period.name, c.train, c.day)
        if key not in seen:
            seen.add(key)
            unique.append(i)
    info = {i: (t, lo) for i, t, lo in found}
    kept, exempt = _apply_remarks([clashes[i] for i in unique], [info[i] for i in unique], tips, versions)
    settled = 0
    for c in list(kept):                                  # the running lines of a VPT settle some clashes
        if c.line_verdict == S4L.BLOCKED:
            c.every_line, settled = True, settled + 1
            c.remark = (c.remark + "; " if c.remark else "") + c.line_why
        elif c.line_verdict == S4L.OPEN:
            kept.remove(c)
            c.outcome, c.remark, settled = R_EXEMPT, (c.remark + "; " if c.remark else "") + c.line_why, settled + 1
            exempt.append(c)
    trains = len({c.train for c in kept})
    warnings = []
    if not_found:
        warnings.append(f"{len(not_found)} place(s) in the Section 4 tables are not in the XML (see 'Not "
                        "Checked'), so those sections were not checked - most are lines GTR does not run on.")
    if skipped:
        warnings.append(f"{len(skipped)} train(s) were not checked (runs as required and not passenger, or on a "
                        "MAINT diagram) - see 'Trains Not Checked'.")
    other_trains = len({(c.operator, c.train) for c in kept if c.operator})
    return CheckResult(kept, not_found, checked, trains, used, warnings, exempt, sorted(skipped.items()), settled,
                       other_trains)


def _vpt_lines(t, by_id, ends, minute: int, day: int) -> Optional[List[str]]:
    """The line codes for XML train `t` from our own VPT (None when no VPT train matches it)."""
    for vt in by_id.get(t.id, []):
        codes = _lines_between(vt, ends[0], ends[-1], minute, day)
        if codes is not None:
            return codes
    return None


def _apply_remarks(clashes: List[Clash], info, tips, versions) -> Tuple[List[Clash], List[Clash]]:
    """Each clash's possession remarks applied to its train: (clashes that stand, clashes the remarks lift)."""
    from . import s4remarks as R
    rules: Dict[int, R.Remarks] = {}
    kept: List[Clash] = []
    exempt: List[Clash] = []
    by_head: Dict[str, List[Tuple[Any, Dict[str, List[Tuple[int, int]]]]]] = {}
    for t, times in versions:
        by_head.setdefault(t.id[:4].upper(), []).append((t, times))
    for c, (t, lo) in zip(clashes, info):
        p = c.possession
        if id(p) not in rules:
            rules[id(p)] = R.parse_remarks(p.remarks)
        r = rules[id(p)]
        if not r.text:
            kept.append(c)
            continue
        end_tips = set().union(*(tips(e) for e in p.ends))

        def other_time(hc: str, end_tips=end_tips, day=c.day) -> Optional[int]:
            best = None
            for ot, otimes in by_head.get(hc[:4].upper(), []):
                if day not in ot.days:
                    continue
                for tip in end_tips:
                    for _n, tm in otimes.get(tip, []):
                        best = tm if best is None else min(best, tm)
            return best
        view = R.TrainView(t.id, [x.loc for x in t.calls], _date(t.valid_from), _date(t.valid_until), lo,
                           other_time)
        v = R.apply(r, view, tips)
        c.remark, c.outcome, c.every_line = v.text, v.outcome, v.every_line
        (exempt if v.outcome == R.EXEMPT else kept).append(c)
    return kept, exempt


def _date(s: str) -> Optional[date]:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _plan_dates(plan) -> Tuple[Optional[date], Optional[date]]:
    def d(s):
        try:
            return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return d(getattr(plan, "start", "")), d(getattr(plan, "end", ""))


def _valid_in(t, per: Period, start, end) -> bool:
    """The train version runs at some time in the period (its own dates, else the XML's)."""
    def d(s):
        try:
            return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    a = d(getattr(t, "valid_from", "")) or start
    b = d(getattr(t, "valid_until", "")) or end
    if a and per.end < a:
        return False
    if b and per.start > b:
        return False
    return True


def _hhmm(minutes: int) -> str:
    from rstools.clock import hhmm
    return hhmm(minutes)


def _when(day: int, minutes: int) -> str:
    """'Tue 0008': the train's time on the day it falls (a train of Monday night reaches here on Tuesday)."""
    return f"{DAY_SHORT[(day + minutes // 1440) % 7]} {_hhmm(minutes)}"


# --------------------------------------------------------------------------- output
_CLASH_HEAD = ["Clash", "Line of route", "Section", "Between", "Period", "Night", "Possession", "Available",
               "Blocked", "Train", "Train runs", "First place", "Time there", "Second place", "Time there",
               "Direction", "Remarks", "Remarks for this train", "Line used (VPT)", "Operator"]
_CLASH_WIDTHS = [20, 28, 9, 34, 16, 10, 24, 14, 30, 9, 8, 22, 10, 22, 10, 9, 40, 50, 16, 14]


def clash_row(c: Clash) -> list:
    p = c.possession
    return ["Every line blocked" if c.all_lines else "Some lines: check the line used", p.route, p.number,
            p.section, c.period.name, p.night, c.window.text, p.available, p.blocked or "-", c.train,
            DAY_SHORT[c.day], p.ends[0], c.at_a, p.ends[-1], c.at_b, c.direction or "-", p.remarks or "-",
            c.remark or "-", c.line or "-", c.operator or "-"]


def _clash_order(c: Clash):
    return (not c.all_lines, c.possession.route, _num_key(c.possession.number), c.period.start, c.day, c.at_a)


def build_workbook(result: CheckResult, statement: Statement, xml: str):
    from .s4remarks import CHECK
    from .xlstyle import add_sheet, new_workbook
    wb = new_workbook()
    by_section: Dict[str, int] = {}
    for c in result.clashes:
        by_section[f"{c.possession.number} {c.possession.section}"] = by_section.get(
            f"{c.possession.number} {c.possession.section}", 0) + 1
    every = sum(1 for c in result.clashes if c.all_lines)
    to_check = sum(1 for c in result.clashes if c.outcome == CHECK)
    summary = [["Trains in a Section 4 possession window", result.trains],
               ["Clashes (train, day, section and period)", len(result.clashes)],
               ["...where every line of the section is blocked", every],
               ["...where only some lines are blocked (check the line the train uses)", len(result.clashes) - every],
               ["...whose remarks need checking by hand", to_check],
               ["Clashes lifted by the remarks (see 'Exempt')", len(result.exempt)],
               ["Trains not checked (see 'Trains Not Checked')", len(result.skipped)],
               ["Clashes settled by the running lines in a VPT", result.by_line],
               ["Trains of other operators in the clashes", result.other_trains],
               ["Sections with clashes", len(by_section)],
               ["Possession rows checked", result.checked],
               ["Possession rows read", len(statement.possessions)],
               ["Places not in the XML (sections not checked)", len(result.not_found)]]
    add_sheet(wb, "Summary", ["Figure", "Count"], summary, [62, 12], center=[2],
              fills={2: "bad" if every else "ok", 4: "review" if to_check else "ok"})
    rows: List[list] = []
    fills: Dict[int, str] = {}
    for c in sorted(result.clashes, key=_clash_order):
        if c.all_lines:
            fills[len(rows)] = "bad"
        elif c.outcome == CHECK:
            fills[len(rows)] = "review"
        rows.append(clash_row(c))
    add_sheet(wb, "Clashes", _CLASH_HEAD, rows, _CLASH_WIDTHS, fills=fills, center=[3, 10, 11, 13, 15, 16])
    ex = [clash_row(c) for c in sorted(result.exempt, key=_clash_order)]
    add_sheet(wb, "Exempt", _CLASH_HEAD, ex, _CLASH_WIDTHS, center=[3, 10, 11, 13, 15, 16])
    add_sheet(wb, "Trains Not Checked", ["Train", "Why it was not checked"], [list(x) for x in result.skipped],
              [12, 80])
    sec_rows = [[k, v] for k, v in sorted(by_section.items(), key=lambda kv: (-kv[1], kv[0]))]
    add_sheet(wb, "By Section", ["Section", "Clashes"], sec_rows, [60, 10], center=[2])
    nf = [[k, len(v), "; ".join(v[:6]) + (" ..." if len(v) > 6 else "")] for k, v in
          sorted(result.not_found.items())]
    add_sheet(wb, "Places Not Checked", ["Place in Section 4", "Sections", "e.g."], nf, [36, 10, 90], center=[2])
    audit = [["Timetable (Attune XML)", os.path.basename(xml)]]
    audit += [["Section 4", os.path.basename(f)] for f in statement.files]
    audit += [["Periods checked", "; ".join(f"{p.name} ({p.start:%d/%m/%Y} to {p.end:%d/%m/%Y})"
                                            for p in result.periods) or "None"],
              ["How", "A train clashes when it calls at or passes both ends of a section, on a day and in a period "
                      "the possession applies to, at a time inside the possession window. Where only the Down "
                      "or Up line is blocked, trains are taken as Down when they reach the first-named place "
                      "first. The XML has no line codes, so a train on a line left open (e.g. the fast lines "
                      "when the slow lines are blocked) is still listed: check the Blocked column."],
              ["Remarks", "Each possession's remarks are applied to the train: excepted train types (e.g. ECS, "
                          "passenger, freight), named trains or headcodes, 'after / until passage of' a train, "
                          "access to a depot via a route (the train must go to or from the depot and pass the "
                          "route), dates, and lines left open. A lifted clash is on 'Exempt' with the reason; a "
                          "remark that needs checking by hand (weeks, other possessions, unknown wording) keeps "
                          "the clash and says so."],
              ["Running lines (VPT)",
               "With a VPT of this timetable, a clash where only some lines are blocked is settled by the line the "
               "train runs on through the section: on a blocked line it stands as an 'every line' clash; on a line "
               "that is not blocked it is listed on 'Exempt'; where the line is not known it stays 'check the line "
               "used'. " + S4L.CODE_TEXT],
              ["Not checked", "Trains that run as required (unless they are passenger trains) and trains worked "
                              "by a MAINT diagram (see 'Trains Not Checked')."]]
    add_sheet(wb, "What Was Compared", ["Item", "Detail"], audit, [26, 110])
    return wb


def _num_key(n: str):
    parts = re.findall(r"\d+|[a-z]+", n)
    return [int(p) if p.isdigit() else p for p in parts]


def run_check(xml: str, pdfs: Sequence[str], out_dir: str, name: str = "", fmt: str = "xlsx",
              progress=lambda f, m: None, log=lambda m: None, vpt: str = "", others: Sequence[str] = ()):
    """Read the XML and the Section 4 PDF(s) - or, with no PDFs, the Section 4 rule set in use (Options > Rules and
    reference data) - check, and save the report. `vpt`: a VPT of the same timetable, for the running lines;
    `others`: other operators' VPTs, whose trains are checked too. Returns (path, result, statement, plan start)."""
    from rstools.stationbook import StationBookError, _plan_of
    from rstools import naming, rules
    if pdfs:
        progress(0.05, "Reading the Section 4 PDF(s)...")
        statement = read_statement(pdfs, log)
    else:
        info = rules.active_set_info()
        stored = rules.load_set() if info else None
        if info is None or stored is None:
            raise Section4Error("Choose the Section 4 PDF(s), or add a Section 4 rule set in Options > Rules and "
                                f"reference data.\n\nThe latest rules can be downloaded from {rules.RULES_URL}")
        statement = stored
        log(f"Section 4 rule set in use: {info['name']} ({len(statement.possessions)} possession rows)")
    if not statement.possessions:
        raise Section4Error("No Section 4 possessions were found. Use Network Rail's Engineering Access Statement "
                            f"Section 4 (Standard Possession Opportunities) PDF(s), from {rules.RULES_URL}")
    progress(0.4, "Reading the Attune XML...")
    log(f"Reading {os.path.basename(xml)}")
    try:
        plan = _plan_of(xml)                        # kept while the file is unchanged: a repeat check is quicker
    except StationBookError as exc:
        raise Section4Error(str(exc))
    own, theirs = None, []
    try:
        if vpt:
            log(f"Reading {os.path.basename(vpt)} for the running lines")
            own = _plan_of(vpt)
        for o in others:
            log(f"Reading {os.path.basename(o)} (another operator)")
            theirs.append(_plan_of(o))
    except (StationBookError, PrintError) as exc:
        raise Section4Error(str(exc))
    progress(0.6, "Checking...")
    result = check(plan, statement, own, theirs)
    stale = rules.coverage_warning(statement, plan.start, plan.end)
    if stale:
        result.warnings.insert(0, stale)
    progress(0.85, "Saving...")
    from .engine import _out, _save
    path = _out(out_dir, name or naming.clip(f"Section 4 check - {os.path.splitext(os.path.basename(xml))[0]}"),
                fmt)
    _save(build_workbook(result, statement, xml), path)
    return path, result, statement, plan.start
