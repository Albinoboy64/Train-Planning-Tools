"""Apply a list of changes to the updated CWN workbook.

* changed cells are filled with the round's highlight colour
* with "show previous value" on, the old value is shown struck through on the
  line above the new value in the same cell, in the cell's own font
* explanatory notes (e.g. what an inbound used to form) go in a 'Change notes' column to the right of
  the CWN, on the row of the change they explain
* only cells holding text are coloured (a new or re-inserted train is not coloured across empty cells)
* cancelled trains (and removed rows) are re-inserted struck through
* tabs containing changes get their tab colour set
* ACWN output keeps only changed trains and only changed tabs
"""
from __future__ import annotations

import re
from collections import defaultdict
from copy import copy
from typing import Dict, List, Optional, Set

from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import PatternFill, Alignment

from rstools.fsutil import clean_cell
from .compare import Change
from .model import CWNModel, SheetModel, Block, cell_text
from .options import Options
from .xlsxfix import MAX_AUTO_WIDTH, col_dim, text_width

_LINK_RE = re.compile(r"^'?(.*?)'?!\$?([A-Z]{1,3})\$?(\d+)(.*)$")


def _fill(colour: str) -> PatternFill:
    return PatternFill("solid", fgColor="FF" + colour[-6:].upper())


def _font_with(font, **kw):
    f = copy(font)
    for k, v in kw.items():
        setattr(f, k, v)
    return f


def _inline(font, strike: bool = False) -> InlineFont:
    """Rich-text run font identical to the cell's own font (optionally struck through)."""
    return InlineFont(rFont=font.name, charset=font.charset, family=font.family, b=font.b, i=font.i,
                      strike=True if strike else None, outline=font.outline, shadow=font.shadow,
                      condense=font.condense, extend=font.extend,
                      color=copy(font.color) if font.color is not None else None,
                      sz=font.sz, u=font.u, vertAlign=font.vertAlign, scheme=font.scheme)


def resolve_row(c: Change, blk: Optional[Block]) -> Optional[int]:
    if blk is None:
        return None
    if c.target == "unit":
        for u in blk.units:
            if u.diag == c.target_key:
                return u.row
        return blk.units[0].row if len(blk.units) == 1 else None
    if c.target == "note":
        for r, t, _d in blk.notes:
            if t == c.target_key:
                return r
        return None
    if c.target == "nw":
        for r, key, _d in blk.nw:
            if key == c.target_key:
                return r
        return None
    if c.target == "inrow":
        for u in blk.units:
            if u.in_id == c.target_key:
                return u.row
    return blk.start_row


class _SheetOps:
    def __init__(self, sm: SheetModel):
        self.sm = sm
        self.cells: Dict[tuple, dict] = {}
        self.row_fill: Dict[int, str] = {}
        self.inserts: Dict[int, list] = defaultdict(list)
        self.changed_blocks: Set[str] = set()
        self.notes: Dict[int, List[tuple]] = defaultdict(list)    # row -> [(note, colour)]
        self.rounds: List[tuple] = []   # (round, colour) of applied changes

    def cell(self, r, c):
        return self.cells.setdefault((r, c), {"fill": None, "old": [], "cur": None, "seen": set()})

    @property
    def any(self):
        return bool(self.cells or self.row_fill or self.inserts or self.notes)


def apply_changes(wb, model: CWNModel, changes: List[Change], opts: Options,
                  acwn: bool = False, only_blocks: bool = False) -> Dict[str, int]:
    """Mutates wb.  Returns {sheet title: number of changes applied}. only_blocks: `model` holds only
    some trains (chosen days) - every other train's rows are left out of the output."""
    by_sheet: Dict[str, List[Change]] = defaultdict(list)
    for c in sorted(changes, key=lambda x: x.round):
        if opts.cat(c.category, "cwn"):
            by_sheet[c.sheet].append(c)

    if not opts.keep_links:
        # first, so rich-text old/new values and re-inserted rows pick up the plain fonts
        remove_hyperlinks(wb)
    summary: Dict[str, int] = {}
    row_maps: Dict[str, Dict[int, Optional[int]]] = {}
    removed_titles = set()
    for sk, sm in model.sheets.items():
        ws = wb[sm.title]
        ops = _SheetOps(sm)
        blocks = sm.block_by_key()
        n_applied = 0
        for c in by_sheet.get(sk, []):
            if _apply_one(c, ops, blocks, opts):
                n_applied += 1
                ops.rounds.append((c.round, c.colour))
        if not ops.any:
            if acwn:                                # ACWN: tabs without changes are left out
                removed_titles.add(ws.title)
                wb.remove(ws)
                continue
            if not only_blocks:                     # nothing to change on this tab
                continue
        else:
            summary[sm.title] = n_applied
        dims = ws.row_dimensions                 # .get: looking a row up must not create one for every row
        orig_heights = {r: d.height for r, d in dims.items() if r > sm.header_row}
        _write_cell_ops(ws, ops)
        if ops.inserts or acwn or only_blocks:
            keep: Optional[Set[int]] = None
            if acwn or only_blocks:
                keep = set()
                for b in sm.blocks:
                    if not acwn or b.key in ops.changed_blocks:
                        keep.update(range(b.start_row, b.end_row + 1))
            row_maps[ws.title] = _rebuild(ws, sm, keep, ops.inserts, orig_heights)
        if opts.highlight_tabs and ops.rounds:
            ws.sheet_properties.tabColor = "FF" + max(ops.rounds)[1][-6:].upper()

    if opts.keep_links:
        _fix_hyperlinks(wb, row_maps, removed_titles)
    tidy_workbook(wb)
    return summary


def _anchor_row(c: Change, sm: SheetModel, blocks: Dict[str, Block]) -> int:
    if c.anchor == "__TOP__":
        return sm.header_row
    if c.anchor in blocks:
        return blocks[c.anchor].end_row
    after = sm.header_row          # anchor gone: fall back to time order
    for b in sm.blocks:
        st = b.sort_time
        if c.sort_time is None or (st is not None and st <= c.sort_time):
            after = b.end_row
    return after


def _apply_one(c: Change, ops: _SheetOps, blocks: Dict[str, Block], opts: Options) -> bool:
    sm = ops.sm
    show_old = opts.cat(c.category, "show_old") and not c.hide_old
    colour = c.colour
    if c.kind == "remove_block":
        insert = True if c.category == "CANCELLED" else show_old
        if not insert or not c.rows:
            return False
        after = _anchor_row(c, sm, blocks)
        ops.inserts[after].append({"type": "rows", "rows": c.rows, "colour": colour,
                                   "template": max(after, sm.header_row + 1)})
        return True

    blk = blocks.get(c.block_key)
    if blk is None:
        return False
    ops.changed_blocks.add(blk.key)

    if c.kind == "add_block":
        for row in range(blk.start_row, blk.end_row + 1):
            ops.row_fill[row] = colour
        return True
    if c.kind == "add_row":
        r = resolve_row(c, blk)
        if r is None:
            return False
        ops.row_fill[r] = colour
        return True
    if c.kind == "remove_row":
        if show_old and c.rows:
            ops.inserts[blk.end_row].append({"type": "rows", "rows": c.rows, "colour": colour,
                                             "template": blk.start_row})
        else:   # flag the train so the change is still visible
            ops.cell(blk.start_row, sm.cols["id"])["fill"] = colour
        return True

    # modify
    r = resolve_row(c, blk)
    col = sm.cols.get(c.field)
    if r is None or col is None:
        return False
    st = ops.cell(r, col)
    st["fill"] = colour
    if c.target != "inrow":
        st["cur"] = c.new
        old_text = c.old or "-"
        if show_old and c.old != c.new and (c.round, old_text) not in st["seen"]:
            st["seen"].add((c.round, old_text))       # never stack the same old value twice
            st["old"].append(old_text)
    if show_old and c.note and all(n != c.note for n, _c in ops.notes[r]):
        ops.notes[r].append((c.note, colour))           # shown to the right of the change
    if c.target == "inrow" and not blk.is_berth:
        ops.cell(blk.start_row, sm.cols["id"])["fill"] = colour
    return True


def _write_cell_ops(ws, ops: _SheetOps):
    default_h = ws.sheet_format.defaultRowHeight or 15
    lines_per_row: Dict[int, tuple] = {}
    col_need: Dict[int, float] = {}
    for (r, c), st in ops.cells.items():
        cell = ws.cell(row=r, column=c)
        if st["fill"]:
            cell.fill = _fill(st["fill"])
        if not st["old"]:
            continue
        font = cell.font
        cur = clean_cell(st["cur"] if st["cur"] is not None else cell_text(cell.value))
        runs = []
        olds = [clean_cell(o) for o in st["old"]]
        for k, old in enumerate(olds):
            last = k == len(olds) - 1
            # the line break sits inside the struck run so it is never a whitespace-only run
            runs.append(TextBlock(_inline(font, strike=True), old if (last and not cur) else old + "\n"))
        if cur:
            runs.append(TextBlock(_inline(font), cur))
        cell.value = CellRichText(runs)
        al = cell.alignment
        cell.alignment = Alignment(horizontal=al.horizontal, vertical=al.vertical, wrap_text=True,
                                   indent=al.indent, text_rotation=al.text_rotation)
        n_lines = len(olds) + (1 if cur else 0)
        sz = float(font.sz or 11)
        prev = lines_per_row.get(r, (1, 0))
        lines_per_row[r] = (max(prev[0], n_lines), max(prev[1], sz))
        need = max(text_width(t, font) for t in olds + [cur])
        col_need[c] = max(col_need.get(c, 0), need)

    for r, (n, sz) in lines_per_row.items():
        line_h = max(ws.row_dimensions[r].height or default_h, sz * 1.32)
        ws.row_dimensions[r].height = round(line_h * n, 2)
    for c, need in col_need.items():
        dim = col_dim(ws, c)
        cur_w = dim.width if dim.width else 8.43
        if need > cur_w:
            dim.width = min(round(need, 1), max(cur_w, MAX_AUTO_WIDTH))

    max_col = ops.sm.max_col
    for r, colour in ops.row_fill.items():
        f = _fill(colour)
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            if cell.value not in (None, ""):             # colour the text, not the empty cells
                cell.fill = f
    if ops.notes:
        _write_notes(ws, ops)


NOTES_HEADING = "Change notes"


def _write_notes(ws, ops: _SheetOps):
    """Notes in a column just right of the CWN, beside the change they explain."""
    sm = ops.sm
    col = sm.max_col + 1
    head = ws.cell(row=sm.header_row, column=col)
    src = ws.cell(row=sm.header_row, column=sm.max_col)
    head.value = NOTES_HEADING
    if src.has_style:
        head._style = copy(src._style)
    width = len(NOTES_HEADING) + 2
    for r, notes in ops.notes.items():
        cell = ws.cell(row=r, column=col)
        text = "; ".join(n for n, _c in notes)
        cell.value = clean_cell(text)
        if cell.data_type == "f":
            cell.data_type = "s"           # a note is text, never a formula
        cell.fill = _fill(notes[-1][1])
        cell.font = _font_with(ws.cell(row=r, column=1).font, i=True, strike=None, u=None)
        cell.alignment = Alignment(vertical="center", wrap_text=len(text) > MAX_AUTO_WIDTH)
        width = max(width, min(len(text) + 2, MAX_AUTO_WIDTH))
    col_dim(ws, col).width = width


def _rebuild(ws, sm: SheetModel, keep: Optional[set], inserts: Dict[int, list],
             orig_heights: Dict[int, Optional[float]]) -> Dict[int, Optional[int]]:
    """Rewrite the data area of a sheet with inserted rows and/or only kept rows.

    Returns {original row: new row (None if dropped)} so hyperlinks can be re-pointed.
    """
    from .xlsxfix import data_extent
    hr = sm.header_row
    max_row, data_cols = data_extent(ws)          # not formatting that runs on past the data
    max_row = max(max_row, hr)
    mc = max(data_cols, sm.max_col + 1)
    snap = {}
    for r in range(hr + 1, max_row + 1):
        cells = []
        for c in range(1, mc + 1):
            cell = ws.cell(row=r, column=c)
            cells.append((cell.value, copy(cell._style), cell.hyperlink))
            cell.hyperlink = None
        dim = ws.row_dimensions.get(r)
        snap[r] = (cells, dim.height if dim is not None else None)

    seq = [("ins", x) for x in inserts.get(hr, [])]
    for r in range(hr + 1, max_row + 1):
        if keep is None or r in keep:
            seq.append(("src", r))
        seq.extend(("ins", x) for x in inserts.get(r, []))

    row_map: Dict[int, Optional[int]] = dict.fromkeys(snap)
    t = hr + 1
    for kind, item in seq:
        if kind == "src":
            cells, h = snap[item]
            for c, (v, style, link) in enumerate(cells, start=1):
                cell = ws.cell(row=t, column=c)
                cell.value = v
                if cell.data_type == "f":      # the CWN is read as values, so this is text: never a live formula
                    cell.data_type = "s"
                cell._style = copy(style)
                if link is not None:
                    cell.hyperlink = copy(link)
            if h is not None or t in ws.row_dimensions:
                ws.row_dimensions[t].height = h
            row_map[item] = t
            t += 1
            continue
        tmpl_cells = snap.get(item["template"], snap.get(hr + 1, ([], None)))[0]
        tmpl_h = orig_heights.get(item["template"])
        fill = _fill(item["colour"])
        for spec in item["rows"]:                      # removed rows put back, struck through
            vals = spec.get("v", [])
            for c in range(1, mc + 1):
                cell = ws.cell(row=t, column=c)
                v = vals[c - 1] if c - 1 < len(vals) else None
                cell.value = None if v in ("", None) else clean_cell(v)
                if cell.data_type == "f":
                    cell.data_type = "s"       # a re-inserted train's text, never a live formula
                if c - 1 < len(tmpl_cells):
                    cell._style = copy(tmpl_cells[c - 1][1])
                if cell.value is not None:             # strike and colour the text, not the empty cells
                    cell.font = _font_with(cell.font, b=bool(spec.get("b")), i=bool(spec.get("i")), strike=True)
                    cell.fill = fill
                else:                                  # (which may have copied a neighbour's highlight)
                    cell.fill = PatternFill(fill_type=None)
            ws.row_dimensions[t].height = tmpl_h
            t += 1

    if t <= max_row:
        ws.delete_rows(t, max_row - t + 1)
    for r in range(t, max_row + 1):
        if r in ws.row_dimensions:
            del ws.row_dimensions[r]
    if ws.auto_filter.ref:
        m = re.match(r"^([A-Z]+\d+):([A-Z]+)\d+$", ws.auto_filter.ref)
        if m:
            ws.auto_filter.ref = f"{m.group(1)}:{m.group(2)}{max(t - 1, hr)}"
    return row_map


def _fix_hyperlinks(wb, row_maps: "Dict[str, Dict[int, Optional[int]]] | Dict[str, Dict[int, int]]",
                    removed_titles: set):
    """CWN cells link to rows on other tabs: re-point them after rows were inserted/removed."""
    if not row_maps and not removed_titles:
        return
    for ws in wb.worksheets:
        for cell in list(ws._cells.values()):
            link = cell.hyperlink
            if link is None or not link.location:
                continue
            m = _LINK_RE.match(link.location)
            if not m:
                continue
            title, col, row, rest = m.group(1).replace("''", "'"), m.group(2), int(m.group(3)), m.group(4)
            if title in removed_titles:
                cell.hyperlink = None
                continue
            rmap = row_maps.get(title)
            if not rmap or row not in rmap:
                continue
            new_row = rmap[row]
            q = "'" + title.replace("'", "''") + "'"
            nl = copy(link)
            nl.location = f"{q}!{col}{new_row}{rest}" if new_row else f"{q}!A1"
            cell.hyperlink = nl


def remove_hyperlinks(wb, where=None):
    """Drop the tab-to-tab headcode links (tens of thousands of them make Excel slow to open).
    The link styling (underline and link colour) goes too, so the text reads as normal text.
    `where(sheet_title, row, column)`, if given, limits this to the cells it returns True for."""
    plain = {}
    for ws in wb.worksheets:
        for cell in ws._cells.values():
            if cell.hyperlink is None:
                continue
            if where is not None and not where(ws.title, cell.row, cell.column):
                continue
            cell.hyperlink = None
            style = getattr(cell, "_style", None)
            if style is None:                       # merged cells / cells moved without a style record
                continue
            font_id = style.fontId
            if font_id not in plain:
                font = cell.font
                plain[font_id] = _font_with(font, u=None, color=None) if font.u else None
            if plain[font_id] is not None:
                cell.font = plain[font_id]
        if where is None:
            ws._hyperlinks = []


def tidy_workbook(wb):
    """Write empty-string cells as truly empty cells (Excel can reject empty inline strings)
    and drop out-of-range print settings carried over from the source file."""
    for ws in wb.worksheets:
        ps = ws.page_setup
        for attr in ("copies", "horizontalDpi", "verticalDpi", "scale", "paperSize"):
            if getattr(ps, attr, None) in (0, "0"):
                setattr(ps, attr, None)
        for cell in ws._cells.values():
            if cell._value == "":
                cell._value = None
                cell.data_type = "n"
