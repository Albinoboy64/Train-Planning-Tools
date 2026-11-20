"""Put each train's day variants in day order in a multi-day CWN (a tidier copy; nothing is changed or lost).

A train that runs differently on different days has one entry (block) per variant, e.g. 1A23 (MO),
1A23 (TWThO), 1A23 (FO). CWNs list these in no fixed order. This writes a copy of the CWN in which,
on every location tab, each train's variants are ordered Monday first through to Friday (then
Saturday and Sunday) - or, if chosen, by departure time first and day second.

Only the variants of the same train swap places: they are put back into the positions those variants
already occupied, so every other train stays exactly where it was. Rows move whole - values, styles,
row heights and links - and links from other tabs are re-pointed to the rows' new positions.
"""
from __future__ import annotations

import os
from collections import defaultdict
from copy import copy
from typing import Callable, Dict, List, Tuple

from .days import coverage, code_days
from .model import Block, SheetModel


class ReorderError(Exception):
    pass


def _day_key(b: Block, base) -> Tuple[int, int]:
    """(first day the variant runs, number of days): MO before TWThO before FO; a Monday-only variant
    before an every-day one that also starts on Monday."""
    days = code_days(b.days or b.variant, base)
    if not days:
        return (99, 99)
    return (min(days), len(days))


def _order(blocks: List[Block], base, by_time: bool) -> List[Block]:
    def key(b: Block):
        t = b.sort_time if b.sort_time is not None else 9999
        d = _day_key(b, base)
        return (t, d) if by_time else (d, t)
    return sorted(blocks, key=key)


MAX_GAP = 240                   # minutes: variants of one train depart within a few hours of each other


def _trains(blocks: List[Block], base) -> List[List[Block]]:
    """Split the blocks sharing a headcode into trains. The variants of one train run on different
    days (MO, TWThO, FO); a second block running on a day already covered - e.g. the same ECS
    headcode used morning and evening - is another train. Returned in sheet order."""
    clusters: List[Tuple[set, List[int], List[Block]]] = []
    for b in sorted(blocks, key=lambda b: (b.sort_time if b.sort_time is not None else 9999, b.start_row)):
        days = code_days(b.days or b.variant, base) or set(base) or set(range(7))
        t = b.sort_time
        fits = [c for c in clusters if not (c[0] & days)
                and (t is None or not c[1] or min(abs(t - x) for x in c[1]) <= MAX_GAP)]
        if fits:
            c = min(fits, key=lambda c: min((abs(t - x) for x in c[1]), default=0) if t is not None else 0)
        else:
            c = (set(), [], [])
            clusters.append(c)
        c[0].update(days)
        if t is not None:
            c[1].append(t)
        c[2].append(b)
    return [sorted(c[2], key=lambda b: b.start_row) for c in clusters]


def plan_sheet(sm: SheetModel, base, by_time: bool) -> Tuple[List[Block], int]:
    """The sheet's blocks in their new order, and how many trains had their variants reordered."""
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in sm.blocks:
        if b.base_id:
            groups[(b.base_id, b.is_berth)].append(b)
    replacement: Dict[str, Block] = {}
    moved = 0
    for blocks in (t for g in groups.values() for t in _trains(g, base)):
        if len(blocks) < 2:
            continue
        ordered = _order(blocks, base, by_time)
        if [b.key for b in ordered] != [b.key for b in blocks]:
            moved += 1
        for slot, b in zip(blocks, ordered):          # the variants fill the positions they already had
            replacement[slot.key] = b
    return [replacement.get(b.key, b) for b in sm.blocks], moved


def _rewrite(ws, sm: SheetModel, new_order: List[Block]) -> Dict[int, int]:
    """Rewrite the data rows so the blocks follow `new_order`; rows outside blocks stay put.
    Returns {old row: new row} for every row that moved."""
    first = min(b.start_row for b in sm.blocks)
    last = max(b.end_row for b in sm.blocks)
    mc = max(ws.max_column, sm.max_col)
    by_start = {b.start_row: b for b in sm.blocks}
    # the data area as a list of chunks: whole blocks, and any rows between them (kept in place)
    chunks, r = [], first
    while r <= last:
        b = by_start.get(r)
        if b is not None:
            chunks.append(("block", b))
            r = b.end_row + 1
        else:
            chunks.append(("row", r))
            r += 1
    order = iter(new_order)
    sequence: List[int] = []
    for kind, item in chunks:
        if kind == "block":
            nb = next(order)
            sequence.extend(range(nb.start_row, nb.end_row + 1))
        else:
            sequence.append(item)
    moved_at = [i for i, src in enumerate(sequence) if src != first + i]
    if not moved_at:
        return {}
    # only the span from the first to the last row that moves is rewritten (rows outside it stay put)
    lo, hi = moved_at[0], moved_at[-1]
    sequence = sequence[lo:hi + 1]
    first, last = first + lo, first + hi
    snap = {}
    for row in range(first, last + 1):
        cells = []
        for c in range(1, mc + 1):
            cell = ws.cell(row=row, column=c)
            cells.append((cell.value, copy(cell._style), copy(cell.hyperlink) if cell.hyperlink else None,
                          copy(cell.comment) if cell.comment else None))
        dim = ws.row_dimensions[row] if row in ws.row_dimensions else None
        snap[row] = (cells, (dim.height, dim.hidden, dim.outlineLevel) if dim is not None else None)
    row_map = {}
    for target, src in enumerate(sequence, start=first):
        cells, dim = snap[src]
        for c, (v, style, link, comment) in enumerate(cells, start=1):
            cell = ws.cell(row=target, column=c)
            cell.value = v
            cell._style = style                     # a copy already, used once
            cell.hyperlink = link
            cell.comment = comment
        d = ws.row_dimensions[target]
        if dim is None:
            d.height, d.hidden, d.outlineLevel = None, False, 0
        else:
            d.height, d.hidden, d.outlineLevel = dim
        if src != target:
            row_map[src] = target
    return row_map


def reorder_cwn(path: str, out_dir: str = "", name: str = "", by_time: bool = False,
                log: Callable[[str], None] = lambda m: None) -> dict:
    """Write a copy of the CWN at `path` with every train's day variants in order. Returns
    {'path', 'trains', 'tabs', 'warnings'}."""
    from rstools.fsutil import unique_stem
    from .loader import load_any
    from .meta import is_comparison_output
    from .model import parse_workbook
    from .writer import _fix_hyperlinks
    from .xlsxfix import save_workbook
    if not path or not os.path.isfile(path):
        raise ReorderError(f"File not found:\n{path}")
    if is_comparison_output(path):
        raise ReorderError("This is a comparison CWN made by this app. Choose the CWN itself - put its day "
                           "variants in order first, then compare.")
    log(f"Reading {os.path.basename(path)}")
    wb = load_any(path)
    model = parse_workbook(wb)
    if not model.sheets:
        raise ReorderError("No CWN location tabs (with an ID / TIME heading row) were found in this file.")
    base, _assumed = coverage(model, path)
    warnings, row_maps, trains, tabs = list(model.warnings), {}, 0, 0
    for sm in model.sheets.values():
        if not sm.blocks:
            continue
        ws = wb[sm.title]
        merged = [m for m in ws.merged_cells.ranges
                  if m.max_row >= min(b.start_row for b in sm.blocks) and m.min_row <= max(b.end_row for b in sm.blocks)]
        new_order, moved = plan_sheet(sm, base, by_time)
        if not moved:
            continue
        if merged:
            warnings.append(f"Tab '{sm.title}' has merged cells among its trains, so it was left as it was.")
            continue
        formulas = sum(1 for b in sm.blocks for r in range(b.start_row, b.end_row + 1)
                       for c in range(1, sm.max_col + 1)
                       if isinstance(ws.cell(row=r, column=c).value, str) and ws.cell(row=r, column=c).value.startswith("="))
        if formulas:
            warnings.append(f"Tab '{sm.title}' has {formulas} formula cell(s) among its trains, so it was left as "
                            "it was (moving rows could change what the formulas refer to).")
            continue
        row_maps[sm.title] = _rewrite(ws, sm, new_order)
        trains += moved
        tabs += 1
        log(f"{sm.title}: {moved} train(s) with variants put in order")
    for w in warnings:
        log("WARNING: " + w)
    if not trains:
        log("Every train's day variants are already in order - no copy was saved.")
        return {"path": "", "trains": 0, "tabs": 0, "warnings": warnings}
    _fix_hyperlinks(wb, row_maps, set())
    folder = out_dir or os.path.dirname(os.path.abspath(path))
    stem = name.strip() or os.path.splitext(os.path.basename(path))[0] + (" (variants by time)" if by_time
                                                                           else " (variants in day order)")
    out = os.path.join(folder, unique_stem(folder, stem, (".xlsx",)) + ".xlsx")
    save_workbook(wb, out)
    log(f"Saved: {out}")
    return {"path": out, "trains": trains, "tabs": tabs, "warnings": warnings}
