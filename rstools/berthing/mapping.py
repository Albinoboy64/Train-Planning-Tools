"""Which XML location each berth on a chart is: the sheet, the berth's label as written on the chart, its
TIPLOC and the platform / siding road codes Attune uses for it (e.g. Brighton 'Plat 7' = BRGHTN 7 or 7F;
Eastbourne 'No 3 Siding' = EBOUSID S3). '*' takes any code at that TIPLOC not used by another berth on the
sheet; berths sharing a TIPLOC with no road in the XML are filled in turn.

The list is a CSV the user can edit (Edit berth locations...); berths added to the built-in list in later
versions are used too, without changing the user's own rows."""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "berth_locations_default.csv")
USER_NAME = "berth_locations.csv"
ANY = "*"


def norm(text) -> str:
    """Sheet names and berth labels compared loosely: case, spaces, '_' and '.' do not matter
    ('St. Leonards' = 'St Leonards', 'East_Grinstead' = 'East Grinstead')."""
    return " ".join(str(text or "").replace("_", " ").replace(".", " ").split()).casefold()


@dataclass
class Berth:
    tiploc: str
    codes: Tuple[str, ...]      # platform / road codes; (ANY,) for any


@dataclass
class Locations:
    sheets: Dict[str, Dict[str, Berth]] = field(default_factory=dict)     # norm(sheet) -> norm(label) -> Berth
    path: str = ""
    warning: str = ""

    def sheet(self, name: str) -> Dict[str, Berth]:
        key = norm(name)
        if key in self.sheets:
            return self.sheets[key]
        # a sheet renamed slightly between issues ('RDH Up Tonb Goods Loop' / 'RDH Up Tonb Sdg'): same first words
        words = key.split()
        for k, v in self.sheets.items():
            if len(words) >= 2 and k.split()[:2] == words[:2]:
                return v
        return {}

    def berth(self, sheet: str, label: str) -> Optional[Berth]:
        rows = self.sheet(sheet)
        found = rows.get(norm(label))
        return found if found is not None else guess(label, rows)


_PLAT = re.compile(r"^(?:plat(?:form)?|p)\s*(\d+[a-z]?)\b", re.I)
_ROAD = re.compile(r"(?:siding|sdg|shed|road|carriage|no)\s*(\d+)\b|^(\d+)\s*(?:up\s+)?(?:sdg|siding|shed)\b", re.I)


def guess(label: str, rows: Dict[str, Berth]) -> Optional[Berth]:
    """A berth not in the list, read from its label on a sheet whose TIPLOCs are known: 'Plat 5' -> platform 5,
    'Siding 2' / 'No 2 Siding' / '2 Shed' -> road S2. None when it cannot be told."""
    if not rows:
        return None
    m = _PLAT.match(label.strip())
    kinds = [b for b in rows.values() if b.tiploc and not any(c.startswith("S") or c == ANY for c in b.codes)]
    if m and kinds:
        n = m.group(1).upper()
        return Berth(kinds[0].tiploc, (n, n + "F"))
    m = _ROAD.search(label.strip())
    roads = [b for b in rows.values() if b.tiploc and any(c.startswith("S") for c in b.codes)]
    if m and roads and len({b.tiploc for b in roads}) == 1:
        return Berth(roads[0].tiploc, ("S" + (m.group(1) or m.group(2)),))
    return None


def _read(path: str) -> List[Dict[str, str]]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
        except UnicodeDecodeError:
            continue
    return []


def _parse(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, Berth]]:
    out: Dict[str, Dict[str, Berth]] = {}
    for r in rows:
        sheet, label = r.get("Sheet", ""), r.get("Berth", "")
        if not sheet or not label:
            continue
        codes = tuple(c.strip().upper() if c.strip() != ANY else ANY for c in re.split(r"[;,]", r.get("Codes", ""))
                      if c.strip()) or (ANY,)
        out.setdefault(norm(sheet), {})[norm(label)] = Berth(r.get("TIPLOC", "").strip().upper(), codes)
    return out


def user_path() -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), USER_NAME)


def ensure_user_copy() -> str:
    """The user's editable copy (made from the built-in list the first time); the built-in list if the
    data folder cannot be written."""
    path = user_path()
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(DEFAULT_CSV, encoding="utf-8") as src, open(path, "w", encoding="utf-8-sig", newline="") as dst:
                dst.write(src.read())
        except OSError:
            return DEFAULT_CSV
    return path


def load(path: Optional[str] = None) -> Locations:
    """The berth list: the user's rows, plus any built-in rows for berths the user's list does not have."""
    sheets = _parse(_read(DEFAULT_CSV))
    path = path or user_path()
    warning = ""
    if os.path.exists(path) and os.path.abspath(path) != os.path.abspath(DEFAULT_CSV):
        try:
            mine = _parse(_read(path))
        except OSError as exc:
            mine, warning = {}, f"Your berth list ({path}) could not be read ({exc}); the built-in list was used."
        for sheet, rows in mine.items():
            sheets.setdefault(sheet, {}).update(rows)
    return Locations(sheets, path, warning)
