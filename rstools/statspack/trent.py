"""Reader for the TRENT unit diagram prints (Word .docx): the SNGX 'VehicleLayout29' layout and the TLGN
unit diagram layout.

TLGN layout (tab-separated; station names, four-character headcodes, a running mileage, and the
diagram each unit came from / forms next):

     HE 51   SO   FROM - 19/12/2026   UNTIL - 15/05/2027   FLEET    :717/0
     6-car
     Off (Previous Day)   303
     Hornsey E.M.U.D.             03+52   5L98      51(1)     3.97
     London Kings Cross   04+01   04.12   2L98      51(1)    38.43
     Welwyn GC CSD        22+05           WASH
     Forms (Next Day)     316
     Mileage:  (Loaded)  374.99   (Empty)  18.91   (Total)  393.90

VehicleLayout29 (SNGX):

Layout of each diagram (fixed-width text, one paragraph per line):

     BI 1   WO     LTP    FROM - 16/12/2026   UNTIL - 12/05/2027      FLEET   :387/3
              AP  DP Arr    Dep                    Route                    Mileage
     BRHM          1        04+35  5Y00BP                     1(1)          6.78   6.78
     HYWRDSH   3     06.09                  ATTTT
     ...
   Mileage:  (Loaded)  562.50   (Empty)   28.55   (Total)  591.05

Movement rows carry the headcode, the coupled diagrams in position order
('801(1)\\854(2)') and the miles from this location to the next row's location.
"""
from __future__ import annotations

import re
import zipfile
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .days import days_of_code

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

FORMAT_HELP = ("Use the TRENT 'VehicleLayout29' diagram print (SNGX: TIPLOC codes, full headcodes such as "
               "1F93BT, LTP/STP and the mileage of each service) or the TLGN unit diagram print (station names, "
               "'Forms (Next Day)').")

_HEADER = re.compile(
    r"^\s*(?P<depot>[A-Z]{1,4})\s*(?P<num>\d+[A-Z]?)\s+(?P<days>\S+)\s+(?:(?P<plan>(?!FROM)\S+)\s+)?"
    r"FROM\s*-\s*(?P<frm>\d\d/\d\d/\d{4})\s+UNTIL\s*-\s*(?P<until>\d\d/\d\d/\d{4})\s+FLEET\s*:\s*(?P<fleet>\S+)")
_LINK = re.compile(r"^\s*(?P<kind>Off \(Previous Day\)|Forms \(Next Day\))\s*(?P<num>\d+[A-Z]?)?\s*$")
_SHORT_HEADCODE = re.compile(r"^[0-9][A-Z][0-9]{2}$")
_TOTALS = re.compile(r"Mileage:\s*\(Loaded\)\s*(?P<l>[\d.]+|\?+)\s*\(Empty\)\s*(?P<e>[\d.]+|\?+)\s*"
                     r"\(Total\)\s*(?P<t>[\d.]+|\?+)")
_HEADCODE = re.compile(r"^[0-9][A-Z][0-9]{2}[A-Z0-9]{2}$")
_ROUTE = re.compile(r"^\d+[A-Z]?\(\d+\)(?:\\\d+[A-Z]?\(\d+\))*$")
_POS = re.compile(r"(\d+[A-Z]?)\((\d+)\)")
_TIME = re.compile(r"^(\d{1,2})[.+:/](\d{2})$")
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
_OTHER_LAYOUTS = (re.compile(r"^\s*DIAGRAM\s*:"), re.compile(r"^\s*Diagram\s+:"),
                  re.compile(r"FROM - \d\d/\d\d/\d{4}\s*UNTIL"))


class TrentFormatError(Exception):
    pass


@dataclass
class TrentRow:
    loc: str
    arr: Optional[int]          # minutes after midnight of the diagram's start day (may exceed 1440)
    dep: Optional[int]
    headcode: str               # movement rows only
    activity: str               # activity rows (ATTACH, DETACH, REVRSE, STABLD, CET...)
    positions: List[str]        # coupled diagram numbers in position order (front first)
    miles: Optional[float]      # miles from this location to the next row's location
    cumulative: bool = False    # read from a print that gives a running mileage (converted on reading)


@dataclass
class TrentDiagram:
    depot: str
    number: str
    days_code: str
    plan: str                   # LTP / STP / draft ...
    start: str
    end: str
    fleet: str
    rows: List[TrentRow] = field(default_factory=list)
    loaded: Optional[float] = None
    empty: Optional[float] = None
    total: Optional[float] = None
    prev_num: str = ""          # TLGN print: the diagram (same depot) the units came from the day before
    next_num: str = ""          # ...and the one they form the next day

    @property
    def key(self) -> str:
        return f"{self.depot}{self.number}"

    @property
    def days(self) -> Set[int]:
        return days_of_code(self.days_code)


@dataclass
class TrentData:
    path: str
    diagrams: List[TrentDiagram]
    warnings: List[str]

    def days(self) -> Set[int]:
        out = set()
        for d in self.diagrams:
            out |= d.days
        return out

    def fleets(self) -> Set[str]:
        return {d.fleet for d in self.diagrams}


def _paragraph_lines(path: str) -> List[str]:
    try:
        with zipfile.ZipFile(path) as z:
            from rstools.fsutil import zip_read
            data = zip_read(z, "word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise TrentFormatError(f"'{path}' is not a readable Word (.docx) file: {exc}")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise TrentFormatError(f"'{path}' could not be read - the Word file looks damaged ({exc}).")
    lines = []
    for p in root.iter(W + "p"):
        parts = []
        for node in p.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag == W + "tab":
                parts.append("\t")
        lines.append("".join(parts))
    return lines


def _minutes(text: str) -> Optional[int]:
    m = _TIME.match(text.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _float(text: str) -> Optional[float]:
    t = text.strip()
    return float(t) if _NUM.match(t) else None


def _parse_row(line: str) -> Optional[TrentRow]:
    if len(line) < 15 or not line[:5].strip() == "" or not line[5:14].strip():
        return None
    loc = line[5:14].strip()
    if loc.startswith("*"):
        return None                     # a note such as '*(Hand Bash Then via WM)*' or '*TRAFFIC SPARE*'
    arr_t, dep_t = line[21:28].strip(), line[28:35].strip()
    rest = line[35:].split()
    headcode = activity = ""
    positions: List[str] = []
    miles = None
    if rest and _HEADCODE.match(rest[0]):
        headcode = rest[0]
        for tok in rest[1:]:
            if _ROUTE.match(tok):
                positions = [num for num, _pos in sorted(_POS.findall(tok), key=lambda x: int(x[1]))]
        nums = [tok for tok in rest[1:] if _NUM.match(tok)]
        if nums:
            miles = float(nums[-1])
    elif rest:
        activity = rest[0]
    return TrentRow(loc=loc, arr=_minutes(arr_t), dep=_minutes(dep_t), headcode=headcode, activity=activity,
                    positions=positions, miles=miles)


def _parse_tab_row(line: str) -> Optional[TrentRow]:
    """A TLGN print row: location, arrival, departure, route (headcode or activity), units, running miles."""
    parts = [p.replace("\xa0", " ").strip() for p in line.split("\t")]
    while parts and not parts[0]:
        parts.pop(0)
    if len(parts) < 4 or parts[0].startswith(("Mileage", "Arrives", "*")):
        return None
    loc, arr_t, dep_t, route = parts[0], parts[1], parts[2], parts[3]
    if _minutes(arr_t) is None and _minutes(dep_t) is None and not route:
        return None
    headcode = activity = ""
    positions: List[str] = []
    cum = None
    if _SHORT_HEADCODE.match(route) or _HEADCODE.match(route):
        headcode = route
        for tok in parts[4:]:
            if _ROUTE.match(tok):
                positions = [num for num, _pos in sorted(_POS.findall(tok), key=lambda x: int(x[1]))]
            elif _NUM.match(tok):
                cum = float(tok)
    elif route:
        activity = route
    row = TrentRow(loc=loc, arr=_minutes(arr_t), dep=_minutes(dep_t), headcode=headcode, activity=activity,
                   positions=positions, miles=cum)
    row.cumulative = True
    return row


def _is_tiploc(loc: str) -> bool:
    return bool(loc) and not any(ch.islower() for ch in loc) and " " not in loc


def _name_tiplocs(diagrams) -> None:
    """The TLGN print names stations but gives a TIPLOC on 'STABLD' lines. The line next to it is the
    same place by name (e.g. 'Hornsey E.M.U.D.' then 'HRNSYMD'), so the TIPLOC is replaced by that name."""
    seen: Dict[str, Counter] = defaultdict(Counter)
    for d in diagrams:
        rows = d.rows
        for i, r in enumerate(rows):
            if _is_tiploc(r.loc):
                for j in (i - 1, i + 1):
                    if 0 <= j < len(rows) and not _is_tiploc(rows[j].loc):
                        seen[r.loc][rows[j].loc] += 2 if j < i else 1     # the line before counts more
    names = {tip: c.most_common(1)[0][0] for tip, c in seen.items()}
    for d in diagrams:
        for r in d.rows:
            r.loc = names.get(r.loc, r.loc)


def parse_vehicle_layout(path: str) -> TrentData:
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    lines = _paragraph_lines(path)
    diagrams: List[TrentDiagram] = []
    warnings: List[str] = []
    cur: Optional[TrentDiagram] = None
    tabbed = any("\t" in line and _HEADER.match(line) for line in lines[:400])     # the TLGN layout
    for line in lines:
        m = _HEADER.match(line)
        if m:
            cur = TrentDiagram(depot=m["depot"], number=m["num"], days_code=m["days"], plan=m["plan"] or "LTP",
                               start=m["frm"], end=m["until"], fleet=m["fleet"])
            diagrams.append(cur)
            continue
        if cur is None:
            continue
        t = _TOTALS.search(line)
        if t:
            cur.loaded, cur.empty, cur.total = (_float(t["l"]), _float(t["e"]), _float(t["t"]))
            continue
        if "AP  DP" in line or not line.strip():
            continue
        if tabbed:
            link = _LINK.match(line.replace("\t", " "))
            if link:
                if link["num"]:
                    setattr(cur, "prev_num" if link["kind"].startswith("Off") else "next_num", link["num"])
                continue
            row = _parse_tab_row(line)
        else:
            row = _parse_row(line)
        if row:
            cur.rows.append(row)
    if tabbed:
        for d in diagrams:                  # running mileage -> miles of each move (as VehicleLayout29 gives)
            last = 0.0
            for r in d.rows:
                if r.headcode and r.miles is not None:
                    r.miles, last = round(r.miles - last, 4), r.miles
        _name_tiplocs(diagrams)

    if not diagrams:
        head = "\n".join(lines[:60])
        if any(p.search(head) for p in _OTHER_LAYOUTS):
            raise TrentFormatError("This TRENT print is not one of the layouts the app reads. " + FORMAT_HELP)
        raise TrentFormatError("No unit diagrams were found in this file. " + FORMAT_HELP)

    mismatched = []
    for d in diagrams:
        _unroll_times(d)
        if not d.days:
            warnings.append(f"Diagram {d.key} has an unrecognised days code '{d.days_code}' and was skipped.")
        elif not _totals_match(d):
            mismatched.append(f"{d.key} {d.days_code}")
    if mismatched:
        warnings.append(f"{len(mismatched)} diagram(s) in the TRENT print have service miles that do not add up to "
                        f"the printed mileage total (e.g. {', '.join(mismatched[:8])}) - part of the print may not "
                        "have been read. Check the file is a complete TRENT unit diagram print.")
    return TrentData(path, [d for d in diagrams if d.days], warnings)


def is_empty_headcode(headcode: str) -> bool:
    """Class 5 / 3 / 0 moves are empty (ECS); TRENT's '(Empty)' total uses the same rule."""
    return headcode[:1] in ("5", "3", "0")


def _totals_match(d: TrentDiagram, tol: float = 0.5) -> bool:
    """Do the rows' miles add up to the diagram's printed Loaded / Total figures?"""
    if d.total is None or d.loaded is None:
        return True
    moves = [r for r in d.rows if r.headcode]
    if any(r.miles is None for r in moves):
        return True                     # '???' miles: nothing to check against
    loaded = sum(r.miles for r in moves if not is_empty_headcode(r.headcode))
    total = sum(r.miles for r in moves)
    return abs(loaded - d.loaded) <= tol and abs(total - d.total) <= tol


def _unroll_times(d: TrentDiagram):
    """Times after midnight continue past 24:00 (00+23 -> 24:23)."""
    last = None
    for r in d.rows:
        for attr in ("arr", "dep"):
            v = getattr(r, attr)
            if v is None:
                continue
            while last is not None and v < last - 6 * 60:
                v += 1440
            setattr(r, attr, v)
            last = v
