"""The locations a berthing chart starts from, for each operator, kept as a 'location set' the user can change.

SNGX starts from the app's built-in layout (layout.load_default); a set saved in the settings folder replaces its
sheets. TLGN has no built-in layout: its set is made in the app from an XML (Settings > Berthing locations > Make
from XML...), and until one is saved every TLGN chart is laid out from its own XML, as before.

A set is the chart's sheets in the layout's own form (layout.to_dict): each sheet's berths, capacities and notes;
a sheet made from an XML also has its 'TIPLOC <code>' line, and each berth the platform / road codes it stands for.
Saved as berth_set_<OPERATOR>.json in the settings folder (rstools.branding.settings_dir)."""
from __future__ import annotations

import copy
import datetime
import json
import os
from typing import Dict, List, Optional

from . import auto
from .layout import Block, GridSheet, Layout, from_dict, load_default, to_dict
from .mapping import norm

FIELDS = ("Sheet", "Location", "Berth", "Capacity", "TIPLOC", "Codes")   # the rows in Settings > Berthing locations


def path(operator: str) -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), f"berth_set_{operator.upper()}.json")


def _clean(text) -> str:
    from rstools.fsutil import clean_cell
    return " ".join(str(clean_cell(str(text or ""))).split())[:200]


def _data(operator: str) -> Optional[dict]:
    from rstools import limits
    p = path(operator)
    try:
        if os.path.getsize(p) > limits.get("BERTH_SET_MAX_BYTES"):
            return None
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("sheets"), list) else None


def stored_sheets(operator: str) -> Optional[list]:
    """The sheets of the operator's saved set; None when there is none (or it cannot be read)."""
    data = _data(operator)
    if data is None:
        return None
    try:
        return from_dict({"sheets": data["sheets"]}).sheets
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def has_set(operator: str) -> bool:
    return stored_sheets(operator) is not None


def base_layout(operator: str) -> Layout:
    """The built-in layout (its cover, legend and sheets), with the operator's saved sheets in place of its own.
    For TLGN with no saved set, the built-in sheets are returned; the chart then makes its sheets from the XML."""
    layout = load_default()
    sheets = stored_sheets(operator)
    if sheets is not None:
        layout.sheets = sheets
        layout.path = f"your {operator.upper()} locations (Settings > Berthing locations)"
    return layout


def info(operator: str) -> dict:
    """What the Settings window says about a set: whether one is saved, where from, when, and its size."""
    data = _data(operator)
    if data is not None:
        sheets = stored_sheets(operator) or []
        return {"saved": True, "source": str(data.get("source", "")), "made": str(data.get("made", "")),
                "sheets": len(sheets), "berths": sum(len(s.blocks) for s in sheets if isinstance(s, GridSheet))}
    if operator.upper() == "SNGX":
        layout = load_default()
        return {"saved": False, "source": "the app's built-in layout", "made": "", "sheets": len(layout.sheets),
                "berths": sum(len(s.blocks) for s in layout.sheets if isinstance(s, GridSheet))}
    return {"saved": False, "source": "", "made": "", "sheets": 0, "berths": 0}


def save(operator: str, sheets: list, source: str = "") -> bool:
    """Save the operator's set (atomically); False if the settings folder cannot be written."""
    from rstools.fsutil import write_json
    data = to_dict(Layout("", "Cover", [], list(sheets)))
    return write_json(path(operator), {"operator": operator.upper(), "source": _clean(source),
                                       "made": datetime.date.today().isoformat(), "sheets": data["sheets"]})


def reset(operator: str) -> None:
    """Forget the saved set: SNGX goes back to the built-in layout, TLGN to a layout made from each XML."""
    try:
        os.remove(path(operator))
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------ editing as rows
def rows(operator: str, builtin: bool = False) -> List[Dict[str, str]]:
    """The set as rows of Sheet / Berth / Capacity / TIPLOC / Codes: the saved set (unless `builtin`), else for
    SNGX the built-in layout (TIPLOCs and codes from the berth list), else none."""
    from .mapping import load as load_locations
    sheets = None if builtin else stored_sheets(operator)
    if sheets is None:
        sheets = load_default().sheets if operator.upper() == "SNGX" else []
    locations = load_locations()
    out = []
    for sh in sheets:
        if not isinstance(sh, GridSheet):
            continue
        made = _from_xml(sh)
        for b in sh.blocks:
            br = None if made else locations.berth(sh.name, b.label)
            codes = b.codes or ("" if made else ";".join(c for c in (br.codes if br else ()) if c != "*"))
            where = sh.sections[b.section] if len(sh.sections) > 1 and 0 <= b.section < len(sh.sections) else ""
            out.append({"Sheet": sh.name, "Location": where, "Berth": b.label, "Capacity": b.capacity,
                        "TIPLOC": auto.berth_tiploc(sh, b) if made else (br.tiploc if br else ""), "Codes": codes})
    return out


def _from_xml(sheet) -> bool:
    """A sheet made from an XML: its berths carry their own TIPLOCs (not the berth list)."""
    return bool(auto.sheet_tiplocs(sheet) or any(b.tiploc for b in getattr(sheet, "blocks", [])))


def sheets_from_rows(operator: str, table: List[Dict[str, str]]) -> list:
    """The sheets for edited rows, in the rows' order. A berth that was there before keeps its notes; the
    Location column gives each siding location on a sheet (its banner), in order. A sheet made from an XML (all
    TLGN sheets, and any new sheet) keeps each berth's TIPLOC and gets 'TIPLOC' lines, so its berths are found
    without the berth list. Depot sheets of the layout (SNGX) are kept as they are."""
    before = stored_sheets(operator)
    if before is None:
        before = load_default().sheets if operator.upper() == "SNGX" else []
    old_sheets = {norm(s.name): s for s in before}
    out: list = []
    by_name: Dict[str, GridSheet] = {}
    for r in table:
        name, label = _clean(r.get("Sheet", ""))[:31], _clean(r.get("Berth", ""))
        if not name or not label:
            continue
        old_sheet = old_sheets.get(norm(name))
        sh = by_name.get(norm(name))
        if sh is None:
            if isinstance(old_sheet, GridSheet):
                sh = copy.deepcopy(old_sheet)
                sh.name, sh.blocks, sh.sections = name, [], []
            else:
                sh = GridSheet(name, corner=("Siding", "Capacity"))
            sh.preface = [(a, b) for a, b in sh.preface if not auto._TIPLOC.match(a)]
            by_name[norm(name)] = sh
            out.append(sh)
        where = _clean(r.get("Location", "")) or (sh.sections[-1] if sh.sections else name)   # blank: as above
        if norm(where) not in [norm(x) for x in sh.sections]:
            sh.sections.append(where)
        section = [norm(x) for x in sh.sections].index(norm(where))
        was = next((b for b in getattr(old_sheet, "blocks", []) if norm(b.label) == norm(label)), None)
        blk = copy.deepcopy(was) if was is not None else Block(label)
        blk.label, blk.capacity, blk.section = label, _clean(r.get("Capacity", "")), section
        blk.codes = ";".join(c.strip().upper() for c in _clean(r.get("Codes", "")).replace(",", ";").split(";")
                             if c.strip())
        tip = _clean(r.get("TIPLOC", "")).upper()
        xml_sheet = operator.upper() != "SNGX" or not isinstance(old_sheet, GridSheet) or _from_xml(old_sheet)
        blk.tiploc = tip if xml_sheet else ""
        blk.units = {}
        sh.blocks.append(blk)
    for sh in out:                                         # the 'TIPLOC' lines: one per siding location
        if not any(b.tiploc for b in sh.blocks):
            continue
        if len(sh.sections) == 1:
            tip = next(b.tiploc for b in sh.blocks if b.tiploc)
            sh.preface.insert(0, (f"{auto.TIPLOC_LINE} {tip}", ""))
            continue
        lines = []
        for i, sec in enumerate(sh.sections):
            tip = next((b.tiploc for b in sh.blocks if b.section == i and b.tiploc), "")
            if tip:
                lines.append((f"{auto.TIPLOC_LINE} {tip} \u2013 {sec}", ""))
        sh.preface = lines + sh.preface
    for s in before:                                       # depot sheets are not edited here
        if not isinstance(s, GridSheet):
            out.append(s)
    return out


def save_rows(operator: str, table: List[Dict[str, str]], source: str = "") -> bool:
    """Save edited rows as the operator's set. For SNGX the TIPLOC and codes of each berth also go in the berth
    list (berth_locations.csv), which the built-in sheets are matched by."""
    sheets = sheets_from_rows(operator, table)
    ok = save(operator, sheets, source or "edited in Settings")
    if ok and operator.upper() == "SNGX":
        ok = _save_berth_list([r for r in table if r.get("TIPLOC")])
    return ok


def _save_berth_list(table: List[Dict[str, str]]) -> bool:
    """The rows' TIPLOCs and codes into the user's berth list, replacing its rows for those berths."""
    import csv
    import io
    from rstools.fsutil import atomic_path
    from . import mapping
    src = mapping.ensure_user_copy()
    try:
        old = mapping._read(src)
    except OSError:
        old = []
    keys = {(norm(r["Sheet"]), norm(r["Berth"])) for r in table}
    kept = [r for r in old if (norm(r.get("Sheet", "")), norm(r.get("Berth", ""))) not in keys]
    new = [{"Sheet": _clean(r["Sheet"]), "Berth": _clean(r["Berth"]), "TIPLOC": _clean(r["TIPLOC"]).upper(),
            "Codes": _clean(r.get("Codes", "")) or "*", "Note": ""} for r in table]
    buf = io.StringIO()
    w = csv.DictWriter(buf, ["Sheet", "Berth", "TIPLOC", "Codes", "Note"], extrasaction="ignore")
    w.writeheader()
    for r in kept + new:
        w.writerow({k: r.get(k, "") for k in ("Sheet", "Berth", "TIPLOC", "Codes", "Note")})
    try:
        target = mapping.user_path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with atomic_path(target) as tmp, open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(buf.getvalue())
        return True
    except OSError:
        return False
