"""Network Rail rules the app uses, the rule sets the user has added, and the new-timetable reminder.

* Built in: the headcode (service group) descriptions from the Timetable Planning Rules 2027 (v4), and a Section 4
  rule set read from the 2027 EAS v4 Section 4 PDFs (Kent & Sussex, Anglia, East Coast, East Midlands, Wessex),
  in use until the user adds or chooses another.
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
BUILT_IN_S4 = "2027 EAS v4 (built in)"     # the Section 4 rule set shipped with the app
BUILT_IN_S4_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timetable", "section4_builtin.json.gz")
_builtin_cache: dict = {}


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


def _builtin_data() -> Optional[dict]:
    """The built-in Section 4 rule set as stored (read once), or None if it is missing or damaged."""
    if "data" not in _builtin_cache:
        try:
            with gzip.open(BUILT_IN_S4_FILE, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            _builtin_cache["data"] = data if isinstance(data, dict) and data.get("possessions") else None
        except (OSError, ValueError, EOFError):
            _builtin_cache["data"] = None
    return _builtin_cache["data"]


def _builtin_info() -> Optional[dict]:
    data = _builtin_data()
    if data is None:
        return None
    return dict(data.get("info", {}), name=BUILT_IN_S4, files=list(data.get("files", [])), added="",
                built_in=True)


def list_sets() -> List[dict]:
    """The Section 4 rule sets, those added newest first, then the built-in one: name, files, possessions,
    periods, added, active, built_in. The built-in set is in use unless an added set has been chosen."""
    idx = _load_index()
    active = idx.get("active_section4", "")
    out = []
    for s in idx.get("section4", []):
        if isinstance(s, dict) and os.path.isfile(os.path.join(_dir(), s.get("file", ""))):
            out.append(dict(s, active=s.get("name") == active, built_in=False))
    out.sort(key=lambda s: s.get("added", ""), reverse=True)
    builtin = _builtin_info()
    if builtin is not None:
        out.append(dict(builtin, active=not any(s["active"] for s in out)))
    return out


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


def _read_set(name: str, pdfs: Sequence[str], log) -> Tuple[dict, dict]:
    """Read Section 4 PDFs: (the data to store, a summary - possessions, sections, from, to)."""
    from rstools.timetable.section4 import Section4Error, read_statement
    st = read_statement(pdfs, log)
    if not st.possessions:
        raise Section4Error("No Section 4 possessions were found in the PDF(s). Use Network Rail's Engineering "
                            "Access Statement Section 4 (Standard Possession Opportunities) PDFs.")
    periods = sorted({(per.name, per.start.isoformat(), per.end.isoformat()) for p in st.possessions
                      for per in p.periods}, key=lambda x: x[1])
    summary = {"possessions": len(st.possessions), "sections": len({(p.route, p.number) for p in st.possessions}),
               "from": periods[0][1] if periods else "", "to": periods[-1][2] if periods else ""}
    data = {"name": name, "files": [os.path.basename(p) for p in pdfs], "warnings": st.warnings,
            "possessions": [_dump(p) for p in st.possessions]}
    return data, summary


def _write_gz(path: str, data: dict):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))


def build_builtin_set(pdfs: Sequence[str], out: str = BUILT_IN_S4_FILE, log=print) -> dict:
    """Make the built-in Section 4 rule set shipped with the app from Network Rail's Section 4 PDFs (run when
    building a release with new rules: python -m rstools.rules PDF...)."""
    data, summary = _read_set(BUILT_IN_S4, pdfs, log)
    data["info"] = summary
    _write_gz(out, data)
    _builtin_cache.clear()
    return summary


def add_section4_set(name: str, pdfs: Sequence[str], log=lambda m: None) -> dict:
    """Read the Section 4 PDFs and keep what the check needs as a named rule set (made the one in use)."""
    name = _safe(name)
    if name == BUILT_IN_S4:
        name = name.replace("(built in)", "(added)")
    data, summary = _read_set(name, pdfs, log)
    fname = _safe(name) + ".json.gz"
    _write_gz(os.path.join(_dir(), fname), data)
    info = dict(summary, name=name, file=fname, files=data["files"], added=datetime.now().isoformat(timespec="seconds"))
    idx = _load_index()
    idx["section4"] = [s for s in idx.get("section4", []) if s.get("name") != name] + [info]
    idx["active_section4"] = name
    _save_index(idx)
    return info


def remove_set(name: str):
    """Remove an added rule set (the built-in one cannot be removed)."""
    if name == BUILT_IN_S4:
        return
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
    if name == BUILT_IN_S4 or any(s.get("name") == name for s in idx.get("section4", [])):
        idx["active_section4"] = name
        _save_index(idx)


def load_set(name: str = ""):
    """A stored Section 4 rule set (the one in use unless named) as a section4.Statement, or None."""
    from rstools.timetable.section4 import Statement
    info = next((s for s in list_sets() if (s["name"] == name if name else s["active"])), None)
    if info is None:
        return None
    if info.get("built_in"):
        data = _builtin_data()
        if data is None:
            return None
    else:
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


if __name__ == "__main__":                       # rebuild the built-in Section 4 rule set from new PDFs
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -m rstools.rules SECTION4.pdf [SECTION4.pdf ...]")
    print(build_builtin_set(sys.argv[1:]))
