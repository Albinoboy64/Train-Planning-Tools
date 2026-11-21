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
from typing import Dict, List, Optional, Sequence, Set, Tuple

DAY_CODES = {"m": 0, "mo": 0, "mon": 0, "t": 1, "tu": 1, "tue": 1, "tues": 1, "w": 2, "we": 2, "wed": 2,
             "th": 3, "thu": 3, "thur": 3, "thurs": 3, "f": 4, "fr": 4, "fri": 4, "s": 5, "sa": 5, "sat": 5,
             "su": 6, "sun": 6}
DAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEK = 7 * 1440
_WINDOW = re.compile(r"(\d{2})[.:]?(\d{2})\s*([A-Za-z]{1,5}(?:\s*[-/]\s*[A-Za-z]{1,5})?)\s+to\s+"
                     r"(\d{2})[.:]?(\d{2})\s*([A-Za-z]{1,5}(?:\s*[-/]\s*[A-Za-z]{1,5})?)\b")
_SECTION_NO = re.compile(r"\b(\d{2,4}\.\d{1,3}[a-z]?)\b")
_LINE_WORDS = re.compile(r"\b(fast|slow|main|relief|local|suburban|electric|loop|platforms?|reversible|goods|chatham|"
                         r"thameslink|quarry|hendon|bay|siding|no\.?\s*\d|[a-f]\s*&\s*[a-f]|[a-f] lines?)\b", re.I)
_ROUTE = re.compile(r"^\s*([A-Z]{2}\d{3,4}[A-Z]?)\s+(.+?)(?:\s+continued.*)?\s*$")
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
class Statement:
    possessions: List[Possession] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


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


def _text_in(tp, x0, y0, x1, y1) -> str:
    try:
        text = tp.get_text_bounded(left=x0, bottom=y0, right=x1, top=y1)
    except Exception:
        return ""
    return " ".join(text.replace("￾", "").replace("\x02", "-").split())


def _segments(page):
    import pypdfium2.raw as R
    cols, rows = [], []          # cols: lines of constant y (column edges), rows: constant x (row edges)
    for obj in page.get_objects():
        if obj.type != R.FPDF_PAGEOBJ_PATH:
            continue
        l, b, r, t = obj.get_bounds()
        if t - b < 3 and r - l > 3:
            cols.append(((b + t) / 2, l, r))
        elif r - l < 3 and t - b > 3:
            rows.append(((l + r) / 2, b, t))
    return cols, rows


def _cluster(values, tol=2.5):
    out = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(g) / len(g) for g in out]


def read_statement(paths: Sequence[str], log=lambda m: None) -> Statement:
    st = Statement()
    for path in paths:
        log(f"Reading {os.path.basename(path)}")
        before = len(st.possessions)
        _read_pdf(path, st)
        st.files.append(path)
        found = len(st.possessions) - before
        if not found:
            st.warnings.append(f"No Section 4 possessions were found in '{os.path.basename(path)}'. Use Network "
                               "Rail's Engineering Access Statement Section 4 (Standard Possession Opportunities) PDF.")
        else:
            log(f"  {found} possession row(s)")
    return st


def _read_pdf(path: str, st: Statement):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise Section4Error("The PDF reader (pypdfium2) is not available.")
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception as exc:
        raise Section4Error(f"'{os.path.basename(path)}' could not be opened as a PDF ({exc}).")
    route, section, number = "", "", ""
    ends: Tuple[str, ...] = ()
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
            top = _text_in(tp, 0, 0, hx0 - 1, 2000)
            for line in re.split(r"(?<=\S)\s{0,1}(?=[A-Z]{2}\d{3})", top):
                m = _ROUTE.match(line)
                if m:
                    route = f"{m.group(1)} {re.sub(r'continued.*', '', m.group(2), flags=re.I).strip(' .…')}"
            # body rows: bands between row edges that cross the period columns
            body = sorted({round(x, 1) for x, b, t in rows if b <= (p_lo + p_hi) / 2 <= t and x > hx1 - 1})
            body = _cluster(body)
            sec_edges = _cluster([x for x, b, t in rows if b <= (sec_lo + sec_hi) / 2 <= t and x > hx1 - 1])
            rem_edges = _cluster([x for x, b, t in rows if b <= (rem_lo + rem_hi) / 2 <= t and x > hx1 - 1])
            day_edges = _cluster([x for x, b, t in rows if b <= (day_lo + day_hi) / 2 <= t and x > hx1 - 1])
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
                        st.possessions.append(Possession(route, section, number, ends, night, covered, windows,
                                                         blocked, remarks, f"{os.path.basename(path)} p{pno + 1}"))
    finally:
        pdf.close()


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


@dataclass
class CheckResult:
    clashes: List[Clash]
    not_found: Dict[str, List[str]]          # place name -> sections it ends
    checked: int                             # possession rows checked
    trains: int
    periods: List[Period]
    warnings: List[str]


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


def check(plan, statement: Statement, log=lambda m: None) -> CheckResult:
    """The trains in `plan` (stationbook.read_plan) running over a Section 4 section in one of its windows."""
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
    for _hc, vs in plan.trains.items():
        for t in vs:
            times: Dict[str, List[Tuple[int, int]]] = {}
            for n, c in enumerate(t.calls):
                tm = c.dep if c.dep is not None else c.arr
                if tm is not None:
                    times.setdefault(c.loc, []).append((n, tm // 60))
            versions.append((t, times))
    clashes: List[Clash] = []
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
                        clashes.append(Clash(p, per, w, t.id, day, _when(day, ta), _when(day, tb), direction))
    # one row per train, day, possession and period (a train in two windows of the same night once)
    seen, unique = set(), []
    for c in clashes:
        key = (id(c.possession), c.period.name, c.train, c.day)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    trains = len({c.train for c in unique})
    warnings = []
    if not_found:
        warnings.append(f"{len(not_found)} place(s) in the Section 4 tables are not in the XML (see 'Not "
                        "Checked'), so those sections were not checked - most are lines GTR does not run on.")
    return CheckResult(unique, not_found, checked, trains, used, warnings)


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
    m = minutes % 1440
    return f"{m // 60:02d}{m % 60:02d}"


def _when(day: int, minutes: int) -> str:
    """'Tue 0008': the train's time on the day it falls (a train of Monday night reaches here on Tuesday)."""
    return f"{DAY_SHORT[(day + minutes // 1440) % 7]} {_hhmm(minutes)}"


# --------------------------------------------------------------------------- output
def build_workbook(result: CheckResult, statement: Statement, xml: str):
    from .xlstyle import add_sheet, new_workbook
    wb = new_workbook()
    by_section: Dict[str, int] = {}
    for c in result.clashes:
        by_section[f"{c.possession.number} {c.possession.section}"] = by_section.get(
            f"{c.possession.number} {c.possession.section}", 0) + 1
    every = sum(1 for c in result.clashes if c.possession.every_line)
    summary = [["Trains in a Section 4 possession window", result.trains],
               ["Clashes (train, day, section and period)", len(result.clashes)],
               ["...where every line of the section is blocked", every],
               ["...where only some lines are blocked (check the line the train uses)", len(result.clashes) - every],
               ["Sections with clashes", len(by_section)],
               ["Possession rows checked", result.checked],
               ["Possession rows read", len(statement.possessions)],
               ["Places not in the XML (sections not checked)", len(result.not_found)]]
    add_sheet(wb, "Summary", ["Figure", "Count"], summary, [62, 12], center=[2],
              fills={2: "bad" if every else "ok"})
    rows: List[list] = []
    fills: Dict[int, str] = {}
    for c in sorted(result.clashes, key=lambda c: (not c.possession.every_line, c.possession.route,
                                                    _num_key(c.possession.number), c.period.start, c.day, c.at_a)):
        p = c.possession
        if p.every_line:
            fills[len(rows)] = "bad"
        rows.append(["Every line blocked" if p.every_line else "Some lines: check the line used", p.route,
                     p.number, p.section, c.period.name, p.night, c.window.text, p.available, p.blocked or "-",
                     c.train,
                     DAY_SHORT[c.day], p.ends[0], c.at_a, p.ends[-1], c.at_b, c.direction or "-", p.remarks or "-"])
    add_sheet(wb, "Clashes", ["Clash", "Line of route", "Section", "Between", "Period", "Night", "Possession",
                              "Available", "Blocked", "Train", "Train runs", "First place", "Time there",
                              "Second place", "Time there", "Direction", "Remarks"], rows,
              [20, 28, 9, 34, 16, 10, 24, 14, 30, 9, 8, 22, 10, 22, 10, 9, 40], fills=fills,
              center=[3, 10, 11, 13, 15, 16])
    sec_rows = [[k, v] for k, v in sorted(by_section.items(), key=lambda kv: (-kv[1], kv[0]))]
    add_sheet(wb, "By Section", ["Section", "Clashes"], sec_rows, [60, 10], center=[2])
    nf = [[k, len(v), "; ".join(v[:6]) + (" ..." if len(v) > 6 else "")] for k, v in
          sorted(result.not_found.items())]
    add_sheet(wb, "Not Checked", ["Place in Section 4", "Sections", "e.g."], nf, [36, 10, 90], center=[2])
    audit = [["Timetable (Attune XML)", os.path.basename(xml)]]
    audit += [["Section 4", os.path.basename(f)] for f in statement.files]
    audit += [["Periods checked", "; ".join(f"{p.name} ({p.start:%d/%m/%Y} to {p.end:%d/%m/%Y})"
                                            for p in result.periods) or "None"],
              ["How", "A train clashes when it calls at or passes both ends of a section, on a day and in a period "
                      "the possession applies to, at a time inside the possession window. Where only the Down "
                      "or Up line is blocked, trains are taken as Down when they reach the first-named place "
                      "first. The XML has no line codes, so a train on a line left open (e.g. the fast lines "
                      "when the slow lines are blocked) is still listed: check the Blocked column."]]
    add_sheet(wb, "What Was Compared", ["Item", "Detail"], audit, [26, 110])
    return wb


def _num_key(n: str):
    parts = re.findall(r"\d+|[a-z]+", n)
    return [int(p) if p.isdigit() else p for p in parts]


def run_check(xml: str, pdfs: Sequence[str], out_dir: str, name: str = "", fmt: str = "xlsx",
              progress=lambda f, m: None, log=lambda m: None):
    """Read the XML and the Section 4 PDF(s) - or, with no PDFs, the Section 4 rule set in use (Options > Rules and
    reference data) - check, and save the report. Returns (path, result, statement, plan start date)."""
    from rstools.stationbook import StationBookError, read_plan
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
        plan = read_plan(xml)
    except StationBookError as exc:
        raise Section4Error(str(exc))
    progress(0.6, "Checking...")
    result = check(plan, statement, log)
    stale = rules.coverage_warning(statement, plan.start, plan.end)
    if stale:
        result.warnings.insert(0, stale)
    progress(0.85, "Saving...")
    from .engine import _out, _save
    path = _out(out_dir, name or naming.clip(f"Section 4 check - {os.path.splitext(os.path.basename(xml))[0]}"),
                fmt)
    _save(build_workbook(result, statement, xml), path)
    return path, result, statement, plan.start
