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

from rstools.days import DAY_LETTERS as _DAY_TOKENS

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
    """What may still differ between a train's variants for them to merge (their days always may, and so may the
    AM / PM berths: where the unit starts and ends its day is not about this location)."""
    diagrams: bool = False          # the DIAG cells
    berths: bool = False            # the day codes of a berth / next-day working line for the same next working
    berth_diagrams: bool = False    # ... and that next working's diagram number


MARKER = "\u25be"                   # '▾': a value that varies by day (click the cell for each day's value)
ACCENT = "FF00707A"                 # dark teal: stands out, reads well printed
_NW_PARTS = re.compile(r"^(?P<pre>berth\s+)?(?P<diag>[a-z]{1,4}\d{1,4}[a-z]?)\s+(?P<time>\d{1,2}[.+:]\d{2})"
                       r"(?:\s?(?P<days>[a-z]{1,8}))?(?P<rest>\b.*)?$", re.I)
_VARY_TITLE = {"diag": "Diagram varies by day", "am": "AM berth varies by day", "pm": "PM berth varies by day",
               "dest": "Next working varies by day"}


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
    if col in (cols.get("am"), cols.get("pm")):
        return "berth"
    if rules.diagrams and col == cols.get("diag") and text:
        return ("diag", text.startswith("("), text.endswith(")"))
    if rules.berths and col == cols.get("dest"):
        d = _nw(text)
        if d is not None:
            return ("nw", d["pre"].casefold(), "" if rules.berth_diagrams else d["diag"].casefold(), d["time"],
                    d["rest"].strip().casefold())
    return text


def _signature(b: Block, cols: Dict[str, int], rules: MergeRules, extra=None) -> tuple:
    """A block's contents apart from its DAYS cell (and what `rules` let differ): the same for variants that
    can merge. `extra(b)` adds to it (in a comparison CWN: how each cell is highlighted)."""
    days_col = cols.get("days")
    sig = tuple(tuple(_norm(cell_text(v), c, cols, rules) for c, v in enumerate(spec["v"], start=1)
                      if c != days_col) for spec in b.rows)
    return sig + (extra(b),) if extra else sig


def _field_names(cols: Dict[str, int]) -> Dict[int, str]:
    from .model import FIELD_LABELS
    return {c: FIELD_LABELS.get(f, f).lower() for f, c in cols.items()}


def why_not_merged(a: Block, b: Block, cols: Dict[str, int], rules: MergeRules) -> str:
    """Why two variants of a train stay apart on a tab: the first thing that differs, e.g. 'units: 3 rows vs 2'
    or 'platform: 13 vs 12'."""
    if len(a.rows) != len(b.rows):
        return f"{len(a.rows)} rows (units and notes) vs {len(b.rows)}"
    names = _field_names(cols)
    days_col = cols.get("days")
    for ra, rb in zip(a.rows, b.rows):
        for c in range(1, max(len(ra["v"]), len(rb["v"])) + 1):
            if c == days_col:
                continue
            ta = cell_text(ra["v"][c - 1]) if c - 1 < len(ra["v"]) else ""
            tb = cell_text(rb["v"][c - 1]) if c - 1 < len(rb["v"]) else ""
            if _norm(ta, c, cols, rules) != _norm(tb, c, cols, rules):
                return f"{names.get(c, 'column ' + str(c))}: {ta or 'blank'} vs {tb or 'blank'}"
    return "highlighting or change notes"


def _only_code(days: Set[int]) -> str:
    return "".join(_DAY_TOKENS[d] for d in sorted(days)) + "O" if days else ""


@dataclass
class Varies:
    """A merged cell whose value differs by day: shown as the value for most days and a marker; clicking it
    lists each value with its days (an Excel input message and drop-down)."""
    text: str                         # what the cell shows
    title: str                        # the pop-up's title
    items: List[Tuple[str, str]]      # (value, its days code), first day first

    def prompt(self) -> str:
        return "\n".join(f"{code}: {v}" if code else v for v, code in self.items)


def _by_day(values: List[Tuple[str, Set[int], str]], code) -> Tuple[str, List[Tuple[str, str]]]:
    """(the value covering the most days - the first day on a tie, the values with their days code, first day
    first). A value from one variant keeps that variant's own code (TWThO); one from several gets their days
    combined."""
    by_value: Dict[str, List[Tuple[Set[int], str]]] = {}
    for v, days, own in values:
        by_value.setdefault(v, []).append((days, own))

    def days_of(src) -> Set[int]:
        return set().union(*(d for d, _o in src))
    ordered = sorted(by_value.items(), key=lambda x: min(days_of(x[1]), default=99))
    main = max(ordered, key=lambda x: (len(days_of(x[1])), -min(days_of(x[1]), default=99)))[0]
    items = [(v or "(none)", src[0][1] if len(src) == 1 and src[0][1] else code(days_of(src)))
             for v, src in ordered]
    return main, items


def _marked(main: str) -> str:
    return f"{main} {MARKER}" if main else MARKER


def _merged_cells(group: List[Block], cols: Dict[str, int], base, sx_style: bool) -> Dict[Tuple[int, int], object]:
    """The cells of the merged variant that differ between the variants merged: (row offset, column) -> a
    Varies, or plain text (a berth line whose day codes were combined)."""
    days = [_days_of(b, base) for b in group]
    texts = [[[cell_text(v) for v in spec["v"]] for spec in b.rows] for b in group]
    field = {c: f for f, c in cols.items()}
    out: Dict[Tuple[int, int], object] = {}
    for i in range(len(texts[0])):
        for c in range(1, max(len(t[i]) for t in texts) + 1):
            if c == cols.get("days"):
                continue
            vals = [t[i][c - 1] if c - 1 < len(t[i]) else "" for t in texts]
            if len(set(vals)) == 1:
                continue
            f = field.get(c)
            if f in ("diag", "am", "pm"):
                first = next((v for v in vals if v), "")
                lead = "(" if first.startswith("(") else ""
                trail = ")" if first.endswith(")") else ""
                inner = [(v.strip("()").strip(), d, b.raw.get("days", "")) for v, d, b in zip(vals, days, group)]
                main, items = _by_day(inner, lambda d: days_code(d, base, sx_style))
                out[(i, c)] = Varies(lead + _marked(main) + trail, _VARY_TITLE[f], items)
            elif f == "dest":
                nws = [_nw(v) for v in vals]
                if any(d is None for d in nws):
                    continue
                head = nws[0]
                assert head is not None
                nd = [code_days(d["days"], range(7)) or set() if d else set() for d in nws]
                union = set().union(*nd)
                tail = " " + head["time"] + _only_code(union) + head["rest"]
                if len({d["diag"] for d in nws if d}) == 1:
                    out[(i, c)] = head["pre"] + head["diag"] + tail
                else:
                    main, items = _by_day([(d["diag"], x, d["days"]) for d, x in zip(nws, nd) if d], _only_code)
                    out[(i, c)] = Varies(head["pre"] + _marked(main) + tail, _VARY_TITLE[f], items)
    return out


def _merge(blocks: List[Block], sm: SheetModel, base, rules: MergeRules, sx_style: bool, extra=None
           ) -> Tuple[List[Block], Dict[str, Set[int]], Dict[str, Tuple[List[Block], dict]], List[str]]:
    """Merge a train's variants that are the same apart from their days (and what `rules` let differ): (the
    variants left, in sheet order; the days of each merged one; the variants merged into each and the cells of
    the merged one that change; why the variants left with days stay apart). Only variants with a DAYS code
    merge."""
    if not sm.cols.get("days"):
        return blocks, {}, {}, []
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in blocks:
        if b.days and _days_of(b, base):
            groups[("same", _signature(b, sm.cols, rules, extra))].append(b)
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
    left.sort(key=lambda b: b.start_row)
    dated = [b for b in left if b.days and _days_of(b, base)]
    apart = []
    for b in dated[1:]:
        reason = why_not_merged(dated[0], b, sm.cols, rules)
        apart.append(f"{b.label()} kept apart from {dated[0].label()} ({reason})")
    return left, days, merged, apart


Merges = Dict[str, Tuple[str, List[Block], dict]]


def plan_sheet(sm: SheetModel, base, by_time: bool, merge: bool = False, sx_style: bool = False,
               rules: Optional[MergeRules] = None, extra=None
               ) -> Tuple[List[Optional[Block]], int, Merges, List[str]]:
    """The sheet's blocks in their new order (None where a variant was merged away), how many trains were
    changed, the merges: kept block key -> (its new DAYS code, the blocks merged into it, its cells that
    change: (row offset, column) -> Varies or text), and why variants that could not merge stay apart."""
    rules = rules or MergeRules()
    groups: Dict[tuple, List[Block]] = defaultdict(list)
    for b in sm.blocks:
        if b.base_id:
            groups[(b.base_id, b.is_berth)].append(b)
    replacement: Dict[str, Optional[Block]] = {}
    merges: Merges = {}
    apart: List[str] = []
    moved = 0
    for blocks in (t for g in groups.values() for t in _trains(g, base)):
        if len(blocks) < 2:
            continue
        left, days, merged, why = (_merge(blocks, sm, base, rules, sx_style, extra) if merge
                                   else (blocks, {}, {}, []))
        apart += why
        for k, (gone, cells) in merged.items():
            merges[k] = (days_code(days[k], base, sx_style), gone, cells)
        ordered = _order(left, base, by_time, days)
        if merged or [b.key for b in ordered] != [b.key for b in blocks]:
            moved += 1
        for i, slot in enumerate(blocks):              # the variants fill the positions they already had
            replacement[slot.key] = ordered[i] if i < len(ordered) else None
    return [replacement.get(b.key, b) for b in sm.blocks], moved, merges, apart


def _write_varies(cell, v: "Varies | str", dvs: Dict[tuple, list]):
    """Write a merged cell that differs by day: the main value and marker in the accent colour, and an input
    message (and drop-down) listing each day's value, shown when the cell is clicked."""
    if isinstance(v, str):
        cell.value = v
        cell.data_type = "s"                       # text from the CWN stays text, never a formula
        return
    from openpyxl.styles import Font
    cell.value = v.text
    cell.data_type = "s"
    f = cell.font
    cell.font = Font(name=f.name, sz=f.sz, b=f.b, i=f.i, u=f.u, strike=f.strike, vertAlign=f.vertAlign,
                     color=ACCENT)
    items = [f"{val} ({code})" if code else val for val, code in v.items]
    listed = ",".join(i.replace(",", " ").replace('"', "'") for i in items)
    key = (v.title[:32], v.prompt()[:255], listed if len(listed) <= 250 else "")
    dvs.setdefault(key, []).append(cell.coordinate)


def _add_validations(ws, dvs: Dict[tuple, list]):
    from openpyxl.worksheet.datavalidation import DataValidation
    for (title, prompt, listed), refs in dvs.items():
        dv = DataValidation(type="list" if listed else None, formula1=f'"{listed}"' if listed else None,
                            allow_blank=True, showErrorMessage=False, showInputMessage=True,
                            promptTitle=title, prompt=prompt)
        dv.sqref = " ".join(refs)
        ws.add_data_validation(dv)


def _fit_columns(ws, wanted: Dict[int, list]):
    """Widen columns (never narrow) so the text written into their cells shows in full."""
    from .xlsxfix import fit_column
    for col, cells in wanted.items():
        fit_column(ws, col, cells)


def _rewrite(ws, sm: SheetModel, new_order: List[Optional[Block]],
             merges: Optional[Merges] = None) -> Dict[int, int]:
    """Rewrite the data rows so the blocks follow `new_order` (None: a variant merged away, its rows
    removed and the rows below moved up); rows outside blocks stay put. A merged variant gets its new DAYS
    code, and its cells that differ by day the value for most days, a marker and a click-to-show list.
    Returns {old row: new row} for every row that moved (rows removed point to the variant they were
    merged into)."""
    from .xlsxfix import data_extent
    merges = merges or {}
    first = min(b.start_row for b in sm.blocks)
    last = max(b.end_row for b in sm.blocks)
    data_rows, data_cols = data_extent(ws)
    mc = max(data_cols, sm.max_col + 1)           # the CWN's columns and a change-note column beside them
    cells_of = ws._cells
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
    if removed:                                   # the rows below move up; the freed rows at the bottom are cleared
        end = max(data_rows, last)
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
            cell = cells_of.get((row, c))
            cells.append(None if cell is None else
                         (cell.value, copy(cell._style), copy(cell.hyperlink) if cell.hyperlink else None,
                          copy(cell.comment) if cell.comment else None))
        dim = ws.row_dimensions.get(row)
        snap[row] = (cells, (dim.height, dim.hidden, dim.outlineLevel) if dim is not None else None)
    row_map: Dict[int, int] = {}
    for target, src in enumerate(sequence[lo:hi + 1], start=first + lo):
        if src is None:                           # a freed row at the bottom: nothing left in it
            for c in range(1, mc + 1):
                cells_of.pop((target, c), None)
            ws.row_dimensions.pop(target, None)
            continue
        cells, dim = snap[src]
        for c, got in enumerate(cells, start=1):
            if got is None:
                cells_of.pop((target, c), None)
                continue
            v, style, link, comment = got
            cell = ws.cell(row=target, column=c)
            cell.value = v
            if cell.data_type == "f":               # read as values, so this is text: never a live formula
                cell.data_type = "s"
            cell._style = style                     # a copy already, used once
            cell.hyperlink = link
            cell.comment = comment
        if dim is not None:
            d = ws.row_dimensions[target]
            d.height, d.hidden, d.outlineLevel = dim
        elif target in ws.row_dimensions:
            ws.row_dimensions.pop(target, None)
        if src != target:
            row_map[src] = target
    if removed:
        for rng in list(ws.merged_cells.ranges):  # merged cells below the trains move up with their rows
            if rng.min_row > last:
                rng.shift(0, -removed)
    blocks = sm.block_by_key()
    dvs: Dict[tuple, list] = {}
    widths: Dict[int, list] = defaultdict(list)
    for key, (code, gone, changed) in merges.items():
        kept = blocks[key]
        at = row_map.get(kept.start_row, kept.start_row)
        if days_col:
            cell = ws.cell(row=at, column=days_col)
            cell.value = code or None
            if cell.data_type == "f":
                cell.data_type = "s"
            widths[days_col].append(cell)
        for (offset, col), v in changed.items():
            cell = ws.cell(row=at + offset, column=col)
            _write_varies(cell, v, dvs)
            widths[col].append(cell)
        for b in gone:                            # links to a variant merged away now lead to the merged one
            for row in range(b.start_row, b.end_row + 1):
                row_map[row] = at
    _add_validations(ws, dvs)
    _fit_columns(ws, widths)
    return row_map


def _highlights(ws, sm: SheetModel):
    """In a comparison CWN: how each cell of a block is marked (highlight, struck-through old values, change
    note), so variants merge only when their changes are shown the same way."""
    notes = sm.max_col + 1
    days_col = sm.cols.get("days")
    cells_of = ws._cells

    def sig(b: Block) -> tuple:
        out = []
        for r in range(b.start_row, b.end_row + 1):
            for c in range(1, notes + 1):
                cell = cells_of.get((r, c))
                if cell is None or cell.value in (None, ""):
                    continue
                fill = cell.fill
                rgb = fill.fgColor.rgb if fill is not None and fill.fill_type == "solid" else None
                text = "" if c == days_col and type(cell.value) is str else str(cell.value)   # days may differ
                out.append((r - b.start_row, c, text, rgb if isinstance(rgb, str) else None,
                            bool(cell.font.strike)))
        return tuple(out)
    return sig


def reorder_cwn(path: str, out_dir: str = "", name: str = "", by_time: bool = False,
                log: Callable[[str], None] = lambda m: None, merge: bool = False,
                rules: Optional[MergeRules] = None,
                progress: Callable[[float, str], None] = lambda f, m: None) -> dict:
    """Write a copy of the CWN at `path` with every train's day variants in order (and, if `merge`, variants
    that are the same apart from their days merged into one). A comparison CWN made by this app can be put in
    order too: its highlights, struck-through previous values and change notes move with their rows.
    Returns {'path', 'trains', 'merged', 'tabs', 'warnings', 'apart'}."""
    from rstools.fsutil import output_folder, unique_stem
    from .loader import load_any
    from .meta import is_comparison_output
    from .model import parse_workbook
    from .writer import _fix_hyperlinks
    from .xlsxfix import save_workbook
    if not path or not os.path.isfile(path):
        raise ReorderError(f"This file could not be found:\n{path}")
    comparison = is_comparison_output(path)
    log(f"Reading {os.path.basename(path)}" + (" (a comparison CWN)" if comparison else ""))
    progress(0.02, "Reading the CWN...")
    wb = load_any(path, rich_text=comparison,
                  progress=lambda f: progress(0.02 + 0.5 * f, "Reading the CWN..."))
    model = parse_workbook(wb)
    if not model.sheets:
        raise ReorderError("No CWN location tabs (with an ID / TIME heading row) were found in this file.")
    base, _assumed = coverage(model, path)
    # a weekday CWN that writes 'every day but Friday' as FSX gets merged codes written the same way
    sx_style = any(re.fullmatch(r"(?i)[a-z]*sx", b.days or "") for sm in model.sheets.values() for b in sm.blocks)
    warnings, row_maps, trains, tabs, merged_n = list(model.warnings), {}, 0, 0, 0
    apart_all: List[str] = []
    sheets = [sm for sm in model.sheets.values() if sm.blocks]
    for n, sm in enumerate(sheets):
        progress(0.55 + 0.3 * n / max(len(sheets), 1), f"Putting variants in order: {sm.title}")
        ws = wb[sm.title]
        merged = [m for m in ws.merged_cells.ranges
                  if m.max_row >= min(b.start_row for b in sm.blocks)
                  and m.min_row <= max(b.end_row for b in sm.blocks)]
        new_order, moved, merges, apart = plan_sheet(sm, base, by_time, merge, sx_style, rules,
                                                     _highlights(ws, sm) if comparison else None)
        apart_all += [f"{sm.title}: {a}" for a in apart]
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
    if merge and apart_all:
        log(f"{len(apart_all)} variant(s) differ on their tab, so they were kept apart:")
        for a in apart_all[:APART_SHOWN]:
            log("  " + a)
        if len(apart_all) > APART_SHOWN:
            log(f"  ... and {len(apart_all) - APART_SHOWN} more")
    for w in warnings:
        log("WARNING: " + w)
    if not trains:
        log("Every train's day variants are already in order" + (" and none can be merged" if merge else "")
            + " - no copy was saved.")
        progress(1.0, "Nothing to change")
        return {"path": "", "trains": 0, "merged": 0, "tabs": 0, "warnings": warnings, "apart": apart_all}
    _fix_hyperlinks(wb, row_maps, set())
    _unlink_diagram_cells(wb, model)
    folder = output_folder(out_dir)
    stem = name.strip() or os.path.splitext(os.path.basename(path))[0] + variants_suffix(by_time, merge)
    out = os.path.join(folder, unique_stem(folder, stem, (".xlsx",)) + ".xlsx")
    save_workbook(wb, out, trim="data", progress=lambda f: progress(0.85 + 0.15 * f, "Saving..."))
    log(f"Saved: {out}")
    progress(1.0, "Done")
    return {"path": out, "trains": trains, "merged": merged_n, "tabs": tabs, "warnings": warnings,
            "apart": apart_all}


def _unlink_diagram_cells(wb, model):
    """Diagram numbers (DIAG / AM / PM) carry no link to another tab: clicking one stays on the cell, so its
    each-day values can be read (a link would jump away first). Headcode links elsewhere are kept."""
    from .writer import remove_hyperlinks
    cols = {sm.title: ({sm.cols[k] for k in ("diag", "am", "pm") if k in sm.cols},
                       min((b.start_row for b in sm.blocks), default=sm.header_row + 1))
            for sm in model.sheets.values()}

    def where(title, row, col):
        hit = cols.get(title)
        return hit is not None and col in hit[0] and row >= hit[1]
    remove_hyperlinks(wb, where)


APART_SHOWN = 300                  # lines of 'kept apart' detail in the log (the rest are counted)


def variants_suffix(by_time: bool, merge: bool) -> str:
    """The end of the default output name: ' (variants in day order)', ' (variants by time, merged)'."""
    return f" (variants {'by time' if by_time else 'in day order'}{', merged' if merge else ''})"
