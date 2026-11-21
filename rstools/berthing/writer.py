"""Writing a berthing chart workbook: the cover, one sheet per location in the chosen chart's order and
formatting - tidied (one font, consistent borders and column widths, no formulas, macros or old counting
sections) - and a Notes sheet with anything that needs checking."""
from __future__ import annotations

import datetime
from typing import Callable, List, Optional, Sequence

from .chart import fix_text
from .layout import DAY_COLUMNS, DEPOT_DAYS, CoverRow, DepotSheet, GridSheet, Layout

FONT = "Arial"
HEADER_FILL = "FFFF00"
DAY_WIDTH = 15.5


def _styles():
    from openpyxl.styles import Border, Font, PatternFill, Side
    return Border, Font, PatternFill, Side


def _font(size: float = 10, bold: bool = False, colour: str = "", italic: bool = False):
    _B, Font, _P, _S = _styles()
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=("FF" + colour) if colour else None)


def _fill(colour: str):
    _B, _F, PatternFill, _S = _styles()
    return PatternFill("solid", fgColor="FF" + colour) if colour else PatternFill(fill_type=None)


def _border(left: str = "", right: str = "", bottom: str = ""):
    Border, _F, _P, Side = _styles()
    side = lambda s: Side(style=s) if s else Side()
    return Border(left=side(left), right=side(right), bottom=side(bottom))


def write(layout: Layout, path: str, cover: Callable[[str], str] = lambda t: t,
          legend: Sequence[str] = (), notes: Sequence[str] = ()):
    """Save the chart. `cover` rewrites each cover line (issue, dates); `legend` lines are added to the cover;
    `notes` go on a Notes sheet at the end."""
    import openpyxl
    from cwn_compare.xlsxfix import save_workbook
    from rstools.fsutil import plain_text
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _cover(wb.create_sheet(layout.cover_name[:31] or "Cover"), layout.cover, cover, legend)
    for sheet in layout.sheets:
        ws = wb.create_sheet(sheet.name[:31])
        if isinstance(sheet, DepotSheet):
            _depot(ws, sheet)
        else:
            _grid(ws, sheet)
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


def _grid(ws, sheet: GridSheet):
    from openpyxl.utils import get_column_letter
    from rstools.fsutil import clean_cell
    r = 0
    for a, b in sheet.preface:
        r += 1
        _note_row(ws, r, a, b)
    r += 1
    hdr = r
    head = [sheet.corner[0] or "Siding", sheet.corner[1]] + DAY_COLUMNS
    for c, text in enumerate(head, start=1):
        cell = ws.cell(r, c, text or None)
        cell.font = _font()
        cell.fill = _fill(HEADER_FILL)
        cell.border = _border(left="thin" if c >= 4 and c % 2 == 0 else ("medium" if c == 2 else ""),
                              right="medium" if c == 2 else "", bottom="medium")
    for a, b in sheet.lead:
        r += 1
        _note_row(ws, r, a, b)
        _frame(ws, r, last=False)
    for blk in sheet.blocks:
        for off in range(max(1, blk.height)):
            r += 1
            a, b = (fix_text(blk.label), blk.capacity) if off == 0 else blk.notes.get(off, ("", ""))
            if off == 0 and 0 in blk.notes:
                b = b or blk.notes[0][1]
            _note_row(ws, r, a, b, bold_a=off == 0)
            cells = blk.units.get(off, [None] * 16)
            for i in range(16):
                cell = ws.cell(r, 3 + i)
                unit = cells[i] if i < len(cells) else None
                if unit is not None and unit.text:
                    cell.value = clean_cell(unit.text)
                    cell.font = _font(10, unit.bold, unit.colour, unit.italic)
                    cell.fill = _fill(unit.fill)
                elif (off, i) in blk.data_notes:
                    cell.value = fix_text(blk.data_notes[(off, i)])
                    cell.font = _font(10, True)
            _frame(ws, r, last=off == max(1, blk.height) - 1)
    widths = {1: max(12.0, min(sheet.widths.get(1, 18), 30)), 2: max(9.0, min(sheet.widths.get(2, 10), 18))}
    for c in range(1, 19):
        day = max(DAY_WIDTH, min(sheet.widths.get(c, DAY_WIDTH), 20))
        ws.column_dimensions[get_column_letter(c)].width = widths.get(c, day)
    ws.freeze_panes = ws.cell(hdr + 1, 3)
    ws.print_title_rows = f"{hdr}:{hdr}"
    ws.print_area = f"A1:R{max(r, hdr)}"
    _print(ws)


def _note_row(ws, r: int, a: str, b: str, bold_a: bool = False):
    if a:
        ws.cell(r, 1, fix_text(a)).font = _font(10, bold_a)
    if b:
        ws.cell(r, 2, fix_text(b)).font = _font()


def _frame(ws, r: int, last: bool):
    """The borders on a body row: a box round columns B, a line before each day's START, and a line under
    each berth."""
    bottom = "thin" if last else ""
    for c in range(1, 19):
        cell = ws.cell(r, c)
        cell.border = _border(left="medium" if c == 2 else ("thin" if c >= 4 and c % 2 == 0 else ""),
                              right="medium" if c == 2 else "", bottom=bottom)
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
