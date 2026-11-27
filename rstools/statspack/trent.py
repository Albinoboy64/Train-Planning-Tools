"""Reader for the TRENT unit diagram prints (Word .docx). Four layouts of the same diagrams are read:

* VehicleLayout29 - TIPLOCs, full headcodes, LTP / STP, platforms and miles (the most complete);
* VehicleLayout23 (also the TLGN unit diagram print) - station names, four-character headcodes, a running
  mileage, the unit count and the diagram each unit came from / forms next;
* VehicleLayout11 - short station names and the miles of each move;
* VehicleLayout05 - short station names, no mileage.

Station names are turned into TIPLOCs with the built-in name table (trent_names.csv, the same places in
all four layouts), so every layout gives the same diagrams. Several prints can be read together: where
two cover the same diagram, the more complete one is used and the other fills in what it lacks (e.g.
VehicleLayout23's next-day links for a VehicleLayout29 diagram).

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
from datetime import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, cast

from rstools import safexml
from rstools.days import days_of_code

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

FORMAT_HELP = ("Use the TRENT VehicleLayout29 unit diagram print (TIPLOCs, full headcodes such as 1F93BT, LTP/STP "
               "and miles), saved as Word (.docx). Other TRENT layouts (VehicleLayout23, 11, 05) are not used.")

_HEADER = re.compile(
    r"^\s*(?P<depot>[A-Z]{1,4})\s*(?P<num>\d+[A-Z]?)\s+(?P<days>\S+)\s+(?:(?P<plan>(?!FROM)\S+)\s+)?"
    r"FROM\s*-\s*(?P<frm>\d\d/\d\d/\d{4})\s+UNTIL\s*-\s*(?P<until>\d\d/\d\d/\d{4})\s+FLEET\s*:\s*(?P<fleet>\S+)")
_LINK = re.compile(r"^\s*(?P<kind>Off \(Previous Day\)|Forms \(Next Day\))\s*(?P<num>\d+[A-Z]?)?\s*$")
_SHORT_HEADCODE = re.compile(r"^[0-9][A-Z][0-9]{2}$")
_TOTALS = re.compile(r"Mileage:\s*\(Loaded\)\s*(?P<l>[\d.]+|\?+)\s*\(Empty\)\s*(?P<e>[\d.]+|\?+)\s*"
                     r"\(Total\)\s*(?P<t>[\d.]+|\?+)")
_HEADCODE = re.compile(r"^[0-9][A-Z][0-9]{2}[A-Z0-9]{2}$")
_ROUTE = re.compile(r"^\d+[A-Z]?\(\d+\)(?:[\\/]\d+[A-Z]?\(\d+\))*$")     # VL29 '1(1)\10(2)', VL23 '10(1)/1(2)'
_POS = re.compile(r"(\d+[A-Z]?)\((\d+)\)")
_TIME = re.compile(r"^(\d{1,2})[.+:/](\d{2})½?$")         # VL23 prints half minutes ('06+09½'): to the minute
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
_OTHER_LAYOUTS = (re.compile(r"FROM - \d\d/\d\d/\d{4}\s*UNTIL"),)
# VehicleLayout11 / 05 headers, dates and totals (tabs read as spaces)
_HEADER11 = re.compile(r"^\s*DIAGRAM\s*:\s*(?P<depot>[A-Z]{1,4})\s*(?P<num>\d+[A-Z]?)\s+(?P<days>\S+)"
                       r"\s+Fleet\s+(?P<fleet>\S+)")
_HEADER05 = re.compile(r"^\s*Diagram\s+:\s*(?P<depot>[A-Z]{1,4})\s+(?P<num>\d+[A-Z]?)\s+(?P<days>\S+)"
                       r"\s+(?P<fleet>\S+)\s*$")
_DATES = re.compile(r"(?:Start Date\s*:\s*|Runs from:\s*)(?P<frm>\d\d/\d\d/\d{4})\s+(?:End Date\s*:\s*|until\s+)"
                    r"(?P<until>\d\d/\d\d/\d{4})")
_TOTALS11 = re.compile(r"Loaded\s+(?P<l>[\d.]+)\s+Empty\s+(?P<e>[\d.]+)\s+Total Mileage\s+(?P<t>[\d.]+)")
_TOTALS05 = re.compile(r"MILES\s*:\s*\(LD\)\s*(?P<l>[\d.]+)\s*\(ETY\)\s*(?P<e>[\d.]+)\s*\(TOT\)\s*(?P<t>[\d.]+)")
_ACTIVITY = re.compile(r"^[A-Z][A-Z ]{2,}$")


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
    layout: str = "VL29"        # VL29 / VL23 (and the TLGN print) / VL11 / VL05

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
        root = safexml.fromstring(data, str(path))
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


def _parse_tab_row(line: str, cumulative: bool) -> Optional[TrentRow]:
    """A row of a tab-separated print (VehicleLayout23 / TLGN, 11 or 05): location, arrival, departure, then
    the headcode or activity, the coupled diagrams in position order and (VL23 running, VL11 per move) miles."""
    parts = [p.replace("\xa0", " ").strip() for p in line.split("\t")]
    while parts and not parts[0]:
        parts.pop(0)
    if len(parts) < 4 or parts[0].startswith(("Mileage", "Arrives", "*", "Loaded", "MILES", "OFF", "WORKS")) \
            or "Miles from Fuel" in line:
        return None
    loc, arr_t, dep_t = parts[0], parts[1], parts[2]
    headcode = activity = ""
    positions: List[tuple] = []
    miles = None
    for tok in parts[3:]:
        if not tok:
            continue
        if not headcode and not activity and (_SHORT_HEADCODE.match(tok) or _HEADCODE.match(tok)):
            headcode = tok
        elif _ROUTE.match(tok):
            positions += _POS.findall(tok)              # VL11 carries a third unit on in a later column
        elif _NUM.match(tok):
            if headcode and miles is None:
                miles = float(tok)
        elif not headcode and not activity and _ACTIVITY.match(tok):
            activity = tok
    if _minutes(arr_t) is None and _minutes(dep_t) is None and not (headcode or activity):
        return None
    row = TrentRow(loc=loc, arr=_minutes(arr_t), dep=_minutes(dep_t), headcode=headcode, activity=activity,
                   positions=[num for num, _pos in sorted(positions, key=lambda x: int(x[1]))], miles=miles)
    row.cumulative = cumulative
    return row


_NAMES: Dict[str, Dict[str, str]] = {}


def _name_key(name: str) -> str:
    """A place name compared without case, full stops or extra spaces ('St. Leonards' = 'St Leonards')."""
    return " ".join(name.replace(".", " ").casefold().split())


def name_table() -> Dict[str, Dict[str, str]]:
    """{'to_tiploc': {TRENT name or short name: TIPLOC}, 'name': {TIPLOC: TRENT name}} from trent_names.csv."""
    if not _NAMES:
        import csv
        import os
        to_tip: Dict[str, str] = {}
        names: Dict[str, str] = {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trent_names.csv")
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    tip = (r.get("TIPLOC") or "").strip()
                    if not tip:
                        continue
                    for col in ("TRENT name", "TRENT short name"):
                        n = (r.get(col) or "").strip()
                        if n and n != tip:
                            to_tip.setdefault(_name_key(n), tip)
                    if (r.get("TRENT name") or "").strip():
                        names[tip] = r["TRENT name"].strip()
        except OSError:
            pass
        _NAMES.update(to_tiploc=to_tip, name=names)
    return _NAMES


def _to_tiplocs(diagrams) -> None:
    """Station names (full or short) as TIPLOCs, as VehicleLayout29 gives them; unknown names are kept."""
    to_tip = name_table()["to_tiploc"]
    for d in diagrams:
        for r in d.rows:
            r.loc = to_tip.get(_name_key(r.loc), r.loc)


def parse_vehicle_layout(path: str) -> TrentData:
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    lines = _paragraph_lines(path)
    diagrams: List[TrentDiagram] = []
    warnings: List[str] = []
    cur: Optional[TrentDiagram] = None
    head = [line.replace("\t", " ") for line in lines[:400]]
    if any(_HEADER11.match(h) for h in head):
        layout = "VL11"
    elif any(_HEADER05.match(h) for h in head):
        layout = "VL05"
    elif any("\t" in line and _HEADER.match(line) for line in lines[:400]):
        layout = "VL23"                         # also the TLGN unit diagram print
    else:
        layout = "VL29"
    tabbed = layout != "VL29"
    for line in lines:
        flat = line.replace("\t", " ")
        m = _HEADER.match(line) if layout in ("VL29", "VL23") else (_HEADER11 if layout == "VL11" else
                                                                    _HEADER05).match(flat)
        if m:
            g = m.groupdict()
            cur = TrentDiagram(depot=g["depot"], number=g["num"], days_code=g["days"], plan=g.get("plan") or "",
                               start=g.get("frm") or "", end=g.get("until") or "", fleet=g["fleet"])
            diagrams.append(cur)
            continue
        if cur is None:
            continue
        t = (_TOTALS.search(line) or _TOTALS11.search(flat) or _TOTALS05.search(flat))
        if t:
            cur.loaded, cur.empty, cur.total = (_float(t["l"]), _float(t["e"]), _float(t["t"]))
            continue
        if "AP  DP" in line or not line.strip():
            continue
        if tabbed:
            dates = _DATES.search(flat)
            if dates:
                cur.start, cur.end = dates["frm"], dates["until"]
                continue
            link = _LINK.match(flat)
            if link:
                if link["num"]:
                    setattr(cur, "prev_num" if link["kind"].startswith("Off") else "next_num", link["num"])
                continue
            toks = [p.strip() for p in line.replace("\xa0", " ").split("\t") if p.strip()]
            if toks and cur.rows and all(_ROUTE.match(t) for t in toks):     # VL05: a third unit on its own line
                extra = [p for t in toks for p in _POS.findall(t)]
                cur.rows[-1].positions += [num for num, _pos in sorted(extra, key=lambda x: int(x[1]))]
                continue
            row = _parse_tab_row(line, cumulative=layout == "VL23")
        else:
            row = _parse_row(line)
        if row:
            cur.rows.append(row)
    if layout == "VL23":
        for d in diagrams:                  # running mileage -> miles of each move (as VehicleLayout29 gives)
            last = 0.0
            for r in d.rows:
                if r.headcode and r.miles is not None:
                    r.miles, last = round(r.miles - last, 2), r.miles       # as VL29 prints them
    if tabbed:
        _to_tiplocs(diagrams)
    if layout == "VL05" and diagrams:
        warnings.append("This TRENT print (VehicleLayout05) has no miles for each train, so mileage figures are left "
                        "blank. Use the VehicleLayout29, 23 or 11 print (or add one of them) for mileage.")

    if not diagrams:
        start_text = "\n".join(lines[:60])
        if any(p.search(start_text) for p in _OTHER_LAYOUTS):
            raise TrentFormatError("This TRENT print is not one of the layouts the app reads. " + FORMAT_HELP)
        raise TrentFormatError("No unit diagrams were found in this file. " + FORMAT_HELP)

    mismatched = []
    for d in diagrams:
        _unroll_times(d)
        if not d.plan:          # VL23 / 11 / 05 print no plan: a diagram for a week or less is a short-term one
            d.plan = "STP" if 0 <= _span_days(d.start, d.end) <= 6 else "LTP"
        if not d.days:
            warnings.append(f"Diagram {d.key} has an unrecognised days code '{d.days_code}' and was skipped.")
        elif layout != "VL05" and not _totals_match(d):
            mismatched.append(f"{d.key} {d.days_code}")
    if mismatched:
        warnings.append(f"{len(mismatched)} diagram(s) in the TRENT print have service miles that do not add up to "
                        f"the printed mileage total (e.g. {', '.join(mismatched[:8])}) - part of the print may not "
                        "have been read, or TRENT's own total counts miles no printed move carries. Check the file "
                        "is a complete TRENT unit diagram print.")
    return TrentData(path, [d for d in diagrams if d.days], warnings, layout)


def _span_days(start: str, end: str) -> int:
    """Days from a 'dd/mm/yyyy' start to end; -1 when either is missing."""
    try:
        return (datetime.strptime(end, "%d/%m/%Y") - datetime.strptime(start, "%d/%m/%Y")).days
    except ValueError:
        return -1


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
    loaded = sum(cast(float, r.miles) for r in moves if not is_empty_headcode(r.headcode))   # none are None
    total = sum(cast(float, r.miles) for r in moves)
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
