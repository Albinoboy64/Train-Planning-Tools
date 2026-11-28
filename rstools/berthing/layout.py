"""Reading a berthing chart: its cover, and for each location sheet the berths (label, capacity, notes) and the
units in each night's finish / start columns. Used for the layout of a new chart and to compare two charts.

What the old charts carry but no longer need is left behind: the counting sections ('Start1' ... 'Finish1',
'*4 377*' rows and their COUNTIF formulas), stray columns beyond the 16 days and broken formatting."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from .mapping import Locations, norm
from .xmlread import BerthingError

DAY_COLUMNS = ["FRI FINISH", "SAT START", "SAT FINISH", "SUN START", "SUN FINISH", "MON START", "MON FINISH",
               "TUE START", "TUE FINISH", "WED START", "WED FINISH", "THUR START", "THUR FINISH", "FRI START",
               "FRI FINISH", "SAT START"]
DEPOT_DAYS = ["PREV FRI", "SATURDAY", "SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "NEXT SAT"]
# the night each pair of columns shows (finish day, 0 = Monday): Fri, Sat, Sun, Mon, Tue, Wed, Thu, Fri
NIGHTS = [4, 5, 6, 0, 1, 2, 3, 4]

# '4 387', '(4 377)', '12700', and another operator's train shown by its headcode ('2T80 23+50')
_UNIT = re.compile(r"^\s*L?\s*\(?\s*(?:\d{1,2}\s*\d{3}(?:/\d)?|MAINT|\d[A-Z]\d{2}(?=\s))\b", re.I)
_COUNT_ROW = re.compile(r"^\*.*\*$")
_MARKER = re.compile(r"^(start|finish)\s*\d*$", re.I)
COUNTS_HEAD = "Unit counts"             # the heading of a siding location's counts in a chart made by the app
SECTION_HEAD = "Location"               # the banner row above each siding location (sheets with several)
COUNTS_END = "Cars"                     # ... and its last row
SECTION_LINE = "1F4E79"                 # the line under the last berth of a siding location (app-made charts)
_DEPOT_TITLE = re.compile(r"^\s*\d{1,2}\s+\d{3}(?:/\d)?\s*$")


@dataclass
class Cell:
    text: str
    colour: str = ""            # font colour, 'RRGGBB' ('' = automatic / black)
    bold: bool = False
    fill: str = ""              # fill colour 'RRGGBB' ('' = none)
    italic: bool = False


@dataclass
class Block:
    """A berth: its label row and the rows under it, up to the next berth."""
    label: str
    capacity: str = ""
    height: int = 1
    units: Dict[int, List[Optional[Cell]]] = field(default_factory=dict)    # row offset -> 16 cells
    notes: Dict[int, Tuple[str, str]] = field(default_factory=dict)         # row offset -> (column A, column B)
    data_notes: Dict[Tuple[int, int], str] = field(default_factory=dict)    # (offset, day column) -> text
    section: int = 0                    # which siding location on the sheet (index into GridSheet.sections)
    codes: str = ""                     # platform / road codes ('3;3F'), for a berth of a saved location set
    tiploc: str = ""                    # its TIPLOC, for a berth of a sheet made from an XML (else the sheet's)


@dataclass
class GridSheet:
    name: str
    hidden: bool = False
    tab: str = ""
    corner: Tuple[str, str] = ("Siding", "")         # the header's columns A and B ('Siding', 'Capacity')
    preface: List[Tuple[str, str]] = field(default_factory=list)       # rows above the header
    lead: List[Tuple[str, str]] = field(default_factory=list)          # note rows before the first berth
    blocks: List[Block] = field(default_factory=list)
    widths: Dict[int, float] = field(default_factory=dict)             # column number (1 = A) -> width
    kind: str = "grid"
    sections: List[str] = field(default_factory=list)  # siding locations on the sheet, in order (their names)


@dataclass
class DepotBlock:
    title: str                                      # unit type, e.g. '4 377', '4 387/2'
    rows: int = 0
    cells: List[List[Optional[Cell]]] = field(default_factory=list)     # rows of 16 (finish / start columns)


@dataclass
class DepotSheet:
    name: str
    hidden: bool = False
    tab: str = ""
    blocks: List[DepotBlock] = field(default_factory=list)
    widths: Dict[int, float] = field(default_factory=dict)
    kind: str = "depot"


Sheet = Union[GridSheet, DepotSheet]


@dataclass
class CoverRow:
    cells: Dict[int, Tuple[str, float, bool, str]]   # column -> (text, font size, bold, colour)
    merged: bool = False                             # one line across the page (titles)


@dataclass
class Layout:
    path: str
    cover_name: str = "Cover"
    cover: List[CoverRow] = field(default_factory=list)
    sheets: List[Sheet] = field(default_factory=list)


def _text(v) -> str:
    """A cell's text, without characters an Excel file cannot hold (it is written into the chart again)."""
    from rstools.fsutil import clean_cell
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return clean_cell(" ".join(str(v).split()) if not isinstance(v, str) else v.strip())


def _rgb(color) -> str:
    try:
        if color is not None and color.type == "rgb" and isinstance(color.rgb, str):
            return color.rgb[-6:].upper()
    except AttributeError:
        pass
    return ""


def _cell(c) -> Cell:
    fill = _rgb(c.fill.fgColor) if c.fill is not None and c.fill.fill_type == "solid" else ""
    colour = _rgb(c.font.color) if c.font is not None else ""
    return Cell(_text(c.value), "" if colour == "000000" else colour, bool(c.font.b), "" if fill == "FFFFFF" else fill,
                bool(c.font.i))


def is_unit(text: str) -> bool:
    return bool(_UNIT.match(text or "")) or text.strip().upper() in ("TLK", "SPARE")


def read_chart(path: str, locations: Optional[Locations] = None) -> Layout:
    """Read a berthing chart (.xlsx). Raises BerthingError with a plain message if it cannot be used."""
    import openpyxl
    from rstools.fsutil import check_office_file, long_path
    name = os.path.basename(path)
    try:
        check_office_file(long_path(path))
        wb = openpyxl.load_workbook(long_path(path))
    except PermissionError:
        raise BerthingError(f"'{name}' could not be opened - it may be open in Excel. Close it and try again.")
    except Exception as exc:
        raise BerthingError(f"'{name}' could not be read as an Excel workbook ({exc}).")
    try:
        out = Layout(path)
        for ws in wb.worksheets:
            sheet = _read_sheet(ws, locations)
            if sheet is not None:
                out.sheets.append(sheet)
            elif not out.cover and not out.sheets:
                out.cover_name, out.cover = ws.title.strip() or "Cover", _read_cover(ws)
    finally:
        wb.close()
    if not out.sheets:
        raise BerthingError(f"No berthing chart sheets were found in '{name}' (sheets with FRI FINISH / SAT START "
                            "headings).")
    return out


def _read_cover(ws) -> List[CoverRow]:
    merged = {r.min_row for r in ws.merged_cells.ranges if r.max_col - r.min_col >= 3}
    rows: List[CoverRow] = []
    last = 0
    for r in range(1, min(ws.max_row, 80) + 1):
        cells = {}
        for c in range(1, min(ws.max_column, 15) + 1):
            cell = ws.cell(r, c)
            t = _text(cell.value)
            if t and not t.startswith("="):
                cells[c] = (t, float(cell.font.sz or 10), bool(cell.font.b), _rgb(cell.font.color))
        rows.append(CoverRow(cells, r in merged))
        if cells:
            last = r
    return rows[:last]


def _header(ws) -> Optional[Tuple[int, int, str]]:
    """(header row, first day column, kind) of a location sheet, or None for any other sheet."""
    for r in range(1, min(ws.max_row, 10) + 1):
        for c in range(1, min(ws.max_column, 8) + 1):
            t = _text(ws.cell(r, c).value).upper()
            if t == "FRI FINISH":
                return r, c, "grid"
            if t == "FINISH" and _text(ws.cell(r, c + 1).value).upper() == "START":
                return r, c, "depot"
    return None


def _widths(ws) -> Dict[int, float]:
    from openpyxl.utils import column_index_from_string
    out = {}
    for letter, dim in ws.column_dimensions.items():
        try:
            if dim.width:
                out[column_index_from_string(letter)] = float(dim.width)
        except ValueError:
            continue
    return out


def _tab(ws) -> str:
    return _rgb(ws.sheet_properties.tabColor) if ws.sheet_properties.tabColor is not None else ""


def _read_sheet(ws, locations: Optional[Locations]) -> Optional[Sheet]:
    found = _header(ws)
    if found is None:
        return None
    hdr, col0, kind = found
    if kind == "depot":
        return _read_depot(ws, col0)
    sheet = GridSheet(ws.title.strip(), ws.sheet_state != "visible", _tab(ws),
                      (_text(ws.cell(hdr, 1).value) or "Siding", _text(ws.cell(hdr, 2).value) if col0 > 2 else ""),
                      widths=_widths(ws))
    sheet.preface = [(_text(ws.cell(r, 1).value), _text(ws.cell(r, 2).value)) for r in range(1, hdr)
                     if _text(ws.cell(r, 1).value) or _text(ws.cell(r, 2).value)]
    known = locations.sheet(sheet.name) if locations is not None else {}
    cur: Optional[Block] = None
    offset = 0
    counting = False
    ended = False                   # the current siding location has ended (its counts or its line were passed)
    names: Dict[int, str] = {}      # section -> its name, where the chart gives one ('Start2  Brighton Wall Siding')
    heads: Dict[int, str] = {}      # section -> the name on its 'Location – <name>' banner (a chart made by the app)
    section = 0

    def end_section(name: str = ""):
        nonlocal ended
        if sheet.blocks and not ended:
            ended = True
        if name and sheet.blocks:
            names.setdefault(section, name)
    for r in range(hdr + 1, ws.max_row + 1):
        a, b = _text(ws.cell(r, 1).value), _text(ws.cell(r, 2).value) if col0 > 2 else ""
        data = [ws.cell(r, col0 + i) for i in range(16)]
        if a.startswith(SECTION_HEAD + " \u2013 ") and not any(_text(c.value) for c in data):
            # the banner above a siding location: it names the next berths' location and is not a berth or a note
            if sheet.blocks:
                ended = True
            heads[section + 1 if sheet.blocks else 0] = a[len(SECTION_HEAD) + 3:].strip()
            continue
        if _MARKER.match(a):
            counting = a.lower().startswith("start")        # 'Start1' ... 'Finish1': the old counts
            end_section(b if counting else "")
            continue
        if a.startswith(COUNTS_HEAD):                       # a chart made by the app: 'Unit counts – <name>'
            counting = True
            end_section(a[len(COUNTS_HEAD):].strip(" -–:"))
            continue
        if counting and a == COUNTS_END:
            counting = False
            continue
        formulas = any(isinstance(c.value, str) and c.value.startswith("=") for c in data)
        if counting or _COUNT_ROW.match(a) or formulas:
            end_section()
            continue
        if a and _is_label(a, b, known):
            if ended:
                section, ended = section + 1, False
            cur = Block(a, b if _capacity(b) else "", section=section)
            if b and not _capacity(b):
                cur.notes[0] = ("", b)
            sheet.blocks.append(cur)
            offset = 0
        elif cur is not None:
            offset += 1
            cur.height = offset + 1
            if a or b:
                cur.notes[offset] = (a, b)
        elif a or b:
            sheet.lead.append((a, b))
        if cur is None:
            continue
        row: List[Optional[Cell]] = []
        for i, c in enumerate(data):
            t = _text(c.value)
            if not t:
                row.append(None)
            elif is_unit(t):
                row.append(_cell(c))
            else:
                cur.data_notes[(offset, i)] = t
                row.append(None)
        if any(row):
            cur.units[offset] = row
            cur.height = max(cur.height, offset + 1)
        if _section_line(ws.cell(r, 1)):
            end_section()
    _join_labels(sheet, known)
    sheet.sections = _section_names(sheet, {**names, **heads}, section + 1) if sheet.blocks else []
    for blk in sheet.blocks:                     # trailing empty rows at the end of the sheet are not kept
        used = [o for o in blk.units] + [o for o in blk.notes] + [o for o, _c in blk.data_notes]
        blk.height = max([blk.height if blk is not sheet.blocks[-1] else 1] + [o + 1 for o in used])
    return sheet


_NOTE_WORDS = re.compile(r"^(no attatch|no attach|/detach|allowed|permissive|no permissive|le|ce|cet|max \d+ cet|"
                         r"country end|london end|stp check|attach/detach|with \w+|hand bash|note\b.*|\d+ \d{3} from|"
                         r"no det .*|dn sdg nth|12 car only.*|access .*)$", re.I)
_LABEL_WORDS = re.compile(r"^(plat(form)?\s*\d|p\d|\d{1,2}$|\d{1,2}\s+(up\s+)?(sdg|siding|shed)|no\s*\d+\s|sdg\s*\d|"
                          r"siding|shed\s*\d|down\s|up\s|dn\s|back road|middle r|loop$)", re.I)


def _section_line(cell) -> bool:
    """The line a chart made by the app draws under the last berth of a siding location."""
    side = cell.border.bottom if cell.border is not None else None
    return bool(side is not None and side.style in ("medium", "thick") and _rgb(side.color) == SECTION_LINE)


def _section_names(sheet: GridSheet, given: Dict[int, str], n: int) -> List[str]:
    """A name for each siding location: the chart's own ('Brighton Wall Siding') where it tells them apart, else
    one made from its berths ('Platforms', 'Tilgate', 'Sdg 1 to Sdg 3', or the berth's label)."""
    from collections import Counter
    uses = Counter(norm(v) for v in given.values())
    out = []
    for i in range(n):
        name = given.get(i, "")
        if name and uses[norm(name)] == 1 and (n == 1 or norm(name) != norm(sheet.name)):
            out.append(name)
            continue
        labels = [b.label for b in sheet.blocks if b.section == i]
        out.append(name or sheet.name if n == 1 else _name_from(labels))
    return out


def _name_from(labels: List[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    words = [lab.split() for lab in labels]
    common: List[str] = []
    for column in zip(*words):
        if len({w.casefold() for w in column}) != 1:
            break
        common.append(column[0])
    while common and common[-1].casefold() in ("no", "no.", "-"):
        common.pop()
    head = " ".join(common)
    if head.casefold() in ("plat", "platform", "p"):
        return "Platforms"
    if not head or head.casefold() in ("sdg", "siding", "shed", "road", "down", "up"):
        return f"{labels[0]} to {labels[-1]}"
    return head


def _join_labels(sheet: GridSheet, known: dict):
    """Berths written on two lines with the same first line ('Battersea' / 'Pier No 1', 'Battersea' / 'Pier No 2')
    take both lines as their label, so they can be told apart."""
    seen: Dict[str, int] = {}
    for blk in sheet.blocks:
        seen[norm(blk.label)] = seen.get(norm(blk.label), 0) + 1
    for blk in sheet.blocks:
        second = blk.notes.get(1, ("", ""))[0]
        joined = f"{blk.label} {second}"
        if seen[norm(blk.label)] > 1 and second and (not known or norm(joined) in known):
            blk.label = joined
            del blk.notes[1]


def _capacity(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}(\s*(gx|\(\d+\)|/\d+))?", text.strip(), re.I))


def _is_label(a: str, b: str, known: dict) -> bool:
    """Whether column A starts a berth: a label in the berth list for this sheet, or (for a sheet not in the
    list) one that reads like a berth and not like a note."""
    if known:
        return norm(a) in known
    if _NOTE_WORDS.match(a):
        return False
    return bool(_LABEL_WORDS.match(a)) and (not b or _capacity(b))


def _read_depot(ws, col0: int) -> DepotSheet:
    sheet = DepotSheet(ws.title.strip(), ws.sheet_state != "visible", _tab(ws), widths=_widths(ws))
    cur: Optional[DepotBlock] = None
    for r in range(1, ws.max_row + 1):
        a = _text(ws.cell(r, col0).value)
        if _DEPOT_TITLE.match(a) and not _text(ws.cell(r, col0 + 1).value):
            cur = DepotBlock(" ".join(a.split()))
            sheet.blocks.append(cur)
            continue
        if cur is None:
            continue
        vals = [ws.cell(r, col0 + i) for i in range(16)]
        heads = {_text(c.value).upper() for c in vals}
        if heads & {"FINISH", "START"} or heads & set(DEPOT_DAYS):
            continue                                # the block's day headings
        if any(isinstance(c.value, str) and c.value.startswith("=") for c in vals):
            continue                                # old COUNTA totals
        cur.rows += 1
        cur.cells.append([_cell(c) if _text(c.value) else None for c in vals])
    for blk in sheet.blocks:                        # trailing empty rows are capacity, kept as the block height
        while blk.cells and not any(blk.cells[-1]):
            blk.cells.pop()
    return sheet


# --------------------------------------------------------------------------- the app's built-in layout
DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_layout.json.gz")
_default_cache: Dict[str, object] = {}


def to_dict(layout: Layout) -> dict:
    """A layout as plain data, without any units (only the berths, their notes and the cover)."""
    sheets = []
    for sh in layout.sheets:
        if isinstance(sh, DepotSheet):
            sheets.append({"kind": "depot", "name": sh.name, "hidden": sh.hidden, "tab": sh.tab,
                           "widths": sh.widths, "blocks": [{"title": b.title, "rows": max(b.rows, len(b.cells))}
                                                           for b in sh.blocks]})
            continue
        sheets.append({"kind": "grid", "name": sh.name, "hidden": sh.hidden, "tab": sh.tab, "corner": list(sh.corner),
                       "preface": [list(x) for x in sh.preface], "lead": [list(x) for x in sh.lead],
                       "widths": sh.widths, "sections": sh.sections,
                       "blocks": [{"label": b.label, "capacity": b.capacity, "height": b.height, "section": b.section,
                                   "notes": {str(k): list(v) for k, v in b.notes.items()},
                                   "data_notes": {f"{o},{i}": t for (o, i), t in b.data_notes.items()},
                                   **({"codes": b.codes} if b.codes else {}),
                                   **({"tiploc": b.tiploc} if b.tiploc else {})}
                                  for b in sh.blocks]})
    return {"cover_name": layout.cover_name,
            "cover": [{"cells": {str(c): list(v) for c, v in row.cells.items()}, "merged": row.merged}
                      for row in layout.cover],
            "sheets": sheets}


def from_dict(data: dict, path: str = "") -> Layout:
    out = Layout(path, data.get("cover_name", "Cover"),
                 [CoverRow({int(c): (v[0], float(v[1]), bool(v[2]), v[3]) for c, v in row["cells"].items()},
                           bool(row.get("merged"))) for row in data.get("cover", [])])
    for sh in data.get("sheets", []):
        widths = {int(k): float(v) for k, v in (sh.get("widths") or {}).items()}
        if sh.get("kind") == "depot":
            out.sheets.append(DepotSheet(sh["name"], sh.get("hidden", False), sh.get("tab", ""),
                                         [DepotBlock(b["title"], int(b.get("rows", 0))) for b in sh["blocks"]],
                                         widths))
            continue
        blocks = []
        for b in sh["blocks"]:
            notes = {int(k): (v[0], v[1]) for k, v in (b.get("notes") or {}).items()}
            data_notes = {(int(k.split(",")[0]), int(k.split(",")[1])): t
                          for k, t in (b.get("data_notes") or {}).items()}
            blocks.append(Block(b["label"], b.get("capacity", ""), int(b.get("height", 1)), {}, notes, data_notes,
                                int(b.get("section", 0)), str(b.get("codes", "") or ""),
                                str(b.get("tiploc", "") or "")))
        corner = list(sh.get("corner") or ["Siding", ""]) + [""]
        out.sheets.append(GridSheet(sh["name"], sh.get("hidden", False), sh.get("tab", ""), (corner[0], corner[1]),
                                    [(x[0], x[1]) for x in sh.get("preface", [])],
                                    [(x[0], x[1]) for x in sh.get("lead", [])],
                                    blocks, widths, sections=list(sh.get("sections") or [])))
    return out


def save_default(chart: str, out: str = DEFAULT_FILE) -> dict:
    """Make the app's built-in layout from a berthing chart (run when a new chart should become the default:
    python -m rstools.berthing.layout CHART.xlsx). Only the layout is kept - no trains."""
    import datetime
    import gzip
    import json
    from .mapping import load
    layout = read_chart(chart, load())
    data = to_dict(layout)
    data["source"] = os.path.basename(chart)
    data["made"] = datetime.date.today().isoformat()
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    _default_cache.clear()
    return {"source": data["source"], "sheets": len(layout.sheets),
            "berths": sum(len(s.blocks) for s in layout.sheets if isinstance(s, GridSheet))}


def default_info() -> Optional[dict]:
    """{'source', 'made', 'sheets'} of the built-in layout, or None if it is missing."""
    data = _load_default_data()
    if data is None:
        return None
    return {"source": data.get("source", ""), "made": data.get("made", ""), "sheets": len(data.get("sheets", []))}


def _load_default_data() -> Optional[dict]:
    if "data" not in _default_cache:
        import gzip
        import json
        try:
            with gzip.open(DEFAULT_FILE, "rt", encoding="utf-8") as fh:
                _default_cache["data"] = json.load(fh)
        except (OSError, ValueError, EOFError):
            _default_cache["data"] = None
    return _default_cache["data"]                          # type: ignore[return-value]


def load_default() -> Layout:
    """The app's built-in layout (a fresh copy). Raises BerthingError if it is missing from the app."""
    data = _load_default_data()
    if not data:
        raise BerthingError("The built-in berthing chart layout is missing from the app. Choose a chart to take the "
                            "layout from.")
    return from_dict(data, f"the built-in layout (from {data.get('source', 'the default chart')})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: python -m rstools.berthing.layout CHART.xlsx")
    print(save_default(sys.argv[1]))
