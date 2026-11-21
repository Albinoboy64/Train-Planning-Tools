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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class MergeRules:
    """What may still differ between a train's variants for them to merge (their days always may)."""
    diagrams: bool = False          # the DIAG cells: the merged cell shows each diagram with its days
    berths: bool = False            # the day codes of a berth / next-day working line for the same next working
    berth_diagrams: bool = False    # ... and that next working's diagram number


Part = Tuple[str, bool]             # (text, shown small): a cell written as rich text
_NW_PARTS = re.compile(r"^(?P<pre>berth\s+)?(?P<diag>[a-z]{1,4}\d{1,4}[a-z]?)\s+(?P<time>\d{1,2}[.+:]\d{2})"
                       r"(?:\s?(?P<days>[a-z]{1,8}))?(?P<rest>\b.*)?$", re.I)


def _nw(text: str) -> Optional[dict]:
    """A berth / next-day working line split up: 'Berth HE317 05.17TO (2)' -> pre 'Berth ', diag 'HE317',
    time '05.17', days 'TO', rest ' (2)'. None if it is not one (or its day code is not a day code)."""
    from .model import _day_tokens
    m = _NW_PARTS.match(text or "")
    if not m:
        return None
    d = {k: v or "" for k, v in m.groupdict().items()}
    if d["days"] and _day_tokens(d["days"]) is None:
        return None
    return d


def _norm(text: str, col: int, cols: Dict[str, int], rules: MergeRules):
    """A cell as compared for merging: what may differ is replaced by a placeholder."""
    if rules.diagrams and col == cols.get("diag") and text:
        return ("diag", text.startswith("("), text.endswith(")"))
    if rules.berths and col == cols.get("dest"):
        d = _nw(text)
        if d is not None:
            return ("nw", d["pre"].casefold(), "" if rules.berth_diagrams else d["diag"].casefold(), d["time"],
                    d["rest"].strip().casefold())
    return text


def _signature(b: Block, cols: Dict[str, int], rules: MergeRules) -> tuple:
    """A block's contents apart from its DAYS cell (and what `rules` let differ): the same for variants that
    can merge."""
    days_col = cols.get("days")
    return tuple(tuple(_norm(cell_text(v), c, cols, rules) for c, v in enumerate(spec["v"], start=1)
                       if c != days_col) for spec in b.rows)


def _only_code(days: Set[int]) -> str:
    return "".join(_DAY_TOKENS[d] for d in sorted(days)) + "O" if days else ""


def _with_days(values: List[Tuple[str, Set[int], str]], code) -> List[Part]:
    """Different values side by side, each followed by its days in small type: '549' WSX ' / 549A' WO. A value
    from one variant keeps that variant's own day code (TWThO); one from several gets their days combined."""
    by_value: Dict[str, List[Tuple[Set[int], str]]] = {}
    for v, days, own in values:
        by_value.setdefault(v, []).append((days, own))
    parts: List[Part] = []
    def first_day(src) -> int:
        days = set().union(*(d for d, _o in src))
        return min(days) if days else 99
    ordered = sorted(by_value.items(), key=lambda x: first_day(x[1]))
    for n, (v, src) in enumerate(ordered):
        days = set().union(*(d for d, _o in src))
        parts += [((" / " if n else "") + v, False), (src[0][1] if len(src) == 1 and src[0][1] else code(days), True)]
    return [(t, small) for t, small in parts if t]


def _merged_cells(group: List[Block], cols: Dict[str, int], base, sx_style: bool) -> Dict[Tuple[int, int], list]:
    """The cells of the merged variant that differ between the variants merged: (row offset, column) -> parts."""
    days = [_days_of(b, base) for b in group]
    texts = [[[cell_text(v) for v in spec["v"]] for spec in b.rows] for b in group]
    out: Dict[Tuple[int, int], list] = {}
    for i in range(len(texts[0])):
        for c in range(1, max(len(t[i]) for t in texts) + 1):
            if c == cols.get("days"):
                continue
            vals = [t[i][c - 1] if c - 1 < len(t[i]) else "" for t in texts]
            if len(set(vals)) == 1:
                continue
            if c == cols.get("diag"):
                lead = "(" if vals[0].startswith("(") else ""
                trail = ")" if vals[0].endswith(")") else ""
                inner = [(v.strip("()"), d, b.raw.get("days", "")) for v, d, b in zip(vals, days, group)]
                parts = _with_days(inner, lambda d: days_code(d, base, sx_style))
                out[(i, c)] = ([(lead, False)] if lead else []) + parts + ([(trail, False)] if trail else [])
            elif c == cols.get("dest"):
                nws = [_nw(v) for v in vals]
                if any(d is None for d in nws):
                    continue
                first = nws[0]
                assert first is not None
                nd = [code_days(d["days"], range(7)) or set() if d else set() for d in nws]
                diag_parts = _with_days([(d["diag"], x, d["days"]) for d, x in zip(nws, nd) if d], _only_code)
                if len({d["diag"] for d in nws if d}) == 1:
                    diag_parts = [(first["diag"], False)]
                union = set().union(*nd)
                out[(i, c)] = ([(first["pre"], False)] if first["pre"] else []) + diag_parts + [
                    (" " + first["time"] + _only_code(union) + first["rest"], False)]
    return out


def _merge(blocks: List[Block], sm: SheetModel, base, rules: MergeRules, sx_style: bool
           ) -> Tuple[List[Block], Dict[str, Set[int]], Dict[str, Tuple[List[Block], dict]]]:
    """Merge a train's variants that are the same apart from their days (and what `rules` let differ): (the
    variants left, in sheet order; the days of each merged one; the variants merged into each and the cells of
    the merged one that change). Only variants with a DAYS code merge."""
    if not sm.cols.get("days"):
        return blocks, {}, {}
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in blocks:
        if b.days and _days_of(b, base):
            groups[("same", _signature(b, sm.cols, rules))].append(b)
        else:
            groups[("own", b.key)].append(b)
    left, days, merged = [], {}, {}
    for g in groups.values():
        g.sort(key=lambda b: b.start_row)
        keep = g[0]
        left.append(keep)
        if len(g) > 1:
            days[keep.key] = set().union(*(_days_of(b, base) for b in g))
            merged[keep.key] = (g[1:], _merged_cells(g, sm.cols, base, sx_style))
    return sorted(left, key=lambda b: b.start_row), days, merged


Merges = Dict[str, Tuple[str, List[Block], dict]]


def plan_sheet(sm: SheetModel, base, by_time: bool, merge: bool = False, sx_style: bool = False,
               rules: Optional[MergeRules] = None) -> Tuple[List[Optional[Block]], int, Merges]:
    """The sheet's blocks in their new order (None where a variant was merged away), how many trains were
    changed, and the merges: kept block key -> (its new DAYS code, the blocks merged into it, its cells that
    change: (row offset, column) -> text parts)."""
    rules = rules or MergeRules()
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in sm.blocks:
        if b.base_id:
            groups[(b.base_id, b.is_berth)].append(b)
    replacement: Dict[str, Optional[Block]] = {}
    merges: Merges = {}
    moved = 0
    for blocks in (t for g in groups.values() for t in _trains(g, base)):
        if len(blocks) < 2:
            continue
        left, days, merged = _merge(blocks, sm, base, rules, sx_style) if merge else (blocks, {}, {})
        for k, (gone, cells) in merged.items():
            merges[k] = (days_code(days[k], base, sx_style), gone, cells)
        ordered = _order(left, base, by_time, days)
        if merged or [b.key for b in ordered] != [b.key for b in blocks]:
            moved += 1
        for i, slot in enumerate(blocks):              # the variants fill the positions they already had
            replacement[slot.key] = ordered[i] if i < len(ordered) else None
    return [replacement.get(b.key, b) for b in sm.blocks], moved, merges


def _write_parts(cell, parts: List[Part]):
    """Write text parts into a cell in its own font, the small parts (day codes) in a smaller size."""
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    if not any(small for _t, small in parts):
        cell.value = "".join(t for t, _s in parts)
        return
    f = cell.font
    size = float(f.sz or 11)

    def font(small: bool) -> InlineFont:
        return InlineFont(rFont=f.name, sz=max(6.0, round(size * 0.7, 1)) if small else size, b=f.b, i=f.i,
                          color=copy(f.color) if f.color is not None else None, strike=f.strike)
    cell.value = CellRichText([TextBlock(font(small), t) for t, small in parts if t])


def _rewrite(ws, sm: SheetModel, new_order: List[Optional[Block]],
             merges: Optional[Merges] = None) -> Dict[int, int]:
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
    for key, (code, gone, changed) in merges.items():
        kept = blocks[key]
        at = row_map.get(kept.start_row, kept.start_row)
        if days_col:
            cell = ws.cell(row=at, column=days_col)
            cell.value = code or None
            if cell.data_type == "f":
                cell.data_type = "s"
        for (offset, col), parts in changed.items():
            _write_parts(ws.cell(row=at + offset, column=col), parts)
        for b in gone:                            # links to a variant merged away now lead to the merged one
            for row in range(b.start_row, b.end_row + 1):
                row_map[row] = at
    return row_map


def reorder_cwn(path: str, out_dir: str = "", name: str = "", by_time: bool = False,
                log: Callable[[str], None] = lambda m: None, merge: bool = False,
                rules: Optional[MergeRules] = None) -> dict:
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
        new_order, moved, merges = plan_sheet(sm, base, by_time, merge, sx_style, rules)
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
        gone = sum(len(g) for _c, g, _cells in merges.values())
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
