"""What changed between two versions of a berthing chart, berth by berth and column by column; and carrying an
earlier issue's highlight colours on to cells that have not changed.

Cells are compared as units and times, not as typed text: spacing slips ('(4 387) 00 45'), the old 'L' count
marker and '12700' / '12 700' do not count as changes."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .layout import DAY_COLUMNS, Cell, DepotSheet, GridSheet, Layout
from .mapping import norm

Key = Tuple[str, str, int]              # (sheet, berth, day column)


def canonical(text: str) -> str:
    t = " ".join((text or "").split())
    t = re.sub(r"^L\s*(?=[(\d])", "", t)                         # the old counting marker
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = re.sub(r"^(\(?)(\d{1,2})(\d{3})\b", r"\1\2 \3", t)        # '12700' -> '12 700'
    t = re.sub(r"(\d{2})\s*\+\s*(\d{2})", r"\1+\2", t)            # '06 +10' -> '06+10'
    t = re.sub(r"(?<=\s)(\d{2}) (\d{2})\b", r"\1\2", t)          # '00 45' -> '0045'
    t = re.sub(r"(RP)\s+", r"\1", t, flags=re.I)
    t = re.sub(r"\s*TLK$", " TLK", t)
    t = re.sub(r"\bberth\b", "Berth", t, flags=re.I)
    return t.strip()


def cells(layout: Layout) -> Dict[Key, List[Tuple[int, Cell]]]:
    """Every unit cell of a chart's location sheets: (sheet, berth, column) -> [(row, cell)] in row order."""
    out: Dict[Key, List[Tuple[int, Cell]]] = defaultdict(list)
    for sheet in layout.sheets:
        if isinstance(sheet, DepotSheet):
            for dblk in sheet.blocks:
                for r, row in enumerate(dblk.cells):
                    for c, cell in enumerate(row):
                        if cell is not None and cell.text:
                            out[(norm(sheet.name), norm(dblk.title), c)].append((r, cell))
            continue
        for blk in sheet.blocks:
            for off in sorted(blk.units):
                for c, unit in enumerate(blk.units[off]):
                    if unit is not None and unit.text:
                        out[(norm(sheet.name), norm(blk.label), c)].append((off, unit))
    return out


@dataclass
class Change:
    sheet: str
    berth: str
    column: str
    kind: str                   # 'Changed', 'Added', 'Removed'
    old: str
    new: str
    section: str = ""           # the siding location, on a sheet that has several (else '')
    rank: int = 0               # that location's position on the sheet (chart order)


def diff(old: Layout, new: Layout) -> Tuple[List[Change], Dict[Key, set]]:
    """(changes, {key: rows of the new chart that changed}). A cell counts as changed when its unit and
    time are not in the same berth's same column in the old chart."""
    a, b = cells(old), cells(new)
    # a sheet renamed slightly between issues ('RDH Up Tonb Goods Loop' / 'RDH Up Tonb Sdg') is the same sheet
    old_sheets = {norm(sh.name) for sh in old.sheets}
    new_sheets = {norm(sh.name) for sh in new.sheets}
    rename = {}
    for n in new_sheets - old_sheets:
        match = [o for o in old_sheets - new_sheets if o.split()[:2] == n.split()[:2]]
        if len(match) == 1:
            rename[match[0]] = n
    if rename:
        a = {(rename.get(k[0], k[0]),) + k[1:]: v for k, v in a.items()}
        old_sheets = {rename.get(o, o) for o in old_sheets}
    names: Dict[object, str] = {}
    for lay in (old, new):
        for sheet in lay.sheets:
            names[norm(sheet.name)] = sheet.name
            for blk in sheet.blocks:
                names[(norm(sheet.name), norm(getattr(blk, "label", "") or getattr(blk, "title", "")))] = \
                    getattr(blk, "label", "") or getattr(blk, "title", "")
    # the siding location of each berth, on sheets that have several (the newer chart's wins; renamed sheets match)
    where: Dict[Tuple[str, str], Tuple[str, int]] = {}
    for lay in (old, new):
        for sheet in lay.sheets:
            if isinstance(sheet, GridSheet) and len(sheet.sections) > 1:
                sheet_key = norm(sheet.name)
                sheet_key = rename.get(sheet_key, sheet_key) if lay is old else sheet_key
                for blk in sheet.blocks:
                    name = sheet.sections[blk.section] if blk.section < len(sheet.sections) else ""
                    where[(sheet_key, norm(blk.label))] = (name, blk.section)
    changes: List[Change] = []
    marked: Dict[Key, set] = defaultdict(set)
    heads = {sheet.name: (DAY_COLUMNS if isinstance(sheet, GridSheet) else _depot_heads()) for lay in (old, new)
             for sheet in lay.sheets}
    for gone in sorted(old_sheets - new_sheets):
        changes.append(Change(names.get(gone, gone), "(whole sheet)", "", "Removed", "Sheet not in the newer chart",
                              ""))
    for fresh in sorted(new_sheets - old_sheets):
        changes.append(Change(names.get(fresh, fresh), "(whole sheet)", "", "Added", "", "Sheet new in this chart"))
    for key in sorted(set(a) | set(b), key=lambda k: (k[0], k[1], k[2])):
        sheet_key, berth_key, col = key
        if sheet_key not in old_sheets or sheet_key not in new_sheets:
            if sheet_key in new_sheets:
                marked[key] |= {r for r, _c in b.get(key, [])}     # a new sheet: all of it is new
            continue
        olds = [canonical(c.text) for _r, c in a.get(key, [])]
        news = b.get(key, [])
        left = Counter(olds)
        added: List[Tuple[int, Cell]] = []
        for r, c in news:
            t = canonical(c.text)
            if left[t] > 0:
                left[t] -= 1
            else:
                added.append((r, c))
        removed = []
        for t in olds:                          # old cells not found in the new chart
            if left[t] > 0:
                removed.append(t)
                left[t] -= 1
        sheet_name = names.get(sheet_key, sheet_key)
        head = heads.get(sheet_name, DAY_COLUMNS)
        column = head[col] if col < len(head) else str(col + 1)
        berth = names.get((sheet_key, berth_key), berth_key)
        place, rank = where.get((sheet_key, berth_key), ("", 0))
        for i, (r, c) in enumerate(added):
            marked[key].add(r)
            if i < len(removed):
                changes.append(Change(sheet_name, berth, column, "Changed", removed[i], c.text, place, rank))
            else:
                changes.append(Change(sheet_name, berth, column, "Added", "", c.text, place, rank))
        for t in removed[len(added):]:
            changes.append(Change(sheet_name, berth, column, "Removed", t, "", place, rank))
    return changes, marked


def _depot_heads() -> List[str]:
    from .layout import NIGHTS
    days = ["MON", "TUE", "WED", "THUR", "FRI", "SAT", "SUN"]
    out = []
    for n in NIGHTS:
        out += [f"{days[n]} FINISH", f"{days[(n + 1) % 7]} START"]
    return out


def highlight(layout: Layout, marked: Dict[Key, set], colour: str):
    """Fill the changed cells of a chart with this round's colour."""
    for sheet in layout.sheets:
        if isinstance(sheet, DepotSheet):
            for dblk in sheet.blocks:
                for r, row in enumerate(dblk.cells):
                    for c, cell in enumerate(row):
                        if cell is not None and r in marked.get((norm(sheet.name), norm(dblk.title), c), ()):
                            cell.fill = colour
            continue
        for blk in sheet.blocks:
            for off, units in blk.units.items():
                for c, unit in enumerate(units):
                    if unit is not None and off in marked.get((norm(sheet.name), norm(blk.label), c), ()):
                        unit.fill = colour


def carry_colours(earlier: Layout, layout: Layout, skip: Iterable[str] = ()):
    """Earlier rounds' fills put back on the same unit and time in the same berth and column (a cell this
    round changes gets the new colour instead). Fills in `skip` (e.g. the STP fill) are not carried."""
    skip = {s.upper() for s in skip}
    old: Dict[Tuple[str, str, int, str], List[str]] = defaultdict(list)
    for key, items in cells(earlier).items():
        for _r, c in items:
            if c.fill and c.fill.upper() not in skip:
                old[key + (canonical(c.text),)].append(c.fill)
    for key, items in cells(layout).items():
        for _r, c in items:
            fills = old.get(key + (canonical(c.text),))
            if fills and not c.fill:
                c.fill = fills.pop(0)


def write_report(path: str, changes: List[Change], title: str, about: List[Tuple[str, str]]):
    """The change report: a summary, then every change by sheet, berth and column."""
    from rstools.timetable.xlstyle import add_sheet, new_workbook, save
    wb = new_workbook()
    counts = Counter(c.kind for c in changes)
    add_sheet(wb, "Summary", ["Item", "Detail"], about + [["Changed cells", counts.get("Changed", 0)],
                                                         ["Added", counts.get("Added", 0)],
                                                         ["Removed", counts.get("Removed", 0)]], [26, 90])
    fills = {i: ("review" if c.kind == "Changed" else "ok" if c.kind == "Added" else "bad")
             for i, c in enumerate(changes)}
    add_sheet(wb, "Changes", ["Sheet", "Berth", "Column", "Change", "Was", "Now"],
              [[c.sheet, c.berth, c.column, c.kind, c.old, c.new] for c in changes], [22, 22, 14, 11, 26, 26],
              fills=fills)
    save(wb, path, title)


def colour_name(hex_colour: str) -> Optional[str]:
    from cwn_compare.options import PRESET_COLOURS
    return next((n for n, v in PRESET_COLOURS.items() if v.upper() == hex_colour.upper()[-6:]), None)
