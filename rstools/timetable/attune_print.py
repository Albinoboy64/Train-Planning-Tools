"""Reader for the Attune 'Single Train Report' train print (PDF or Word).

Each train starts with a 'Train:' line, e.g.

    Train: XX 1H05BS(ET) SX [ET/24746000] Greater Thameslink Railway (Southern)

then 'Field: value' heading lines (TrainID, SignalID, Days Pattern, Origin Loc / Time...) and a
table with one row per location:

    Location  Location Name   Working Times   Public Times   Dwell  Activity  Line ...  Allowances ...
                               Arr     Dep     Arr    Dep                     Plat Line Eng pth prf Adj
    ANGMRNG   Angmering        05.46   05p46½  05.46  05.46   0:30   T
    LTLHMJN   Littlehampton Jn         05/41                  /                     (a pass)

Columns move slightly from page to page, so every train's columns are taken from its own heading
row and each time is placed under the nearest heading. Working times keep their half minutes and
markers ('05p46½'); a time written with '/' is a passing time. Public times are what a public
timetable shows, so they are the times compared with a timetable.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

_TRAIN = re.compile(r"^\s*Train:\s*(?P<cat>\S+?)\s*(?P<id>[0-9][A-Z][0-9]{2}[A-Z0-9]{0,2})(?:\((?P<biz>[^)]*)\))?\s+"
                    r"(?P<days>\S+)\s+(?:\[(?P<code>[^\]]*)\]\s*)?(?P<toc>.*)$")
_TIME = re.compile(r"^(?P<h>[01]\d|2[0-3])(?P<mark>[./ap])(?P<m>[0-5]\d)(?P<half>½)?$")   # '29:00' is a dwell
_DWELL = re.compile(r"^(\d{1,3}:\d{2}|/)$")
_ROW = re.compile(r"^ {0,3}(?P<tiploc>[A-Z0-9]{2,7})\s{2,}(?P<rest>\S.*)$")
_ROW_PLACED = re.compile(r"^(?P<tiploc>[A-Z0-9]{2,7})\s+(?P<rest>\S.*)$")      # PDFium: cells may be close
FIELDS = ("TrainID", "SignalID", "Train Class", "Train Category", "TOC TrainID", "Train UID", "Bid/Offer Status",
          "Validity Status", "TOC Status", "RSID Headcode", "From", "Until", "Days Pattern", "Origin Loc",
          "Origin Time", "Service Code", "Destination Loc", "Destination Time", "ODT", "Distance", "Model Train",
          "Timing Load", "Publication Date", "Train Length (m)", "Power Type", "Limiting Speed", "Trailing Load",
          "Bank Holidays", "Sleepers", "Catering", "Reservations", "Brand", "Ops Char", "Business Sector",
          "Accommodation", "UIC Number")
_FIELD_RE = re.compile(r"(?<!\S)("
                       + "|".join(re.escape(f).replace(r"\ ", r"\s+") for f in sorted(FIELDS, key=len, reverse=True))
                       + r")\s*:?(?=\s|$)")
TOC_CODES = {"southern": "SN", "thameslink": "TL", "gatwick express": "GX", "great northern": "GN"}
TIME_COLS = ("wtt_arr", "wtt_dep", "pub_arr", "pub_dep")


@dataclass
class Row:
    tiploc: str
    name: str
    values: Dict[str, str]          # TIME_COLS / 'pass' / dwell, activity, plat, line... -> text as shown

    def hhmm(self, col: str, half: bool = False) -> str:
        """A time column as HHMM ('' if blank). Public times have no half minutes; with half=True a
        working time keeps its half ('05p46½' -> '0546½')."""
        m = _TIME.match(self.values.get(col, ""))
        if not m:
            return ""
        return f"{m.group('h')}{m.group('m')}" + ("½" if half and m.group("half") else "")


@dataclass
class AttuneTrain:
    train_id: str                   # e.g. 1H05BS
    headcode: str                   # e.g. 1H05
    days: str
    category: str                   # XX / OO passenger, EE empty stock ...
    toc_name: str
    operator: str                   # SN / TL / GX / GN ('' if not known)
    heading: str                    # the 'Train:' line
    fields: Dict[str, str]
    rows: List[Row] = field(default_factory=list)
    page: int = 0
    source: str = ""

    @property
    def uid(self) -> str:
        return self.fields.get("Train UID", "")

    @property
    def public(self) -> bool:
        return any(r.values.get("pub_arr") or r.values.get("pub_dep") for r in self.rows)


def is_attune_report(pages: Sequence[Sequence[str]]) -> bool:
    text = "\n".join(line for page in pages[:3] for line in page[:60])
    text = " ".join(text.split(" "))
    flat = " ".join(text.split())
    return "Single Train Report" in flat and "Working Times" in flat and bool(
        re.search(r"^\s*Train:\s", text, re.M))


def _fields(line: str) -> Dict[str, str]:
    """'TrainID:   1H05BS   Train Class:  1  ...' -> {'TrainID': '1H05BS', 'Train Class': '1', ...}."""
    found = list(_FIELD_RE.finditer(line))
    out = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(line)
        out[" ".join(m.group(1).split())] = " ".join(line[m.end():end].split()).lstrip(": ").strip()
    return out


def _tokens(text: str, start: int = 0):
    """(start, end, text) of each run of characters separated by two or more spaces; single
    spaces stay inside a value ('3 Bay Up', 'Littlehampton Junction')."""
    return [(m.start() + start, m.end() + start, m.group()) for m in re.finditer(r"\S+(?: \S+)*", text)]


class PlacedLine(str):
    """A line of text that also knows where each word sits on the page (read with PDFium). Words are
    one space apart and table cells two, so the text reads normally; positions come from `spans`
    [(first char, end char, left x, right x)], which is what places a value under its heading."""
    spans: list

    def __new__(cls, text: str, spans: list):
        obj = super().__new__(cls, text)
        obj.spans = spans
        return obj

    def __reduce__(self):                       # sent between helper processes
        return (PlacedLine, (str(self), self.spans))


def centre(line: str, a: int, b: int) -> float:
    """Centre of characters a..b: on the page for a PlacedLine, else in character columns."""
    spans = getattr(line, "spans", None)
    if not spans:
        return (a + b) / 2
    i = bisect_left([s[1] for s in spans], b)   # the word holding the last character
    j = bisect_left([s[1] for s in spans], a + 1)
    i, j = min(i, len(spans) - 1), min(j, len(spans) - 1)
    return (_x_at(spans[j], a) + _x_at(spans[i], b)) / 2


def _x_at(span, pos: int) -> float:
    s, e, x0, x1 = span
    if e <= s:
        return x0
    return x0 + (x1 - x0) * (min(max(pos, s), e) - s) / (e - s)


def _columns(head1: str, head2: str) -> Dict[str, float]:
    """Centre of every column heading of this train's table."""
    cols: Dict[str, float] = {}
    words = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", head2)]
    names = ["wtt_arr", "wtt_dep", "pub_arr", "pub_dep"]
    detail = {"Plat": "plat", "Line": "line", "Eng": "eng", "pth": "pth", "prf": "prf", "Adj": "adj"}
    offsets = ["off_arr", "off_dep"]
    for a, b, w in words:
        mid = centre(head2, a, b)
        if w in ("Arr", "Dep") and names:
            cols[names.pop(0)] = mid
        elif w in ("Arr", "Dep") and offsets:
            cols[offsets.pop(0)] = mid
        elif w in detail:
            cols[detail[w]] = mid
    for m in re.finditer(r"Dwell|Activity", head1):
        cols[m.group().lower()] = centre(head1, m.start(), m.end())
    return cols


class _Nearest:
    """Column headings by position; nearest(x) is the heading closest to x (bisect, not a scan)."""
    __slots__ = ("pos", "keys")

    def __init__(self, cols: Dict[str, float]):
        items = sorted((v, k) for k, v in cols.items())
        self.pos = [v for v, _k in items]
        self.keys = [k for _v, k in items]

    def __bool__(self):
        return bool(self.pos)

    def nearest(self, x: float) -> str:
        i = bisect_left(self.pos, x)
        if i == len(self.pos) or (i and x - self.pos[i - 1] <= self.pos[i] - x):
            i -= 1
        return self.keys[i]


_INDEX: Dict[int, tuple] = {}


def _index(cols: Dict[str, float]):
    """(time columns, other columns, has dwell) for a train's headings, built once per heading row."""
    hit = _INDEX.get(id(cols))
    if hit is None or hit[0] is not cols:
        hit = (cols, _Nearest({k: v for k, v in cols.items() if k in TIME_COLS}),
               _Nearest({k: v for k, v in cols.items() if k not in TIME_COLS}), "dwell" in cols)
        if len(_INDEX) > 64:
            _INDEX.clear()
        _INDEX[id(cols)] = hit
    return hit[1:]


def _row(line: str, cols: Dict[str, float]) -> Optional[Row]:
    m = (_ROW_PLACED if isinstance(line, PlacedLine) else _ROW).match(line)
    if not m:
        return None
    toks = _tokens(m.group("rest"), m.start("rest"))
    if isinstance(line, PlacedLine):
        toks = [p for t in toks for p in _split_values(*t)]
    if not toks:
        return None
    name = toks[0][2]
    if _TIME.match(name.rsplit(" ", 1)[-1]):       # a time run on to the name ('Littlehampton 05.08')
        return None
    values: Dict[str, str] = {}
    time_cols, other_cols, has_dwell = _index(cols)
    match_time, match_dwell = _TIME.match, _DWELL.match
    for a, _b, text in toks[1:]:
        for part_start, part in (_split_times(a, text) if " " in text else ((a, text),)):
            mid = centre(line, part_start, part_start + len(part))
            t = match_time(part)
            if t and time_cols:
                col = "pass" if t.group("mark") == "/" else time_cols.nearest(mid)
                values[col] = part
            elif has_dwell and "dwell" not in values and match_dwell(part):
                values["dwell"] = part
            elif other_cols:
                for col, piece in _by_column(line, part_start, part, other_cols, mid):
                    values[col] = (values[col] + " " + piece).strip() if col in values else piece
    return Row(m.group("tiploc"), name, values)


def _by_column(line, start: int, text: str, cols: "_Nearest", mid: float):
    """[(column, text)]: on a PDFium line, words of one run that sit under different headings
    ('3 Bay Up UML' -> Plat '3 Bay Up', Line 'UML'); otherwise the whole run under its nearest heading."""
    if not isinstance(line, PlacedLine) or " " not in text:
        return [(cols.nearest(mid), text)]
    out: List[tuple] = []
    pos = start
    for w in text.split(" "):
        col = cols.nearest(centre(line, pos, pos + len(w)))
        if out and out[-1][0] == col:
            out[-1] = (col, out[-1][1] + " " + w)
        else:
            out.append((col, w))
        pos += len(w) + 1
    return out


def _split_values(a: int, b: int, text: str):
    """PDFium lines: a time or dwell next to other text in one run ('10:00 TB') is its own value."""
    words, pos = [], a
    for w in text.split(" "):
        words.append((pos, pos + len(w), w))
        pos += len(w) + 1
    out: List[tuple] = []
    for s, e, w in words:
        lone = bool(_TIME.match(w) or _DWELL.match(w))
        if out and not lone and not out[-1][3]:
            out[-1] = (out[-1][0], e, out[-1][2] + " " + w, False)
        else:
            out.append((s, e, w, lone))
    return [(s, e, w) for s, e, w, _lone in out]


def _split_times(start: int, text: str):
    """A value run may hold two times joined by one space ('06.47 06.38'); split those apart."""
    parts = text.split(" ")
    if len(parts) > 1 and all(_TIME.match(p) for p in parts):
        pos = start
        for p in parts:
            yield pos, p
            pos += len(p) + 1
    else:
        yield start, text


def parse_attune(pages: Sequence[Sequence[str]], source: str = "") -> List[AttuneTrain]:
    trains: List[AttuneTrain] = []
    cur: Optional[AttuneTrain] = None
    cols: Dict[str, float] = {}
    head1 = ""
    for page_no, lines in enumerate(pages, start=1):
        for raw in lines:
            line = raw if isinstance(raw, PlacedLine) else raw.replace("\t", "    ").rstrip()
            if not line.strip():
                continue
            m = _TRAIN.match(line)
            if m:
                heading = " ".join(line.split())
                if cur is not None and cur.heading == heading:
                    continue                            # the same train continued on the next page
                toc = m.group("toc").strip()
                inner = re.search(r"\(([^)]*)\)\s*$", toc)
                op = TOC_CODES.get((inner.group(1) if inner else toc).strip().lower(), "")
                toc = " ".join(toc.split())
                cur = AttuneTrain(m.group("id"), m.group("id")[:4], m.group("days").upper(), m.group("cat"), toc,
                                  op, heading, {}, page=page_no, source=source)
                trains.append(cur)
                cols, head1 = {}, ""
                continue
            if cur is None:
                continue
            if line.lstrip().startswith("Location") and ("Working" in line or "Dwell" in line):
                head1 = line
                continue
            if re.search(r"\bArr\s+Dep\s+Arr\s+Dep\b", line):
                cols = _columns(head1, line)
                continue
            if not cols:
                found = _fields(line)
                for k, v in found.items():
                    cur.fields.setdefault(k, v)
                continue
            row = _row(line, cols)
            if row is not None:
                cur.rows.append(row)
    for t in trains:
        sig = t.fields.get("SignalID", "")
        if re.fullmatch(r"\d[A-Z]\d{2}", sig):
            t.headcode = sig
        if t.fields.get("Days Pattern"):
            t.days = t.fields["Days Pattern"].upper()
    return trains
