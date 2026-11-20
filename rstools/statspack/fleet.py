"""Fleet reference data (operator, capacities, units available, spare units, unit length).

None of this is in the XML or the TRENT print, so a default table (taken from the
DEC26 stats pack) ships with the app. Users can edit their own copy (fleet.csv in
%LOCALAPPDATA%\\TrainPlanningTools) - the app creates it on first use and adds any new
classes / columns from later versions without touching the user's own values.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(HERE, "fleet_default.csv")
COLUMNS = ["Class Name", "Operator", "Power Type", "Vehicles per Unit", "First Class Seated Capacity",
           "Standard Class Seated Capacity", "Standing Capacity", "Total Capacity (excl. First Class)",
           "Units Available", "Spare Units", "Unit Length (metres)"]


def user_fleet_path() -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), "fleet.csv")


@dataclass
class FleetInfo:
    cls: str
    operator: str
    power: str
    cars: Optional[int]
    first: Optional[int]
    standard: Optional[int]
    standing: Optional[int]
    total: Optional[int]
    available: Optional[int]
    spare: Optional[int]
    length: Optional[float]


def _int(v) -> Optional[int]:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _float(v) -> Optional[float]:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _read_csv(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Header and rows of a fleet CSV (UTF-8, or the Windows encoding Excel may save it in)."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                reader = csv.DictReader(fh)
                rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
                return [(h or "").strip() for h in (reader.fieldnames or [])], rows
        except UnicodeDecodeError:
            continue
    return [], []


class FleetTable:
    def __init__(self, rows: List[FleetInfo], warning: str = ""):
        self.rows = rows
        self.warning = warning
        self._by = {r.cls: r for r in rows}

    def get(self, cls: str) -> Optional[FleetInfo]:
        return self._by.get(cls)

    def operator(self, cls: str) -> str:
        r = self._by.get(cls)
        return r.operator if r else ""

    @classmethod
    def load(cls, path: Optional[str] = None) -> "FleetTable":
        """The fleet table, re-read only when the file has changed (e.g. after Edit fleet data)."""
        path = path or ensure_user_copy()
        try:
            st = os.stat(path)
            key = (path, st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if key is not None and key in _LOADED:
            return _LOADED[key]
        table = cls._read(path)
        if key is not None:
            _LOADED.clear()
            _LOADED[key] = table
        return table

    @classmethod
    def _read(cls, path: str) -> "FleetTable":
        warning = ""
        try:
            _hdr, recs = _read_csv(path)
        except OSError as exc:
            warning = f"Your fleet data ({path}) could not be read ({exc}); the built-in fleet data was used."
            _hdr, recs = _read_csv(DEFAULT_CSV)
        rows = []
        for rec in recs:
            name = rec.get("Class Name", "")
            if not name:
                continue
            rows.append(FleetInfo(name, rec.get("Operator", "").upper(), rec.get("Power Type", ""),
                                  _int(rec.get("Vehicles per Unit")), _int(rec.get("First Class Seated Capacity")),
                                  _int(rec.get("Standard Class Seated Capacity")), _int(rec.get("Standing Capacity")),
                                  _int(rec.get("Total Capacity (excl. First Class)")),
                                  _int(rec.get("Units Available")), _int(rec.get("Spare Units")),
                                  _float(rec.get("Unit Length (metres)"))))
        return cls(rows, warning)


_LOADED: Dict[tuple, "FleetTable"] = {}
_CHECKED: List[str] = []                   # user copies already brought up to date this session


def ensure_user_copy() -> str:
    """The editable fleet table, created or brought up to date from the built-in one (once per
    session). Falls back to the built-in table if the user's copy cannot be written."""
    path = user_fleet_path()
    if path in _CHECKED and os.path.exists(path):
        return path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _upgrade(path)
        _CHECKED.append(path)
    except OSError:
        return path if os.path.exists(path) else DEFAULT_CSV
    return path


# figures earlier versions shipped as placeholders (all zero): replaced by the real ones when a user's copy
# still holds exactly these, never when the user entered their own
_SEAT_COLS = ("First Class Seated Capacity", "Standard Class Seated Capacity", "Standing Capacity",
              "Total Capacity (excl. First Class)")
_OLD_PLACEHOLDERS = {"379/0": ("0", "0", "0", "0")}


def _upgrade(path: str):
    """Add new classes and columns from the built-in table; fill cells the user left blank or
    'Unknown'. Values the user entered are never changed."""
    _dh, default = _read_csv(DEFAULT_CSV)
    if not os.path.exists(path):
        _write(path, default)
        return
    hdr, user = _read_csv(path)
    if not hdr:
        return                                  # unreadable - leave it for the user to fix
    by_name = {r.get("Class Name", ""): r for r in user}
    changed = any(c not in hdr for c in COLUMNS)
    for d in default:
        u = by_name.get(d["Class Name"])
        if u is None:
            user.append(dict(d))
            changed = True
            continue
        old = _OLD_PLACEHOLDERS.get(d["Class Name"])
        if old and tuple(str(u.get(c, "")).strip() for c in _SEAT_COLS) == old:
            for c in _SEAT_COLS:
                u[c] = d[c]
            changed = True
        for col in COLUMNS:
            if d.get(col) and u.get(col, "") in ("", "Unknown"):
                u[col] = d[col]
                changed = True
    if changed:
        _write(path, user)


def _write(path: str, rows: List[Dict[str, str]]):
    from rstools.fsutil import atomic_path
    with atomic_path(path) as tmp, open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
