"""Result sheets in the same look as the TT Comparison template.

Bold white headings on dark blue, Calibri 11, wrapped text, thin grey borders, frozen heading row,
filters, no gridlines, 'None identified' on an empty sheet, and print settings (A4 landscape, one
page wide, heading row repeated on every page).
"""
from __future__ import annotations

from copy import copy
from typing import Dict, Optional, Sequence

NONE = "None identified"
HEAD_FILL = "FF1F4E78"
FILLS = {"bad": "FFF4CCCC", "review": "FFFFEB9C", "ok": "FFC6EFCE", "info": "FFDDEBF7"}


def new_workbook():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.properties.creator = wb.properties.lastModifiedBy = "Train Planning Tools"
    wb.remove(wb.active)
    return wb


def add_sheet(wb, title: str, headers: Sequence[str], rows: Sequence[Sequence], widths: Sequence[float],
              formats: Optional[Dict[int, str]] = None, fills: Optional[Dict[int, str]] = None,
              bold_last: bool = False, center: Sequence[int] = ()):
    """A sheet of results. `formats` maps 1-based columns to number formats; `fills` maps 0-based row
    numbers to a FILLS key (the whole row is shaded); `center` lists 1-based columns to centre."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    from rstools.fsutil import clean_cell
    ws = wb.create_sheet(title[:31])
    thin = Side(style="thin", color="FFBFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_font, head_fill = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF"), PatternFill(
        "solid", fgColor=HEAD_FILL)
    head_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    body_font = Font(name="Calibri", size=11)
    left, middle = Alignment(vertical="top", wrap_text=True), Alignment(vertical="top", horizontal="center",
                                                                         wrap_text=True)
    formats, fills, centred = formats or {}, fills or {}, set(center)
    for c, text in enumerate(headers, start=1):
        cell = ws.cell(1, c, text)
        cell.font, cell.fill, cell.alignment, cell.border = head_font, head_fill, head_align, border
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1] if c <= len(widths) else 14
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = False
    if not rows:
        ws.cell(2, 1, NONE).font = Font(name="Calibri", size=11, italic=True, color="FF595959")
    shaded = {k: PatternFill("solid", fgColor=v) for k, v in FILLS.items()}
    bold = Font(name="Calibri", size=11, bold=True)
    styles: dict = {}                   # (column, fill, bold) -> finished style, built once and copied
    for r, row in enumerate(rows, start=2):
        fill_key = fills.get(r - 2, "")
        is_bold = bold_last and r == len(rows) + 1
        for c, value in enumerate(row, start=1):
            cell = ws.cell(r, c, clean_cell(value))
            key = (c, fill_key, is_bold)
            if key in styles:
                cell._style = copy(styles[key])
                continue
            cell.font = bold if is_bold else body_font
            cell.alignment = middle if c in centred else left
            cell.border = border
            if fill_key in shaded:
                cell.fill = shaded[fill_key]
            if c in formats:
                cell.number_format = formats[c]
            styles[key] = copy(cell._style)
    if rows:
        last = len(rows) + 1 - (1 if bold_last else 0)
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(last, 2)}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_title_rows = "1:1"
    from rstools.fsutil import plain_text
    plain_text(ws)                       # text from the inputs is never stored as a formula
    return ws


def save(wb, path: str, title: str, sections=None):
    """Excel through the repaired writer (opens cleanly in Excel), or PDF / Word from the sheets
    (or from `sections`, when the sheets need laying out differently on paper)."""
    if path.lower().endswith(".xlsx"):
        from cwn_compare.xlsxfix import save_workbook
        save_workbook(wb, path)
    else:
        from rstools.docexport import sections_from_workbook, write_document
        write_document(path, title, sections if sections is not None else sections_from_workbook(wb))
