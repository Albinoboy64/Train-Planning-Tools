"""Stats pack comparisons.

* compare two plans (XML + TRENT sets): both packs are built with the same options and the
  newer one is written with every difference highlighted;
* compare two stats pack workbooks (made by this app or by TRACS-RS): read back and compared
  the same way.

Changed cells are highlighted amber, rows only in the new pack green, rows only in the old
pack are added at the bottom of the tab in red (struck through).  A 'Differences' tab
lists every change with the old value, new value and the change.
"""
from __future__ import annotations

import html
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from rstools import safexml
from .stats import Clock, Dur, Row, Table, TAB_ORDER
from .xlsxw import HIGHLIGHT, LAYOUT, Workbook, nowrap, font_size, fit_columns, fmt_dur

# columns identifying a row in each tab (0-based, before any Day column)
KEYS = {
    "Fleet": 1, "Service Miles": 1, "Diagram Summary": 3, "Formation Data": 2, "Diagram Data": 2,
    "Calling Pattern (stops+passes)": 3, "Calling Pattern (stops only)": 3,
}
EXTRA_KEY = {"Formation Data": [7], "Diagram Data": [14, 15]}     # departure / depot+diagram


@dataclass
class Diff:
    tab: str
    key: str
    column: str
    old: object
    new: object
    change: str
    flag: bool = False                 # a mileage increase over the threshold


def _key_cols(t: Table) -> List[int]:
    shift = 1 if t.has_day else 0
    base = list(range(KEYS.get(t.name, 1)))
    cols = [c + shift for c in base + EXTRA_KEY.get(t.name, [])]
    return ([0] if shift else []) + cols


def _norm(v):
    if v is None or type(v) is int:
        return v
    if isinstance(v, (Clock, Dur)):
        return int(v)
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, str):
        t = v.strip()
        m = re.match(r"^(-?)(\d+):(\d\d):(\d\d)$", t)
        if m:
            sec = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4))
            return -sec if m.group(1) else sec
        try:
            return round(float(t), 2)
        except ValueError:
            return t
    return v


def _is_time(v) -> bool:
    return isinstance(v, (Clock, Dur)) or (isinstance(v, str) and bool(re.match(r"^-?\d+:\d\d:\d\d$", v.strip())))


def _change(old, new) -> str:
    a, b = _norm(old), _norm(new)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        d = b - a
        if not d:
            return "0"
        if _is_time(old) or _is_time(new):
            return ("+" if d >= 0 else "") + fmt_dur(int(d))
        shown = f"{d:.2f}" if isinstance(d, float) and not float(d).is_integer() else f"{d:g}"
        return ("+" if d >= 0 else "") + shown
    return ""


def is_mileage(header: str) -> bool:
    h = header.lower()
    return "mile" in h or h.startswith("distance")


def diff_table(old: Table, new: Table, headers: List[str], flag_over: Optional[float] = None):
    """Returns (marks for the new table, removed rows to append, list of Diff). With flag_over,
    mileage that goes up by more than that many miles (or a new row with more) is flagged."""
    kc = _key_cols(new)
    # vehicle miles are unit miles x cars, so only train / unit / formation mileage is flagged
    miles = ({c for c, h in enumerate(headers) if is_mileage(h)}
             if flag_over and "Vehicle" not in new.name else set())
    limit = flag_over or 0.0                # only used when flagging is on (miles is empty otherwise)

    def label_of(row: Row) -> str:
        """How a row is named in the Differences tab, e.g. '1A02BI / 05:40:00'."""
        return " / ".join(str(_show(row.cells[c])) for c in kc
                          if c < len(row.cells) and row.cells[c] not in (None, ""))

    def keyed(t: Table):
        out: Dict[tuple, int] = {}
        seen: Dict[tuple, int] = defaultdict(int)
        for i, r in enumerate(t.rows):
            k = tuple(_norm(r.cells[c]) if c < len(r.cells) else None for c in kc)
            seen[k] += 1
            out[k + (seen[k],)] = i
        return out
    ko, kn = keyed(old), keyed(new)
    marks: Dict[Tuple[int, int], str] = {}
    diffs: List[Diff] = []
    removed: List[Row] = []
    for k, ni in kn.items():
        oi = ko.get(k)
        nrow = new.rows[ni]
        label = label_of(nrow)
        if oi is None:
            marks[(ni, -1)] = "added"
            diffs.append(Diff(new.name, label, "(row)", "", "added", ""))
            for c in miles:
                v = _norm(nrow.cells[c]) if c < len(nrow.cells) else None
                if isinstance(v, (int, float)) and v > limit and nrow.kind != "total":
                    marks[(ni, c)] = "flagged"
                    diffs.append(Diff(new.name, label, headers[c], "", _show(nrow.cells[c]), f"+{v:g}", True))
            continue
        orow = old.rows[oi]
        if orow.cells == nrow.cells:
            continue
        for c in range(max(len(nrow.cells), len(orow.cells))):
            a = orow.cells[c] if c < len(orow.cells) else None
            b = nrow.cells[c] if c < len(nrow.cells) else None
            if a != b and _norm(a) != _norm(b):
                na, nb = _norm(a), _norm(b)
                up = (c in miles and isinstance(na, (int, float)) and isinstance(nb, (int, float))
                      and nb - na > limit)
                marks[(ni, c)] = "flagged" if up else "changed"
                diffs.append(Diff(new.name, label, headers[c] if c < len(headers) else f"Column {c + 1}",
                                  _show(a), _show(b), _change(a, b), up))
    for k, oi in ko.items():
        if k not in kn:
            removed.append(Row(old.rows[oi].cells, old.rows[oi].kind))
            diffs.append(Diff(new.name, label_of(old.rows[oi]), "(row)", "removed", "", ""))
    base = len(new.rows)
    for j in range(len(removed)):
        marks[(base + j, -1)] = "removed"
    return marks, removed, diffs


def _show(v):
    if isinstance(v, Clock):
        return "%02d:%02d:%02d" % (v // 3600, v % 3600 // 60, v % 60)
    if isinstance(v, Dur):
        return fmt_dur(int(v))
    if v is None:
        return ""
    return v


def headers_of(t: Table) -> List[str]:
    spec = LAYOUT[t.name]
    hdr = {c: v for c, v, _s in spec["header"][-1] if v}
    for row in spec["header"][:-1]:
        for c, v, _s in row:
            if v and c not in hdr:
                hdr[c] = v
    n = max(hdr) if hdr else 0
    out = [hdr.get(c, "") or "" for c in range(1, n + 1)]
    # group labels for repeated hour / peak blocks
    if len(spec["header"]) > 1:
        top = {c: v for c, v, _s in spec["header"][0] if v}
        cur = ""
        for c in range(1, n + 1):
            cur = top.get(c, cur)
            cur = "" if cur == "None" else cur      # TRACS-RS's unnamed service-code group
            if cur and c > 2:
                out[c - 1] = f"{cur} {out[c - 1]}".strip()
    return (["Day"] if t.has_day else []) + out


@dataclass
class CompareOptions:
    summary: bool = True               # headline figures (miles, units, time, trains) at the top
    changed_tabs_only: bool = False    # leave out tabs with no differences
    changed_rows_only: bool = False    # on each tab, only rows that changed (plus totals)
    flag_miles: Optional[float] = 10.0  # flag mileage increases over this many miles (None = off)


def _total_row(t: Optional[Table], label: str = "Total") -> Optional[Row]:
    if t is None:
        return None
    for r in t.rows:
        if r.kind == "total" and label in [c for c in r.cells[:2] if isinstance(c, str)]:
            return r
    return None


def _last(r: Optional[Row]):
    if r is None:
        return None
    vals = [c for c in r.cells if c not in (None, "")]
    return vals[-1] if vals else None


def _cell(r: Optional[Row], i: int):
    if r is None:
        return None
    cells = [c for c in r.cells if not (isinstance(c, str) and c.startswith("Total"))]
    cells = cells[len(cells) - 3:] if len(cells) >= 3 else cells      # empty, in service, total
    return cells[i] if i < len(cells) else None


def _sum_col(t: Optional[Table], col: int):
    if t is None:
        return None
    shift = 1 if t.has_day else 0
    total: float = 0
    for r in t.rows:
        if r.kind == "total":
            continue
        v = _norm(r.cells[col + shift]) if col + shift < len(r.cells) else None
        if isinstance(v, (int, float)):
            total += v
    return total


def headline(tables: Dict[str, Table]) -> List[Tuple[str, object]]:
    """The figures a planner checks first, from a pack's tabs (totals tabs where present)."""
    sm = tables.get("Service Miles")
    unit = _total_row(tables.get("Mileage by Unit"))
    veh = _total_row(tables.get("Vehicle Mileage by Service Code"))
    dt = _total_row(tables.get("Diagrammed Time by Unit"))
    wt = _total_row(tables.get("Wheel Turning Time by Unit"))
    ds = tables.get("Diagram Summary")
    side = (sm.side if sm is not None and sm.side else [None, None])
    return [
        ("Trains in service", side[0]), ("Empty trains", side[1]),
        ("Train miles - loaded", _last(_total_row(sm, "Total (Loaded)"))),
        ("Train miles - empty", _last(_total_row(sm, "Total (Empty)"))),
        ("Train miles - total", _last(_total_row(sm, "Total"))),
        ("Unit miles - empty", _cell(unit, 0)), ("Unit miles - in service", _cell(unit, 1)),
        ("Unit miles - total", _cell(unit, 2)), ("Vehicle miles - total", _cell(veh, 2)),
        ("Diagrammed time (units)", _cell(dt, 2)), ("Wheel-turning time (units)", _cell(wt, 2)),
        ("Diagrams", None if ds is None else sum(1 for r in ds.rows if r.kind != "total")),
        ("Units in use (Fleet tab)", _sum_col(tables.get("Fleet"), 8)),
        ("Vehicles in use (Fleet tab)", _sum_col(tables.get("Fleet"), 11)),
    ]


def summary_rows(old: Dict[str, Table], new: Dict[str, Table]) -> List[Tuple[str, object, object, str]]:
    def shown(v):
        return "???" if v is None else _show(v)        # unknown (e.g. no car count for a fleet)
    return [(label, shown(a), shown(b), _change(a, b) if a is not None and b is not None else "")
            for (label, a), (_l, b) in zip(headline(old), headline(new))]


def write_differences(wb: Workbook, diffs: Sequence[Diff], title: str, summary=None,
                      flag_miles: Optional[float] = None):
    """The 'Differences' tab: headline figures (old / new / change), differences per tab, then
    every difference with its old and new value."""
    spec = LAYOUT["Service Miles"]
    st = wb.styles
    sw = wb.new_sheet()
    head = st.xf(spec["header"][0][1][2])
    body = spec["body"]["2"]
    xb = st.xf(nowrap(body))
    widths = [0] * 6

    def put(vals, style=xb):
        sw.row([(i, v, style) for i, v in enumerate(vals, start=1)])
        for i, v in enumerate(vals):
            n = len(str(v)) if v is not None else 0
            if n > widths[i]:
                widths[i] = n
    sw.row([(1, title, st.xf(spec["title"][0][2]))])
    if summary:
        put(["Summary", "Original", "Updated", "Change"], head)
        for row in summary:
            put(list(row))
        sw.row([])
    if flag_miles:
        flagged = [d for d in diffs if d.flag]
        xf_flag = st.xf(nowrap(body), fill=HIGHLIGHT["flagged"])
        put([f"Mileage increases over {flag_miles:g} miles: {len(flagged)}", "Row", "Column", "Old", "New",
             "Change"], head)
        if not flagged:
            put(["None"])
        for d in flagged:
            put([d.tab, d.key, d.column, d.old, d.new, d.change], xf_flag)
        sw.row([])
    if diffs:
        counts: Dict[str, int] = defaultdict(int)
        for d in diffs:
            counts[d.tab] += 1
        put(["Tab", "Differences"], head)
        for tab_name, n in counts.items():
            put([tab_name, n])
        sw.row([])
    put(["Tab", "Row", "Column", "Old", "New", "Change"], head)
    if not diffs:
        put(["No differences found."])
    for d in diffs:
        put([d.tab, d.key, d.column, d.old, d.new, d.change])
    wb.add("Differences", sw, fit_columns([(1, 1, 30.0), (2, 2, 30.0), (3, 3, 24.0), (4, 6, 14.0)], widths,
                                          [font_size(body)] * 6), [])


def _only_changed(t: Table, marks, extra):
    """Rows with a difference (and total rows), with the highlight positions moved to match."""
    marked = {ri for ri, _ci in marks}
    keep = [i for i, r in enumerate(t.rows) if r.kind == "total" or i in marked]
    pos = {old: new for new, old in enumerate(keep)}
    base_old, base_new = len(t.rows), len(keep)
    new_marks = {}
    for (ri, ci), m in marks.items():
        if ri in pos:
            new_marks[(pos[ri], ci)] = m
        elif ri >= base_old:                        # removed rows appended at the bottom
            new_marks[(ri - base_old + base_new, ci)] = m
    return Table(t.name, [t.rows[i] for i in keep], t.key_cols, t.side, t.has_day), new_marks, extra


def write_comparison(sink, entries, title: str, opts: CompareOptions, summary=None,
                     extra_diffs: Sequence[Diff] = ()) -> int:
    """entries: [(sheet name, title, new Table, old Table or None)]. Writes the Differences tab
    and each tab with its differences highlighted; returns the number of differences."""
    diffs: List[Diff] = []
    prepared: List[tuple] = []
    for sheet, title_text, t_new, t_old in entries:
        if t_new.name == "Glossary":
            prepared.append((sheet, title_text, t_new, None, (), True))
            continue
        if t_old is None:                           # tab / day only in the updated pack
            marks = {(i, -1): "added" for i in range(len(t_new.rows))}
            extra: List[Row] = []
            found = [Diff(sheet, "", "(tab)", "", "only in the updated pack", "")]
        else:
            marks, extra, found = diff_table(t_old, t_new, headers_of(t_new), opts.flag_miles)
            for x in found:
                x.tab = sheet
        diffs += found
        prepared.append((sheet, title_text, t_new, marks, extra, bool(found)))
    diffs += list(extra_diffs)
    sink.differences(diffs, title, summary if opts.summary else None, opts.flag_miles)
    for sheet, title_text, t, marks, extra, changed in prepared:
        if opts.changed_tabs_only and not changed:
            continue
        if opts.changed_rows_only and marks:
            t, marks, extra = _only_changed(t, marks, extra)
        sink.table(sheet, title_text, t, marks, extra)
    return len(diffs)


# --------------------------------------------------------------------------- #
# reading stats packs back from Excel
# --------------------------------------------------------------------------- #
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REF = re.compile(r"([A-Z]+)(\d+)$")
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class PackReadError(Exception):
    pass


def _col(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + ord(ch.upper()) - 64
        else:
            break
    return n


def read_pack(path: str) -> List[Tuple[str, Table]]:
    """[(sheet name, Table)] for every recognised stats pack tab in a workbook."""
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackReadError(f"'{os.path.basename(path)}' is not a readable Excel stats pack: {exc}")
    with z:                             # closed straight away, so the pack is never left locked
        return _read_pack(z, path)


def _read_pack(z: zipfile.ZipFile, path: str) -> List[Tuple[str, Table]]:
    try:
        from rstools.fsutil import check_zip
        check_zip(z)
        wb = safexml.fromstring(z.read("xl/workbook.xml"), "xl/workbook.xml")
        rels = safexml.fromstring(z.read("xl/_rels/workbook.xml.rels"), "workbook.xml.rels")
    except (zipfile.BadZipFile, KeyError, OSError, ET.ParseError) as exc:
        raise PackReadError(f"'{os.path.basename(path)}' is not a readable Excel stats pack: {exc}")
    targets = {r.get("Id"): r.get("Target") for r in rels}
    sst = []
    if "xl/sharedStrings.xml" in z.namelist():
        try:
            for si in safexml.fromstring(z.read("xl/sharedStrings.xml"), "sharedStrings.xml").iter(NS + "si"):
                sst.append("".join(t.text or "" for t in si.iter(NS + "t")))
        except (zipfile.BadZipFile, OSError, ET.ParseError) as exc:
            raise PackReadError(f"'{os.path.basename(path)}' looks damaged (its text table could not be read: "
                                f"{exc}). Open it in Excel, save it and try again.")
    out: List[Tuple[str, Table]] = []
    for sh in wb.iter(NS + "sheet"):
        name = sh.get("name") or ""
        base = _base_name(name)
        if base is None or base == "Glossary":
            continue
        target = (targets.get(sh.get(RNS)) or "").lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        try:
            rows = _sheet_cells(z.read(target), sst)
        except (KeyError, ET.ParseError, ValueError, IndexError) as exc:
            raise PackReadError(f"Tab '{name}' could not be read: {exc}")
        out.append((name, _to_table(base, rows)))
    if not out:
        raise PackReadError(f"No stats pack tabs were found in '{os.path.basename(path)}'.")
    return out


_CELL = re.compile(rb'<c\s([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_ATTR = re.compile(rb'(\w+)="([^"]*)"')
_V = re.compile(rb'<v>([^<]*)</v>')
_T = re.compile(rb'<t[^>]*>([^<]*)</t>')
_COLS: Dict[object, int] = {}
_FAST_CELL = re.compile(rb'<c r="([A-Z]+)(\d+)"(?: s="\d+")?(?: t="(\w*)")?(?:/>|><v>([^<]*)</v></c>)')


def _number(text: str):
    f = float(text)
    return int(f) if f.is_integer() and "." not in text and "E" not in text.upper() else f


def _sheet_cells(data: bytes, sst: List[str]) -> Dict[int, Dict[int, object]]:
    """{row: {column: value}} for one worksheet.  A regular-expression scan is several times
    faster than building the element tree for these large, flat sheets."""
    if b"<c " not in data and b"<c\n" not in data:
        return _sheet_cells_et(data, sst)     # prefixed namespaces etc.
    val: object
    fast = _FAST_CELL.findall(data)
    if len(fast) == data.count(b"<c "):        # every cell in the simple form this app writes
        rows: Dict[int, Dict[int, object]] = {}
        for letters, r, t, v in fast:
            col = _COLS.get(letters)
            if col is None:
                col = _COLS[letters] = _col(letters.decode())
            if not v:
                val = None
            elif t == b"s":
                val = sst[int(v)]
            elif t == b"":
                val = int(v) if v.isdigit() else _number(v.decode())
            elif t == b"b":
                val = v == b"1"
            else:
                val = html.unescape(v.decode("utf-8"))
            row = rows.get(int(r))
            if row is None:
                row = rows[int(r)] = {}
            row[col] = val
        return rows
    rows = {}
    for m in _CELL.finditer(data):
        attrs = dict(_ATTR.findall(m.group(1)))
        ref = _REF.match(attrs.get(b"r", b"").decode())
        if not ref:
            continue
        letters, r = ref.group(1), int(ref.group(2))
        col = _COLS.get(letters)
        if col is None:
            col = _COLS[letters] = _col(letters)
        body, t = m.group(2) or b"", attrs.get(b"t")
        if t == b"inlineStr":
            val = html.unescape(b"".join(_T.findall(body)).decode("utf-8"))
        else:
            v = _V.search(body)
            raw = v.group(1).decode("utf-8") if v else None
            val = raw
            if raw is not None:
                if t == b"s":
                    val = sst[int(raw)]
                elif t in (None, b"n"):
                    f = float(raw)
                    val = int(f) if f.is_integer() and "." not in raw and "E" not in raw.upper() else f
                elif t == b"b":
                    val = raw == "1"
                else:
                    val = html.unescape(raw)
        rows.setdefault(r, {})[col] = val
    return rows


def _sheet_cells_et(data: bytes, sst: List[str]) -> Dict[int, Dict[int, object]]:
    rows: Dict[int, Dict[int, object]] = {}
    for c in safexml.fromstring(data, "sheet").iter(NS + "c"):
        ref = _REF.match(c.get("r", ""))
        if not ref:
            continue
        t, v = c.get("t"), c.find(NS + "v")
        text = v.text if v is not None else None
        val: object = text
        if t == "s" and text is not None:
            val = sst[int(text)]
        elif t == "inlineStr":
            val = "".join(x.text or "" for x in c.iter(NS + "t"))
        elif t in (None, "n") and text is not None:
            f = float(text)
            val = int(f) if f.is_integer() and "." not in text else f
        rows.setdefault(int(ref.group(2)), {})[_col(ref.group(1))] = val
    return rows


def _base_name(sheet: str) -> Optional[str]:
    if sheet in LAYOUT:
        return sheet
    for name in TAB_ORDER:
        for code in ("MO", "TO", "WO", "ThO", "FO", "SO", "Su"):
            if sheet == f"{code} {name}"[:31]:
                return name
    return None


def _to_table(name: str, rows: Dict[int, Dict[int, object]]) -> Table:
    spec = LAYOUT[name]
    first_body = 2 + len(spec["header"])
    has_day = rows.get(first_body - 1, {}).get(1) == "Day"
    width = max((max(r) for r in rows.values() if r), default=1)
    if name == "Service Miles":
        width = min(width, 9 + (1 if has_day else 0))
    out = []
    for r in sorted(rows):
        if r < first_body:
            continue
        cells = [rows[r].get(c) for c in range(1, width + 1)]
        while len(cells) > 1 and cells[-1] is None:
            cells.pop()
        first = next((x for x in cells if x not in (None, "")), "")
        kind = "total" if isinstance(first, str) and first.startswith("Total") else "body"
        out.append(Row(cells, kind))
    side = None
    if name == "Service Miles":
        c0 = 11 + (1 if has_day else 0)
        vals = rows.get(first_body, {})
        if vals.get(c0) is not None:
            side = [vals.get(c0), vals.get(c0 + 1)]
    return Table(name, out, key_cols=KEYS.get(name, 1) + (1 if has_day else 0), side=side, has_day=has_day)


def _read_both(old_path: str, new_path: str):
    """Read two packs at once: the original in a second process (a second CPU core) while the
    updated one is read here. Falls back to reading them one after the other."""
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    if (os.cpu_count() or 1) < 2:
        return read_pack(old_path), read_pack(new_path)
    try:
        pool = ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"))
        pending = pool.submit(read_pack, old_path)
    except Exception:
        return read_pack(old_path), read_pack(new_path)
    try:
        new = read_pack(new_path)
        try:
            old = pending.result()
        except PackReadError:
            raise
        except Exception:                      # the helper process failed - read it here instead
            old = read_pack(old_path)
        return old, new
    finally:
        pool.shutdown(cancel_futures=True)


def compare_pack_files(old_path: str, new_path: str, out_path: str,
                       opts: Optional[CompareOptions] = None) -> int:
    opts = opts or CompareOptions()
    old_list, new = _read_both(old_path, new_path)
    old = dict(old_list)
    new_names = {s for s, _t in new}
    gone = [Diff(sheet, "", "(tab)", "only in the original pack", "", "") for sheet in old if sheet not in new_names]
    from .output import sink_for
    sink = sink_for(os.path.splitext(out_path)[1].lstrip(".").lower())
    n = write_comparison(sink, [(sheet, sheet, t, old.get(sheet)) for sheet, t in new],
                         "Differences between stats packs", opts,
                         summary_rows({k: v for k, v in old.items()}, dict(new)), gone)
    sink.save(out_path, os.path.splitext(os.path.basename(out_path))[0])
    return n
