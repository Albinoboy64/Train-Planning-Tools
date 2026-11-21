"""Platform lengths from Network Rail's Timetable Planning Rules 2027 (section 5.4.2, usable length ramp to ramp)
for the Sussex, Kent, Wessex, Anglia, East Midlands and LNE routes, and a check of train length against them.

platform_lengths.csv ships with the app: one row per platform with the station's TIPLOC (as GTR's Attune XML
names it) where known, the station name as in the rules, the platform, its usable length in metres and the
rules' own notes (e.g. '8 cars', 'to Signal TVC 497'). A platform listed twice (two lengths, e.g. to two
signals) is checked against the longer one.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "platform_lengths.csv")
SOURCE = "Network Rail Timetable Planning Rules 2027 (v4)"
TOLERANCE = 3.0       # metres: unit lengths are nominal, so a train within this of the platform is not flagged


@dataclass
class Platform:
    station: str
    platform: str
    length: int
    notes: str


class PlatformTable:
    def __init__(self, rows: Iterable[dict]):
        self.by_tip: Dict[str, Dict[str, Platform]] = {}
        self.by_name: Dict[str, Dict[str, Platform]] = {}
        for r in rows:
            try:
                length = int(float(r.get("Usable length (m)") or 0))
            except ValueError:
                continue
            if length <= 0:
                continue
            plat = (r.get("Platform") or "").strip().upper()
            p = Platform((r.get("Station") or "").strip(), plat, length, (r.get("Notes") or "").strip())
            targets = [self.by_tip.setdefault(t.strip().upper(), {}) for t in (r.get("TIPLOC") or "").split(";")
                       if t.strip()]
            targets.append(self.by_name.setdefault(_key(p.station), {}))
            for table in targets:
                old = table.get(plat)
                if old is None or length > old.length:
                    table[plat] = p

    @classmethod
    def load(cls, path: str = TABLE) -> "PlatformTable":
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                return cls(csv.DictReader(fh))
        except OSError:
            return cls([])

    def find(self, tiploc: str, platform: str, name: str = "") -> Optional[Platform]:
        """The platform a train uses: by TIPLOC (else station name) and platform number. A station listed with
        one platform and no number (a single platform) matches any platform there."""
        table = self.by_tip.get((tiploc or "").upper()) or (self.by_name.get(_key(name)) if name else None)
        if not table:
            return None
        plat = (platform or "").strip().upper()
        if plat in table:
            return table[plat]
        if len(table) == 1 and "" in table:
            return table[""]
        return None


def _key(name: str) -> str:
    from rstools.statspack.seats import _norm
    return _norm(name)


_TABLE: List[PlatformTable] = []


def table() -> PlatformTable:
    if not _TABLE:
        _TABLE.append(PlatformTable.load())
    return _TABLE[0]


def too_long(length: Optional[float], p: Optional[Platform]) -> bool:
    return bool(length and p and length > p.length + TOLERANCE)


def describe(p: Platform, length: float) -> str:
    return f"{length:.0f} m on a {p.length} m platform" + (f" ({p.notes})" if p.notes else "")


def train_length(fleets: List[str], unit_length: Dict[str, float]) -> Tuple[Optional[float], List[str]]:
    """Length of a formation (the fleet of each unit), and the fleets with no length in the fleet table."""
    missing = [f for f in fleets if not unit_length.get(f)]
    if missing or not fleets:
        return None, missing
    return sum(unit_length[f] for f in fleets), []
