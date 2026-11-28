"""Stabling locations: the places units stable (berth) overnight that are not depots - sidings, yards, stations'
platforms. They are listed apart from the depots (Settings > Stabling locations) and never count as a depot, even
when the name says 'Shed' (Littlehampton Shed, Streatham Hill Shed are sidings).

The built-in list holds the known ones; the user's copy (stabling.csv in the data folder) is made from it on first
use, and a place found in a run's inputs that is in neither list (nor a depot) is added to it automatically, with
the file and date it was found in (learn). Nothing here ever stops a run: a list that cannot be read or written is
left as it is."""
from __future__ import annotations

import csv
import datetime
import os
import threading
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STABLING = os.path.join(HERE, "stabling_default.csv")
COLUMNS = ["TIPLOC", "Location", "Operator", "Found"]
_LOCK = threading.Lock()


def user_stabling_path() -> str:
    from .fleet import user_fleet_path
    return os.path.join(os.path.dirname(user_fleet_path()), "stabling.csv")


def ensure_user_stabling() -> str:
    """The editable list (created from the built-in one on first use)."""
    path = user_stabling_path()
    if not os.path.exists(path):
        from rstools.fsutil import copy_default
        if not copy_default(DEFAULT_STABLING, path):
            return DEFAULT_STABLING
    return path


def read_rows(path: str) -> List[Dict[str, str]]:
    """The list's rows ([] if it is missing, too large or cannot be read)."""
    from rstools import limits
    try:
        limits.check_size(path, "SETTINGS_CSV_MAX_BYTES", "stabling location list")
    except OSError:
        return []
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                return [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh)]
        except UnicodeDecodeError:
            continue
        except OSError:
            return []
    return []


def keys(path: Optional[str] = None) -> Set[str]:
    """Every location in the stabling lists (built-in and the user's), as upper-case TIPLOCs (or the location
    names a TLGN print uses, which are kept in the TIPLOC column too). The Location column is only a label."""
    out: Set[str] = set()
    for p in (DEFAULT_STABLING, path or user_stabling_path()):
        for r in read_rows(p):
            if r.get("TIPLOC"):
                out.add(r["TIPLOC"].upper())
    return out


def _write(path: str, rows: List[Dict[str, str]]) -> bool:
    from rstools.fsutil import atomic_path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with atomic_path(path) as tmp, open(tmp, "x", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        return True
    except OSError:
        return False


def add_rows(new: Iterable[Dict[str, str]], path: Optional[str] = None) -> List[Dict[str, str]]:
    """Add rows (TIPLOC, Location, Operator, Found) for locations not in the lists yet; returns those added."""
    with _LOCK:
        if path and not os.path.exists(path):
            from rstools.fsutil import copy_default
            copy_default(DEFAULT_STABLING, path)       # a new list starts from the built-in one
        path = path or ensure_user_stabling()
        if os.path.abspath(path) == os.path.abspath(DEFAULT_STABLING):
            return []                                  # the data folder cannot be written: nothing kept
        rows = read_rows(path)
        have = keys(path)
        added = []
        for r in new:
            tip = (r.get("TIPLOC") or "").strip()
            if not tip or tip.upper() in have:
                continue
            row = {c: (r.get(c) or "").strip() for c in COLUMNS}
            added.append(row)
            have.add(tip.upper())
        if added and not _write(path, rows + added):
            return []
        return added


def learn(places: Iterable[Tuple[str, str, str]], is_depot: Callable[[str], bool], source: str,
          log: Callable[[str], None] = lambda m: None) -> List[str]:
    """Add the places units were found stabling at (TIPLOC or name, location name, operator) that are not depots
    and not listed yet; each is noted in the log. Returns the names added. Never raises."""
    try:
        found = f"{os.path.basename(source)} {datetime.date.today():%d/%m/%Y}" if source else \
            f"{datetime.date.today():%d/%m/%Y}"
        new = [{"TIPLOC": tip, "Location": name or tip, "Operator": op, "Found": found}
               for tip, name, op in places if tip and not is_depot(tip)]
        added = add_rows(new)
    except Exception:                                  # a list is never worth stopping a run for
        return []
    names = [f"{r['Location']} ({r['TIPLOC']})" if r["Location"] != r["TIPLOC"] else r["TIPLOC"] for r in added]
    if names:
        log(f"New stabling location{'s' if len(names) > 1 else ''} added to Settings > Stabling locations: "
            + ", ".join(names[:12]) + (f" and {len(names) - 12} more" if len(names) > 12 else ""))
    return names
