"""Put each train's day variants in day order in a multi-day CWN (a tidier copy; nothing is changed or lost).

A train that runs differently on different days has one entry (block) per variant, e.g. 1A23 (MO),
1A23 (TWThO), 1A23 (FO). CWNs list these in no fixed order. This writes a copy of the CWN in which,
on every location tab, each train's variants are ordered Monday first through to Friday (then
Saturday and Sunday) - or, if chosen, by departure time first and day second.

Only the variants of the same train swap places: they are put back into the positions those variants
already occupied, so every other train stays exactly where it was. Rows move whole - values, styles,
row heights and links - and links from other tabs are re-pointed to the rows' new positions.

Optionally, variants of a train that are the same on a tab apart from their days (e.g. 1A23 MO and 1A23 FO
with the same times, units and workings) are merged into one, whose DAYS cell lists both (MFO); when the
merged variant runs every day the CWN covers, its DAYS cell is left blank, as for any other train. The
rows of the variants merged away are removed and the rows below move up.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from copy import copy
from typing import Callable, Dict, List, Optional, Set, Tuple

from .days import coverage, code_days
from .model import Block, SheetModel, cell_text


class ReorderError(Exception):
    pass


def _days_of(b: Block, base) -> Set[int]:
    return code_days(b.days or b.variant, base) or set()


def _day_key(days: Set[int]) -> Tuple[int, ...]:
    """The days a variant runs, in order: the first day decides (MWO before ThFO, whatever their times). No
    days known: last."""
    return tuple(sorted(days)) if days else (99,)


def _order(blocks: List[Block], base, by_time: bool, days: Optional[Dict[str, Set[int]]] = None) -> List[Block]:
    days = days or {}

    def key(b: Block):
        t = b.sort_time if b.sort_time is not None else 9999
        d = _day_key(days.get(b.key, _days_of(b, base)))
        return (t, d) if by_time else (d, t)
    return sorted(blocks, key=key)


MAX_GAP = 240                   # minutes: variants of one train usually depart within a few hours of each other


def _gap(a: int, b: int) -> int:
    """Minutes between two times of day, across midnight too (23.50 and 00.10 are 20 minutes apart)."""
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def _trains(blocks: List[Block], base) -> List[List[Block]]:
    """Split the blocks sharing a headcode into trains. The variants of one train run on different
    days (MO, TWThO, FO); a second block running on a day already covered - e.g. the same ECS
    headcode used morning and evening - is another train. A block joins the nearest-in-time train it
    does not share a day with (one within a few hours if there is one), so variants that run at quite
    different times or either side of midnight are still put in order. Returned in sheet order."""
    clusters: List[Tuple[set, List[int], List[Block]]] = []
    for b in sorted(blocks, key=lambda b: (b.sort_time if b.sort_time is not None else 9999, b.start_row)):
        days = code_days(b.days or b.variant, base) or set(base) or set(range(7))
        t = b.sort_time

        def near(c, t=t) -> int:
            return min((_gap(t, x) for x in c[1]), default=0) if t is not None else 0
        free = [c for c in clusters if not (c[0] & days)]
        fits = [c for c in free if near(c) <= MAX_GAP] or free
        if fits:
            c = min(fits, key=near)
        else:
            c = (set(), [], [])
            clusters.append(c)
        c[0].update(days)
        if t is not None:
            c[1].append(t)
        c[2].append(b)
    return [sorted(c[2], key=lambda b: b.start_row) for c in clusters]


_DAY_TOKENS = ("M", "T", "W", "Th", "F", "S", "Su")


def days_code(days: Set[int], base: Set[int], sx_style: bool = False) -> str:
    """The DAYS code for `days` within the CWN's days `base`: '' for every day of the CWN, else the shorter
    of the 'only' form (MFO, ThFO) and the 'excepted' form (FX - or FSX in a weekday CWN written that way)."""
    days, base = set(days), set(base)
    if not days or days >= base:
        return ""
    only = "".join(_DAY_TOKENS[d] for d in sorted(days)) + "O"
    rest = base - days
    if len(days) <= len(rest):
        return only
    sat = sx_style and 5 not in base
    return "".join(_DAY_TOKENS[d] for d in sorted(rest | ({5} if sat else set()))) + "X"


def _signature(b: Block, days_col: int) -> tuple:
    """A block's contents apart from its DAYS cell: the same for variants that differ only in their days."""
    return tuple(tuple(cell_text(v) for c, v in enumerate(spec["v"], start=1) if c != days_col)
                 for spec in b.rows)


def _merge(blocks: List[Block], sm: SheetModel, base) -> Tuple[List[Block], Dict[str, Set[int]],
                                                                Dict[str, List[Block]]]:
    """Merge a train's variants that are the same apart from their days: (the variants left, in sheet order;
    the days of each merged one; the variants merged into each). Only variants with a DAYS code merge."""
    col = sm.cols.get("days")
    if not col:
        return blocks, {}, {}
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in blocks:
        if b.days and _days_of(b, base):
            groups[("same", _signature(b, col))].append(b)
        else:
            groups[("own", b.key)].append(b)
    left, days, merged = [], {}, {}
    for g in groups.values():
        keep = min(g, key=lambda b: b.start_row)
        left.append(keep)
        if len(g) > 1:
            days[keep.key] = set().union(*(_days_of(b, base) for b in g))
            merged[keep.key] = [b for b in g if b is not keep]
    return sorted(left, key=lambda b: b.start_row), days, merged


def plan_sheet(sm: SheetModel, base, by_time: bool, merge: bool = False, sx_style: bool = False
               ) -> Tuple[List[Optional[Block]], int, Dict[str, Tuple[str, List[Block]]]]:
    """The sheet's blocks in their new order (None where a variant was merged away), how many trains were
    changed, and the merges: kept block key -> (its new DAYS code, the blocks merged into it)."""
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in sm.blocks:
        if b.base_id:
            groups[(b.base_id, b.is_berth)].append(b)
    replacement: Dict[str, Optional[Block]] = {}
    merges: Dict[str, Tuple[str, List[Block]]] = {}
    moved = 0
    for blocks in (t for g in groups.values() for t in _trains(g, base)):
        if len(blocks) < 2:
            continue
        left, days, merged = _merge(blocks, sm, base) if merge else (blocks, {}, {})
        for k, gone in merged.items():
            merges[k] = (days_code(days[k], base, sx_style), gone)
        ordered = _order(left, base, by_time, days)
        if merged or [b.key for b in ordered] != [b.key for b in blocks]:
            moved += 1
        for i, slot in enumerate(blocks):              # the variants fill the positions they already had
            replacement[slot.key] = ordered[i] if i < len(ordered) else None
    return [replacement.get(b.key, b) for b in sm.blocks], moved, merges


def _rewrite(ws, sm: SheetModel, new_order: List[Optional[Block]],
             merges: Optional[Dict[str, Tuple[str, List[Block]]]] = None) -> Dict[int, int]:
    """Rewrite the data rows so the blocks follow `new_order` (None: a variant merged away, its rows
    removed and the rows below moved up); rows outside blocks stay put. A merged variant gets its new DAYS
    code. Returns {old row: new row} for every row that moved (rows removed point to the variant they were
    merged into)."""
    merges = merges or {}
    first = min(b.start_row for b in sm.blocks)
    last = max(b.end_row for b in sm.blocks)
    mc = max(ws.max_column, sm.max_col)
    by_start = {b.start_row: b for b in sm.blocks}
    # the data area as a list of chunks: whole blocks, and any rows between them (kept in place)
    chunks: List[tuple] = []
    r = first
    while r <= last:
        b = by_start.get(r)
        if b is not None:
            chunks.append(("block", b))
            r = b.end_row + 1
        else:
            chunks.append(("row", r))
            r += 1
    order = iter(new_order)
    sequence: List[Optional[int]] = []
    for kind, item in chunks:
        if kind == "block":
            nb = next(order)
            if nb is not None:
                sequence.extend(range(nb.start_row, nb.end_row + 1))
        else:
            sequence.append(item)
    removed = (last - first + 1) - len(sequence)
    end = last
    if removed:                                   # the rows below move up; the freed rows at the bottom are cleared
        end = max(ws.max_row, last)
        sequence.extend(range(last + 1, end + 1))
        sequence.extend([None] * removed)
    moved_at = [i for i, src in enumerate(sequence) if src != first + i]
    days_col = sm.cols.get("days")
    if not moved_at and not merges:
        return {}
    lo, hi = (moved_at[0], moved_at[-1]) if moved_at else (0, -1)
    snap = {}
    for row in sorted({src for src in sequence[lo:hi + 1] if src is not None}):
        cells = []
        for c in range(1, mc + 1):
            cell = ws.cell(row=row, column=c)
            cells.append((cell.value, copy(cell._style), copy(cell.hyperlink) if cell.hyperlink else None,
                          copy(cell.comment) if cell.comment else None))
        dim = ws.row_dimensions[row] if row in ws.row_dimensions else None
        snap[row] = (cells, (dim.height, dim.hidden, dim.outlineLevel) if dim is not None else None)
    row_map: Dict[int, int] = {}
    for target, src in enumerate(sequence[lo:hi + 1], start=first + lo):
        d = ws.row_dimensions[target]
        if src is None:                           # a freed row at the bottom
            for c in range(1, mc + 1):
                cell = ws.cell(row=target, column=c)
                cell.value, cell.hyperlink, cell.comment = None, None, None
                cell.style = "Normal"
            d.height, d.hidden, d.outlineLevel = None, False, 0
            continue
        cells, dim = snap[src]
        for c, (v, style, link, comment) in enumerate(cells, start=1):
            cell = ws.cell(row=target, column=c)
            cell.value = v
            if cell.data_type == "f":               # read as values, so this is text: never a live formula
                cell.data_type = "s"
            cell._style = style                     # a copy already, used once
            cell.hyperlink = link
            cell.comment = comment
        if dim is None:
            d.height, d.hidden, d.outlineLevel = None, False, 0
        else:
            d.height, d.hidden, d.outlineLevel = dim
        if src != target:
            row_map[src] = target
    if removed:
        for rng in list(ws.merged_cells.ranges):  # merged cells below the trains move up with their rows
            if rng.min_row > last:
                rng.shift(0, -removed)
    blocks = sm.block_by_key()
    for key, (code, gone) in merges.items():
        kept = blocks[key]
        at = row_map.get(kept.start_row, kept.start_row)
        if days_col:
            cell = ws.cell(row=at, column=days_col)
            cell.value = code or None
            if cell.data_type == "f":
                cell.data_type = "s"
        for b in gone:                            # links to a variant merged away now lead to the merged one
            for row in range(b.start_row, b.end_row + 1):
                row_map[row] = at
    return row_map


def reorder_cwn(path: str, out_dir: str = "", name: str = "", by_time: bool = False,
                log: Callable[[str], None] = lambda m: None, merge: bool = False) -> dict:
    """Write a copy of the CWN at `path` with every train's day variants in order (and, if `merge`, variants
    that are the same apart from their days merged into one). Returns {'path', 'trains', 'merged', 'tabs',
    'warnings'}."""
    from rstools.fsutil import unique_stem
    from .loader import load_any
    from .meta import is_comparison_output
    from .model import parse_workbook
    from .writer import _fix_hyperlinks
    from .xlsxfix import save_workbook
    if not path or not os.path.isfile(path):
        raise ReorderError(f"This file could not be found:\n{path}")
    if is_comparison_output(path):
        raise ReorderError("This is a comparison CWN made by this app. Choose the CWN itself - put its day "
                           "variants in order first, then compare.")
    log(f"Reading {os.path.basename(path)}")
    wb = load_any(path)
    model = parse_workbook(wb)
    if not model.sheets:
        raise ReorderError("No CWN location tabs (with an ID / TIME heading row) were found in this file.")
    base, _assumed = coverage(model, path)
    # a weekday CWN that writes 'every day but Friday' as FSX gets merged codes written the same way
    sx_style = any(re.fullmatch(r"(?i)[a-z]*sx", b.days or "") for sm in model.sheets.values() for b in sm.blocks)
    warnings, row_maps, trains, tabs, merged_n = list(model.warnings), {}, 0, 0, 0
    for sm in model.sheets.values():
        if not sm.blocks:
            continue
        ws = wb[sm.title]
        merged = [m for m in ws.merged_cells.ranges
                  if m.max_row >= min(b.start_row for b in sm.blocks)
                  and m.min_row <= max(b.end_row for b in sm.blocks)]
        new_order, moved, merges = plan_sheet(sm, base, by_time, merge, sx_style)
        if not moved:
            continue
        if merged:
            warnings.append(f"Tab '{sm.title}' has merged cells among its trains, so it was left as it was.")
            continue
        formulas = sum(1 for b in sm.blocks for r in range(b.start_row, b.end_row + 1)
                       for c in range(1, sm.max_col + 1)
                       if isinstance(ws.cell(row=r, column=c).value, str)
                       and ws.cell(row=r, column=c).value.startswith("="))
        if formulas:
            warnings.append(f"Tab '{sm.title}' has {formulas} formula cell(s) among its trains, so it was left as "
                            "it was (moving rows could change what the formulas refer to).")
            continue
        row_maps[sm.title] = _rewrite(ws, sm, new_order, merges)
        trains += moved
        tabs += 1
        gone = sum(len(g) for _c, g in merges.values())
        merged_n += gone
        log(f"{sm.title}: {moved} train(s) with variants put in order"
            + (f", {gone} variant(s) merged into another the same apart from its days" if gone else ""))
    for w in warnings:
        log("WARNING: " + w)
    if not trains:
        log("Every train's day variants are already in order" + (" and none can be merged" if merge else "")
            + " - no copy was saved.")
        return {"path": "", "trains": 0, "merged": 0, "tabs": 0, "warnings": warnings}
    _fix_hyperlinks(wb, row_maps, set())
    folder = out_dir or os.path.dirname(os.path.abspath(path))
    stem = name.strip() or os.path.splitext(os.path.basename(path))[0] + variants_suffix(by_time, merge)
    out = os.path.join(folder, unique_stem(folder, stem, (".xlsx",)) + ".xlsx")
    save_workbook(wb, out)
    log(f"Saved: {out}")
    return {"path": out, "trains": trains, "merged": merged_n, "tabs": tabs, "warnings": warnings}


def variants_suffix(by_time: bool, merge: bool) -> str:
    """The end of the default output name: ' (variants in day order)', ' (variants by time, merged)'."""
    return f" (variants {'by time' if by_time else 'in day order'}{', merged' if merge else ''})"
