"""Writing a berthing chart workbook: the cover, one sheet per location in the chosen chart's order and
formatting - tidied (one font, consistent borders and column widths, no formulas, macros or old counting
sections) - and a Notes sheet with anything that needs checking."""
from __future__ import annotations

import datetime
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .chart import fix_text
from .layout import (COUNTS_END, COUNTS_HEAD, DAY_COLUMNS, DEPOT_DAYS, SECTION_HEAD, SECTION_LINE, Block, CoverRow,
                     DepotSheet, GridSheet, Layout)

FONT = "Arial"
HEADER_FILL = "FFFF00"
SIDING_FILL = "CCFFFF"          # the siding names and capacities, light blue as on the original charts
NOTE_COLOUR = "FF0000"          # notes about the sidings: red bold
NOTE_FILL = "FFF2CC"            # a long note inside a berth's box: pale yellow
NIGHT_LINE = "595959"           # the line between one day's FINISH and the next day's START (before each START column)
COUNT_FILL = "EDEDED"
OVER_FILL = "FFC7CE"            # more cars than the siding location holds
DAY_WIDTH = 17.0
ROW_HEIGHT = 15.0
MIN_ROWS = 3                    # rows in every berth's box, at least
LONG_NOTE = 40                  # a note longer than this goes on its own full-width row under the location
OTHER_PREFIX = "Other - "          # the label of a berth made for a location that is not on the chart's sheets
WIDE_LABEL_CAP = 80.0           # column A's widest, for the 'Other - ...' labels and the counts headings
LONG_DATA_NOTE = 18             # ... and a note in the day columns longer than this (it would spill over the boxes)


def _styles():
    from openpyxl.styles import Border, Font, PatternFill, Side
    return Border, Font, PatternFill, Side


def _font(size: float = 10, bold: bool = False, colour: str = "", italic: bool = False):
    _B, Font, _P, _S = _styles()
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=("FF" + colour) if colour else None)


def _fill(colour: str):
    _B, _F, PatternFill, _S = _styles()
    return PatternFill("solid", fgColor="FF" + colour) if colour else PatternFill(fill_type=None)


def _border(left: str = "", right: str = "", bottom: str = "", left_colour: str = "", bottom_colour: str = "",
            top: str = ""):
    Border, _F, _P, Side = _styles()

    def side(style: str, colour: str = ""):
        return Side(style=style, color=("FF" + colour) if colour else None) if style else Side()
    return Border(left=side(left, left_colour), right=side(right), bottom=side(bottom, bottom_colour), top=side(top))


def write(layout: Layout, path: str, cover: Callable[[str], str] = lambda t: t,
          legend: Sequence[str] = (), notes: Sequence[str] = (), counts: bool = False):
    """Save the chart. `cover` rewrites each cover line (issue, dates); `legend` lines are added to the cover;
    `notes` go on a Notes sheet at the end; `counts` adds the unit counts of each siding location."""
    import openpyxl
    from cwn_compare.xlsxfix import save_workbook
    from rstools.fsutil import plain_text
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _cover(wb.create_sheet(layout.cover_name[:31] or "Cover"), layout.cover, cover, legend)
    widths = _siding_widths(layout, counts)
    for sheet in layout.sheets:
        ws = wb.create_sheet(sheet.name[:31])
        if isinstance(sheet, DepotSheet):
            _depot(ws, sheet)
        else:
            _grid(ws, sheet, widths, counts)
        if sheet.hidden:
            ws.sheet_state = "hidden"
        if sheet.tab:
            ws.sheet_properties.tabColor = "FF" + sheet.tab
    if notes:
        ws = wb.create_sheet("Notes")
        ws.column_dimensions["A"].width = 140
        ws.cell(1, 1, "Notes").font = _font(12, True)
        for i, text in enumerate(notes, start=3):
            c = ws.cell(i, 1, text)
            c.font = _font()
            from openpyxl.styles import Alignment
            c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.properties.creator = wb.properties.lastModifiedBy = "Train Planning Tools"
    for ws in wb.worksheets:
        plain_text(ws)                       # text from the inputs is never stored as a formula
    save_workbook(wb, path)


def _cover(ws, rows: List[CoverRow], rewrite: Callable[[str], str], legend: Sequence[str]):
    from openpyxl.styles import Alignment
    r = 0
    for r, row in enumerate(rows, start=1):
        for col, (text, size, bold, colour) in row.cells.items():
            c = ws.cell(r, col, fix_text(rewrite(text)))
            c.font = _font(size, bold, colour if colour not in ("000000",) else "")
            if row.merged:
                c.alignment = Alignment(horizontal="center", vertical="center")
        if row.merged and row.cells:
            first = min(row.cells)
            ws.merge_cells(start_row=r, start_column=first, end_row=r, end_column=15)
            size = max(v[1] for v in row.cells.values())
            ws.row_dimensions[r].height = max(15, size * 1.35)
    present = {t for row in rows for (t, _s, _b, _c) in row.cells.values()}
    extra = [line for line in legend if line not in present]   # a chart made by the app already has them
    r += 2 if extra else 0
    for line in extra:
        ws.cell(r, 3, line).font = _font(10, True)
        r += 1
    for letter, width in (("A", 10), ("B", 10), ("C", 14)):
        ws.column_dimensions[letter].width = width
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    ws.sheet_view.showGridLines = False


def _siding_widths(layout: Layout, counts: bool = False) -> Tuple[float, float]:
    """Columns A and B (siding, capacity) one width on every sheet: wide enough for the longest label or short
    note. The 'Other - ...' berth labels and, with `counts`, the 'Unit counts - <location>' headings are long and
    sit beside column B, so they may widen column A further than ordinary labels do (up to WIDE_LABEL_CAP)."""
    a = b = 0
    wide = 0
    for sheet in layout.sheets:
        if not isinstance(sheet, GridSheet):
            continue
        for blk in sheet.blocks:
            if blk.label.startswith(OTHER_PREFIX):
                wide = max(wide, len(blk.label))
            else:
                a = max(a, len(blk.label))
            b = max(b, len(blk.capacity))
            for na, nb in blk.notes.values():
                if len(na) <= LONG_NOTE:
                    a = max(a, len(na))
                if len(nb) <= LONG_NOTE:
                    b = max(b, len(nb))
        if counts:
            for sec in sorted({blk.section for blk in sheet.blocks}):
                name = sheet.sections[sec] if sec < len(sheet.sections) else ""
                wide = max(wide, len(f"{COUNTS_HEAD} \u2013 {name}" if name else COUNTS_HEAD))
    a_width = max(14.0, min(a * 1.15 + 3, 30.0))
    if wide:
        a_width = max(a_width, min(wide * 1.15 + 3, WIDE_LABEL_CAP))
    return a_width, max(10.0, min(b * 1.15 + 3, 18.0))


def _short_notes(blk: Block) -> Tuple[List[Tuple[str, str]], List[str]]:
    """A berth's notes: the short ones, in order, for the rows under its label (gaps closed up), and the long
    ones, which go on their own row under its siding location."""
    short: List[Tuple[str, str]] = []
    long: List[str] = []
    for off in sorted(blk.notes):
        if off == 0:
            continue                                    # beside the label, in column B
        a, b = blk.notes[off]
        long += [t for t in (a, b) if len(t) > LONG_NOTE]
        a = a if len(a) <= LONG_NOTE else ""
        b = b if len(b) <= LONG_NOTE else ""
        if a or b:
            short.append((a, b))
    return short, long


def _box_notes(blk: Block) -> List[str]:
    """A berth's long notes, in order: they are written inside its own box (not between two locations)."""
    _short, long = _short_notes(blk)
    return long + [t for _k, t in sorted(blk.data_notes.items()) if len(t) > LONG_DATA_NOTE]


def _notes_start(blk: Block) -> int:
    """The first row of the box (counting its label row as 0) below the units, where its long notes start."""
    used = [o for o, row in blk.units.items() if any(row)] + [
        o for (o, _i), t in blk.data_notes.items() if len(t) <= LONG_DATA_NOTE]
    return max(used) + 1 if used else 0


def _rows_needed(blk: Block) -> int:
    short, _long = _short_notes(blk)
    used = [o for o, row in blk.units.items() if any(row)] + [o for o, _i in blk.data_notes]
    notes = _box_notes(blk)
    return max([MIN_ROWS, 1 + len(short)] + [o + 1 for o in used] + ([_notes_start(blk) + len(notes)] if notes else []))


def _grid(ws, sheet: GridSheet, widths: Tuple[float, float] = (18.0, 10.0), counts: bool = False):
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter
    from rstools.fsutil import clean_cell
    fit = Alignment(horizontal="left", vertical="center", shrink_to_fit=True)    # a long unit shrinks, never spills
    r = 0
    for a, b in sheet.preface:
        r += 1
        _note_row(ws, r, a, b, siding=True)
    r += 1
    hdr = r
    head = [sheet.corner[0] or "Siding", sheet.corner[1] or "Capacity"] + DAY_COLUMNS
    for c, text in enumerate(head, start=1):
        cell = ws.cell(r, c, text or None)
        cell.font = _font(10, True)
        cell.fill = _fill(SIDING_FILL if c <= 2 else HEADER_FILL)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _line(c, bottom="medium")
    ws.row_dimensions[r].height = 27
    for a, b in sheet.lead:
        r += 1
        if len(a) > LONG_NOTE or len(b) > LONG_NOTE:
            _wide_note(ws, r, " ".join(t for t in (a, b) if t))
            continue
        _note_row(ws, r, a, b, siding=True)
        _frame(ws, r)
    height = max([_rows_needed(b) for b in sheet.blocks] + [MIN_ROWS])      # every box on the sheet the same
    sections = sorted({b.section for b in sheet.blocks})
    for sec in sections:
        blocks = [b for b in sheet.blocks if b.section == sec]
        if len(sections) > 1:                           # a sheet with several siding locations: name each one
            name = sheet.sections[sec] if sec < len(sheet.sections) else ""
            if name and not blocks[0].label.startswith(OTHER_PREFIX):       # an 'Other - ...' berth is its own name
                r += 1
                _location_banner(ws, r, name)
        for blk in blocks:
            short, _long = _short_notes(blk)
            notes, first = _box_notes(blk), _notes_start(blk)
            for off in range(height):
                r += 1
                if off == 0:
                    side = blk.notes[0][1] if 0 in blk.notes else ""
                    _siding(ws, r, fix_text(blk.label), blk.capacity, side)
                else:
                    a, b = short[off - 1] if off - 1 < len(short) else ("", "")
                    _note_row(ws, r, a, b, siding=True)
                cells = blk.units.get(off, [None] * 16)
                for i in range(16):
                    cell = ws.cell(r, 3 + i)
                    unit = cells[i] if i < len(cells) else None
                    if unit is not None and unit.text:
                        cell.value = clean_cell(unit.text)
                        cell.font = _font(10, unit.bold, unit.colour, unit.italic)
                        cell.fill = _fill(unit.fill)
                    elif (off, i) in blk.data_notes and len(blk.data_notes[(off, i)]) <= LONG_DATA_NOTE:
                        cell.value = fix_text(blk.data_notes[(off, i)])
                        cell.font = _font(10, True, NOTE_COLOUR)
                    cell.alignment = fit
                _frame(ws, r, bottom="thin" if off == height - 1 else "")
                ws.row_dimensions[r].height = ROW_HEIGHT
                if first <= off < first + len(notes):   # a long note: across the day columns, in this berth's box
                    _box_note(ws, r, notes[off - first], bottom="thin" if off == height - 1 else "")
        if counts:
            name = sheet.sections[sec] if sec < len(sheet.sections) else ""
            r = _counts(ws, r, name, blocks)
        if len(sections) > 1 or counts:
            for c in range(1, 19):                      # the line under each siding location
                cell = ws.cell(r, c)
                old = cell.border
                cell.border = _border(left=old.left.style or "", right=old.right.style or "", bottom="medium",
                                      left_colour=_colour_of(old.left), bottom_colour=SECTION_LINE)
    a_width, b_width = widths
    for c in range(1, 19):
        ws.column_dimensions[get_column_letter(c)].width = {1: a_width, 2: b_width}.get(c, DAY_WIDTH)
    ws.freeze_panes = f"C{hdr + 1}"
    ws.print_title_rows = f"{hdr}:{hdr}"
    ws.print_area = f"A1:R{max(r, hdr)}"
    _print(ws)


def _location_banner(ws, r: int, name: str):
    """The name of a siding location across the whole sheet (white bold on the location line's blue), above its berths.
    A chart made by the app is read back with these rows skipped (layout.SECTION_HEAD)."""
    from openpyxl.styles import Alignment
    cell = ws.cell(r, 1, f"{SECTION_HEAD} \u2013 {fix_text(name)}")
    cell.font = _font(11, True, "FFFFFF")
    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    for c in range(1, 19):
        ws.cell(r, c).fill = _fill(SECTION_LINE)
        ws.cell(r, c).border = _border(left="medium" if c == 1 else "", right="medium" if c == 18 else "",
                                       bottom="thin")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=18)
    ws.row_dimensions[r].height = ROW_HEIGHT * 1.35


def _box_note(ws, r: int, text: str, bottom: str = ""):
    """A long note about a berth, across all the day columns of one of its rows (red bold on pale yellow)."""
    from openpyxl.styles import Alignment
    cell = ws.cell(r, 3)
    cell.value = fix_text(text)
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=18)
    for c in range(3, 19):                              # set after merging, so every edge of the range keeps its line
        part = ws.cell(r, c)
        part.fill = _fill(NOTE_FILL)
        part.border = _border(left="medium" if c == 3 else "", right="medium" if c == 18 else "", bottom=bottom)
    cell.font = _font(10, True, NOTE_COLOUR)
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1)


def _wide_note(ws, r: int, text: str):
    """A long note about the sidings on its own row, across the whole sheet, in red bold on the siding blue."""
    from openpyxl.styles import Alignment
    cell = ws.cell(r, 1, fix_text(text))
    cell.font = _font(10, True, NOTE_COLOUR)
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    for c in range(1, 19):
        ws.cell(r, c).fill = _fill(SIDING_FILL)
        ws.cell(r, c).border = _border(bottom="thin", right="medium" if c == 18 else "")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=18)
    ws.row_dimensions[r].height = ROW_HEIGHT * max(1, -(-len(text) // 170))


def _colour_of(side) -> str:
    try:
        rgb = side.color.rgb if side is not None and side.color is not None else ""
        return rgb[-6:] if isinstance(rgb, str) else ""
    except AttributeError:
        return ""


_TYPE = re.compile(r"^\s*L?\s*\(?\s*(\d{1,2})\s*(\d{3})")


def unit_type(text: str) -> Optional[Tuple[int, str]]:
    """(cars, class) of a unit on the chart - '4 387 02+02', '(4 377)', 'L4 377 Berth', '12700 0228TLK' - or None
    for anything else ('TLK' continuation rows, 'SPARE', notes)."""
    m = _TYPE.match(text or "")
    return (int(m.group(1)), m.group(2)) if m else None


def _counts(ws, r: int, name: str, blocks: List[Block]) -> int:
    """The unit counts of one siding location under its berths: a row per unit type (cars and class) with the
    number of units each night's FINISH and START, and a Cars row, red where it is over the location's
    capacity. Returns the last row used."""
    from openpyxl.styles import Alignment
    per: Dict[str, List[int]] = {}
    cars = [0] * 16
    for blk in blocks:
        for row in blk.units.values():
            for i, unit in enumerate(row[:16]):
                t = unit_type(unit.text) if unit is not None else None
                if t is None:
                    continue
                per.setdefault(f"{t[0]} {t[1]}", [0] * 16)[i] += 1
                cars[i] += t[0]
    caps = [re.match(r"\s*(\d+)", b.capacity) for b in blocks]
    capacity = sum(int(m.group(1)) for m in caps if m) if caps and all(caps) else 0
    centre = Alignment(horizontal="center", vertical="center")
    r += 1
    middle = Alignment(vertical="center")
    head = ws.cell(r, 1, f"{COUNTS_HEAD} – {name}" if name else COUNTS_HEAD)
    head.font = _font(10, True)
    head.alignment = middle
    for c in range(1, 19):
        ws.cell(r, c).fill = _fill(COUNT_FILL)
        ws.cell(r, c).border = _line(c, top="thin")
    ws.row_dimensions[r].height = ROW_HEIGHT
    rows = sorted(per.items(), key=lambda kv: (kv[0].split()[1], int(kv[0].split()[0])))
    for key, values in rows + [(COUNTS_END, cars)]:
        r += 1
        label = ws.cell(r, 1, key)
        label.font, label.alignment = _font(10, True), middle
        if key == COUNTS_END and capacity:
            cap = ws.cell(r, 2, f"of {capacity}")
            cap.font, cap.alignment = _font(10, True), Alignment(horizontal="center", vertical="center")
        for c in range(1, 19):
            ws.cell(r, c).fill = _fill(COUNT_FILL)
            ws.cell(r, c).border = _line(c)
        for i, v in enumerate(values):
            cell = ws.cell(r, 3 + i, v or None)
            cell.font = _font(10, key == COUNTS_END)
            cell.alignment = centre
            if key == COUNTS_END and capacity and v > capacity:
                cell.fill = _fill(OVER_FILL)
        ws.row_dimensions[r].height = ROW_HEIGHT
    return r


def _siding(ws, r: int, label: str, capacity: str, side_note: str):
    """A berth's first row in columns A and B: its name, and its capacity (or a note, in red)."""
    from openpyxl.styles import Alignment
    a = ws.cell(r, 1, label or None)
    a.font = _font(10, True)
    a.fill = _fill(SIDING_FILL)
    a.alignment = Alignment(vertical="center")
    b = ws.cell(r, 2, fix_text(capacity or side_note) or None)
    b.font = _font(10, True, "" if capacity else NOTE_COLOUR)
    b.fill = _fill(SIDING_FILL)
    b.alignment = Alignment(horizontal="center" if capacity else "left", vertical="center")


def _line(c: int, bottom: str = "", top: str = ""):
    """The vertical lines of column `c`: a box round the siding columns, a darker line between one day's FINISH
    and the next day's START (before each START column) and a thin one between a day's own START and FINISH."""
    right = "medium" if c == 18 else ""
    if c == 2:
        return _border(left="medium", right="medium", bottom=bottom, top=top)
    if c >= 4 and c % 2 == 0:
        return _border(left="medium", left_colour=NIGHT_LINE, right=right, bottom=bottom, top=top)
    if c >= 5:
        return _border(left="thin", right=right, bottom=bottom, top=top)
    return _border(right=right, bottom=bottom, top=top)


def _note_row(ws, r: int, a: str, b: str, bold_a: bool = False, siding: bool = False):
    """A row's columns A and B: notes about the sidings in red bold, on the siding columns' blue."""
    for col, text in ((1, a), (2, b)):
        cell = ws.cell(r, col, fix_text(text) if text else None)
        if siding:
            cell.fill = _fill(SIDING_FILL)
        if text:
            cell.font = _font(10, True, NOTE_COLOUR) if siding else _font(10, bold_a)


def _frame(ws, r: int, bottom: str = ""):
    """The borders on a body row (see _line), with a line under the last row of each berth."""
    for c in range(1, 19):
        cell = ws.cell(r, c)
        cell.border = _line(c, bottom=bottom)
        if cell.font is None or cell.font.name != FONT:
            cell.font = _font()


def _depot(ws, sheet: DepotSheet):
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter
    from rstools.fsutil import clean_cell
    r = 0
    for blk in sheet.blocks:
        r += 1
        ws.cell(r, 1, blk.title).font = _font(12, True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=16)
        r += 1
        ws.cell(r, 1, DEPOT_DAYS[0])
        for i, day in enumerate(DEPOT_DAYS[1:-1]):
            ws.cell(r, 2 + 2 * i, day)
            ws.merge_cells(start_row=r, start_column=2 + 2 * i, end_row=r, end_column=3 + 2 * i)
        ws.cell(r, 16, DEPOT_DAYS[-1])
        r += 1
        for c in range(1, 17):
            ws.cell(r, c, "FINISH" if c % 2 else "START")
        for rr in (r - 1, r):
            for c in range(1, 17):
                cell = ws.cell(rr, c)
                cell.font, cell.fill = _font(), _fill(HEADER_FILL)
                cell.alignment = Alignment(horizontal="center")
                cell.border = _border(left="thin" if c % 2 == 0 else "", bottom="medium" if rr == r else "")
        for row in range(max(blk.rows, len(blk.cells))):
            r += 1
            cells = blk.cells[row] if row < len(blk.cells) else [None] * 16
            for c in range(16):
                cell = ws.cell(r, c + 1)
                v = cells[c] if c < len(cells) else None
                if v is not None and v.text:
                    cell.value = clean_cell(v.text)
                    cell.font = _font(10, v.bold, v.colour)
                    cell.fill = _fill(v.fill)
                else:
                    cell.font = _font()
                cell.border = _border(left="thin" if c % 2 == 1 else "",
                                      bottom="thin" if row == max(blk.rows, len(blk.cells)) - 1 else "")
        r += 1
    for c in range(1, 17):
        ws.column_dimensions[get_column_letter(c)].width = 11
    ws.freeze_panes = None
    _print(ws)


def _print(ws):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5


def cover_rewriter(issue: str = "", start: str = "", end: str = "",
                   today: Optional[datetime.date] = None) -> Callable[[str], str]:
    """Rewrites the cover's issue line ('Proof 1'), date range ('13/12/26 - 15/05/27') and 'Issued ...' date."""
    import re
    today = today or datetime.date.today()

    def short(iso: str) -> str:
        try:
            return datetime.date.fromisoformat(iso).strftime("%d/%m/%y")
        except ValueError:
            return ""
    dates = f"{short(start)} - {short(end)}" if short(start) and short(end) else ""

    def rewrite(text: str) -> str:
        if issue and re.fullmatch(r"(proof|draft|final|issue|supp\w*|version|stp)\b.*", text.strip(), re.I) \
                and len(text) < 40:
            return issue
        if dates and re.fullmatch(r"\s*\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s*", text):
            return dates
        if re.match(r"^\s*issued\b", text, re.I):
            return f"Issued {today:%d/%m/%Y}"
        return text
    return rewrite


LEGEND = ["Text colour: 387/2 Gatwick Express red, 387/3 Southern green.",
          "RP: forms the rear portion of another train, attached to by a unit that moves onto it that day.",
          "Berth: the unit stays berthed all that day."]
STP_LEGEND = "STP trains are shown in bold on a lavender fill."
