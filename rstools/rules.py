"""Network Rail rules the app uses, the rule sets the user has added, and the new-timetable reminder.

* Built in: the headcode (service group) descriptions from the Timetable Planning Rules 2027 (v4).
* Added by the user: Section 4 (Engineering Access Statement, Standard Possession Opportunities) rule sets. The
  PDFs are read once and only what the Section 4 check needs is kept, compressed, in the settings folder
  (rules/<name>.json.gz) - the PDFs themselves are not copied, so the app does not grow. One set is 'in use'.
* The first time a timetable from Dec 27 onwards is opened, the user is reminded to check the latest rules are
  loaded (once per timetable).
"""
from __future__ import annotations

import gzip
import json
import os
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Tuple

RULES_URL = "https://www.networkrail.co.uk/industry-and-commercial/information-for-operators/operational-rules/"
REMIND_FROM = "DEC27"           # the first timetable the new-timetable reminder applies to
BUILT_IN = [
    {"name": "Timetable Planning Rules 2027 (v4)", "kind": "Timetable Planning Rules",
     "use": "Service group (headcode) descriptions in the capacity report",
     "covers": "Sussex, Kent, Wessex, Anglia, East Midlands and LNE routes", "from": "2026-12-13",
     "to": "2027-12-11"},
]


def _dir() -> str:
    from rstools.branding import settings_dir
    path = os.path.join(settings_dir(), "rules")
    os.makedirs(path, exist_ok=True)
    return path


def _index_path() -> str:
    return os.path.join(_dir(), "rules.json")


def _load_index() -> dict:
    try:
        with open(_index_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(data: dict):
    from rstools.fsutil import write_json
    write_json(_index_path(), data)


# --------------------------------------------------------------------------- timetables
def _sunday_on_or_after(d: date) -> date:
    return d + timedelta(days=(6 - d.weekday()) % 7)


def change_dates(year: int):
    """The May and December timetable change dates of a year (third Sunday of May, second Sunday of
    December - e.g. 16 May 2027 and 12 December 2027)."""
    may = _sunday_on_or_after(date(year, 5, 1)) + timedelta(weeks=2)
    dec = _sunday_on_or_after(date(year, 12, 1)) + timedelta(weeks=1)
    return may, dec


def timetable_of(day: date) -> str:
    """'DEC27' / 'MAY28': the timetable a date falls in."""
    may, dec = change_dates(day.year)
    if day >= dec:
        return f"DEC{day.year % 100:02d}"
    if day >= may:
        return f"MAY{day.year % 100:02d}"
    return f"DEC{(day.year - 1) % 100:02d}"


def _tt_key(name: str):
    m = re.match(r"^(DEC|MAY)(\d\d)$", name)
    return (int(m.group(2)), 1 if m.group(1) == "DEC" else 0) if m else (0, 0)


def parse_date(text: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((text or "").strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def new_timetable_reminder(start: str) -> Optional[str]:
    """A reminder to check the rules, the first time a timetable (from Dec 27) is opened; None otherwise. The
    timetable is remembered, so each is reminded once."""
    day = parse_date(start)
    if day is None:
        return None
    tt = timetable_of(day)
    if _tt_key(tt) < _tt_key(REMIND_FROM):
        return None
    idx = _load_index()
    seen = idx.get("timetables_seen") or []
    if tt in seen:
        return None
    idx["timetables_seen"] = sorted(set(seen) | {tt}, key=_tt_key)
    _save_index(idx)
    active = active_set_info()
    lines = [f"This is the first time a {tt} timetable has been used.",
             "",
             "Check the latest Network Rail rules are loaded (Options > Rules and reference data):"]
    lines.append(f"  - Section 4 rule set in use: {active['name']}" if active else
                 "  - Section 4: no rule set added yet")
    for b in BUILT_IN:
        until = parse_date(b["to"])
        stale = until is not None and day > until
        lines.append(f"  - {b['name']} (built in){' - out of date for this timetable' if stale else ''}")
    lines += ["", f"The latest rules can be downloaded from Network Rail:\n{RULES_URL}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- Section 4 rule sets
def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ._()-]+", "-", name).strip(" .")[:80] or "Section 4"


def list_sets() -> List[dict]:
    """The Section 4 rule sets added, newest first: name, files, possessions, periods, added, active."""
    idx = _load_index()
    active = idx.get("active_section4", "")
    out = []
    for s in idx.get("section4", []):
        if isinstance(s, dict) and os.path.isfile(os.path.join(_dir(), s.get("file", ""))):
            out.append(dict(s, active=s.get("name") == active))
    return sorted(out, key=lambda s: s.get("added", ""), reverse=True)


def active_set_info() -> Optional[dict]:
    return next((s for s in list_sets() if s["active"]), None)


def in_use(today: Optional[date] = None) -> Tuple[str, bool]:
    """A short line saying which rules are in use - 'TPR 2027 (v4) · Section 4: 2027 EAS v4' - and whether any
    of them is out of date (past its last date) or missing."""
    today = today or date.today()
    tpr = BUILT_IN[0]
    tpr_name = tpr["name"].replace("Timetable Planning Rules", "TPR")
    until = parse_date(tpr["to"])
    stale = until is not None and today > until
    info = active_set_info()
    if info is None:
        s4 = "Section 4: none added"
        stale = True
    else:
        s4 = f"Section 4: {info['name']}"
        s4_until = parse_date(info.get("to", ""))
        stale = stale or (s4_until is not None and today > s4_until)
    return f"Rules: {tpr_name} \u00b7 {s4}" + (" (check)" if stale else ""), stale


def add_section4_set(name: str, pdfs: Sequence[str], log=lambda m: None) -> dict:
    """Read the Section 4 PDFs and keep what the check needs as a named rule set (made the one in use)."""
    from rstools.timetable.section4 import Section4Error, read_statement
    name = _safe(name)
    st = read_statement(pdfs, log)
    if not st.possessions:
        raise Section4Error("No Section 4 possessions were found in the PDF(s). Use Network Rail's Engineering "
                            "Access Statement Section 4 (Standard Possession Opportunities) PDFs.")
    data = {"name": name, "files": [os.path.basename(p) for p in pdfs], "warnings": st.warnings,
            "possessions": [_dump(p) for p in st.possessions]}
    fname = _safe(name) + ".json.gz"
    with gzip.open(os.path.join(_dir(), fname), "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    periods = sorted({(per.name, per.start.isoformat(), per.end.isoformat()) for p in st.possessions
                      for per in p.periods}, key=lambda x: x[1])
    info = {"name": name, "file": fname, "files": data["files"], "possessions": len(st.possessions),
            "sections": len({(p.route, p.number) for p in st.possessions}),
            "from": periods[0][1] if periods else "", "to": periods[-1][2] if periods else "",
            "added": datetime.now().isoformat(timespec="seconds")}
    idx = _load_index()
    idx["section4"] = [s for s in idx.get("section4", []) if s.get("name") != name] + [info]
    idx["active_section4"] = name
    _save_index(idx)
    return info


def remove_set(name: str):
    idx = _load_index()
    for s in idx.get("section4", []):
        if s.get("name") == name:
            try:
                os.remove(os.path.join(_dir(), s.get("file", "")))
            except OSError:
                pass
    idx["section4"] = [s for s in idx.get("section4", []) if s.get("name") != name]
    if idx.get("active_section4") == name:
        idx["active_section4"] = idx["section4"][-1]["name"] if idx["section4"] else ""
    _save_index(idx)


def use_set(name: str):
    idx = _load_index()
    if any(s.get("name") == name for s in idx.get("section4", [])):
        idx["active_section4"] = name
        _save_index(idx)


def load_set(name: str = ""):
    """A stored Section 4 rule set (the one in use unless named) as a section4.Statement, or None."""
    from rstools.timetable.section4 import Statement
    info = next((s for s in list_sets() if (s["name"] == name if name else s["active"])), None)
    if info is None:
        return None
    try:
        with gzip.open(os.path.join(_dir(), info["file"]), "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, EOFError):
        return None
    st = Statement([_load(p) for p in data.get("possessions", [])],
                   [f"{info['name']}: {f}" for f in data.get("files", [])], list(data.get("warnings", [])))
    return st


def _dump(p) -> dict:
    d = asdict(p)
    for per in d["periods"]:
        per["start"], per["end"] = per["start"].isoformat(), per["end"].isoformat()
    d["ends"] = list(d["ends"])
    return d


def _load(d: dict):
    from rstools.timetable.section4 import Period, Possession, Window
    periods = []
    for x in d.get("periods", []):
        start, end = parse_date(x.get("start", "")), parse_date(x.get("end", ""))
        if start is not None and end is not None:       # a damaged rule set: periods without dates are left out
            periods.append(Period(x.get("name", ""), start, end))
    windows = [Window(int(w["start"]), int(w["end"]), w["text"]) for w in d.get("windows", [])]
    return Possession(d.get("route", ""), d.get("section", ""), d.get("number", ""), tuple(d.get("ends", [])),
                      d.get("night", ""), periods, windows, d.get("blocked", ""), d.get("remarks", ""),
                      d.get("source", ""))


def coverage_warning(statement, start: str, end: str) -> Optional[str]:
    """A warning (with the download link) when the rules' periods do not cover the timetable's dates."""
    a, b = parse_date(start), parse_date(end)
    periods = [per for p in statement.possessions for per in p.periods]
    if not periods or not a:
        return None
    lo, hi = min(p.start for p in periods), max(p.end for p in periods)
    if a > hi or (b and b < lo) or a < lo:
        return (f"The Section 4 rules cover {lo:%d/%m/%Y} to {hi:%d/%m/%Y}, but the timetable starts {a:%d/%m/%Y}: "
                f"they may be out of date. Download the latest from {RULES_URL} and add them in Options > Rules "
                "and reference data.")
    return None
