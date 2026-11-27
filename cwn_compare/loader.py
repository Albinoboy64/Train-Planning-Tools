"""Load any Excel CWN format into an openpyxl Workbook.

Supported: .xlsx .xlsm .xltx .xltm (native), .xls (via xlrd, with basic
formatting) and .xlsb (via pyxlsb, values only).  Whatever the input format,
the output CWN is always written as .xlsx.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import TYPE_CHECKING

from rstools.fsutil import clean_cell, sheet_title

if TYPE_CHECKING:                      # openpyxl itself is imported only when a file is read
    import openpyxl

NATIVE_EXT = {".xlsx", ".xlsm", ".xltx", ".xltm"}
SUPPORTED_EXT = NATIVE_EXT | {".xls", ".xlsb"}

FILE_TYPES = [
    ("Excel CWN files", "*.xlsx *.xlsm *.xls *.xlsb *.xltx *.xltm"),
    ("All files", "*.*"),
]


class LoadError(Exception):
    pass


def _put(ws, row: int, col: int, value):
    """Copy a value read from an .xls / .xlsb into a cell as data: control characters removed, and text kept as
    text even if it starts with '=' (openpyxl would otherwise store it as a live formula in the outputs)."""
    cell = ws.cell(row=row, column=col, value=clean_cell(value))
    if isinstance(value, str):
        cell.data_type = "s"
    return cell


def _load_native(path: str, read_only: bool, rich_text: bool, progress):
    """openpyxl's load_workbook, reporting how many of the tabs have been read so far."""
    import openpyxl
    if progress is None or read_only:
        return openpyxl.load_workbook(path, data_only=True, read_only=read_only, rich_text=rich_text)
    from openpyxl.reader.excel import ExcelReader

    class Reader(ExcelReader):
        def read_worksheets(self):
            sheets = list(self.parser.find_sheets())
            find = self.parser.find_sheets

            def each():
                for i, item in enumerate(sheets):
                    progress(i / max(len(sheets), 1))
                    yield item
                progress(1.0)
            self.parser.find_sheets = each
            try:
                super().read_worksheets()
            finally:
                self.parser.find_sheets = find
    reader = Reader(path, read_only=False, keep_vba=False, data_only=True, keep_links=True, rich_text=rich_text)
    reader.read()
    return reader.wb


def load_any(path: str, read_only: bool = False, rich_text: bool = False, progress=None) -> "openpyxl.Workbook":
    """read_only=True is faster and lighter for files that are only read (close() it after use). rich_text keeps
    text formatting within cells (a comparison CWN's struck-through previous values); progress(fraction) is
    called as each tab is read."""
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    import openpyxl                     # imported here so the app window opens faster
    ext = os.path.splitext(path)[1].lower()
    if not os.path.exists(path):
        raise LoadError(f"This file could not be found: {path}")
    try:
        if ext in NATIVE_EXT:
            from rstools.fsutil import check_office_file
            check_office_file(path)     # refuse a 'zip bomb' before unpacking
            return _load_native(path, read_only, rich_text, progress)
        if ext == ".xls":
            return _load_xls(path)
        if ext == ".xlsb":
            from rstools.fsutil import check_office_file
            check_office_file(path)     # an .xlsb is a zip too: the same 'zip bomb' limits as .xlsx
            return _load_xlsb(path)
    except LoadError:
        raise
    except PermissionError:
        raise LoadError(
            f"Cannot open '{os.path.basename(path)}' - it may be open in Excel. "
            "Close it and try again.")
    except Exception as exc:
        raise LoadError(f"Could not read '{os.path.basename(path)}' - it looks damaged or is not an Excel workbook "
                        f"({exc}). Open it in Excel, save it and try again.") from exc
    # Unknown extension: try openpyxl then xlrd.
    try:
        from rstools.fsutil import check_office_file
        check_office_file(path)     # refuse a 'zip bomb' before unpacking
        return openpyxl.load_workbook(path, data_only=True)
    except Exception:
        try:
            return _load_xls(path)
        except Exception as exc:
            raise LoadError(
                f"'{os.path.basename(path)}' is not a recognised Excel file.") from exc


def _load_xls(path: str) -> "openpyxl.Workbook":
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from rstools import limits
    try:
        limits.check_size(path, "XLS_MAX_BYTES", "Excel .xls workbook")   # before the file is opened
    except limits.TooLargeError as exc:
        raise LoadError(str(exc))
    import xlrd

    book = xlrd.open_workbook(path, formatting_info=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    palette = book.colour_map

    def rgb(idx):
        c = palette.get(idx)
        if not c:
            return None
        return "FF%02X%02X%02X" % c

    for sh in book.sheets():
        ws = wb.create_sheet(sheet_title(sh.name, wb.sheetnames))
        for r in range(sh.nrows):
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                val = cell.value
                if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
                    val = None
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        val = xlrd.xldate.xldate_as_datetime(val, book.datemode)
                        if val.date() == _dt.date(1899, 12, 31) or val.year < 1900:
                            val = val.time()
                    except Exception:
                        pass
                elif cell.ctype == xlrd.XL_CELL_NUMBER and float(val).is_integer():
                    val = int(val)
                try:
                    xf = book.xf_list[cell.xf_index]
                except Exception:
                    xf = None
                if val is None and xf is None:
                    continue
                oc = _put(ws, r + 1, c + 1, val)
                if xf is not None:
                    f = book.font_list[xf.font_index]
                    oc.font = Font(name=f.name, size=f.height / 20.0, bold=bool(f.bold),
                                   italic=bool(f.italic), strike=bool(f.struck_out),
                                   color=rgb(f.colour_index))
                    bg = xf.background
                    if bg.fill_pattern == 1:
                        col = rgb(bg.pattern_colour_index)
                        if col:
                            oc.fill = PatternFill("solid", fgColor=col)
                    al = xf.alignment
                    horiz = {1: "left", 2: "center", 3: "right"}.get(al.hor_align)
                    oc.alignment = Alignment(horizontal=horiz, wrap_text=bool(al.text_wrapped))
        for c, info in sh.colinfo_map.items():
            ws.column_dimensions[get_column_letter(c + 1)].width = info.width / 256.0
        for r, info in sh.rowinfo_map.items():
            if info.height:
                ws.row_dimensions[r + 1].height = info.height / 20.0
        for (r1, r2, c1, c2) in sh.merged_cells:
            ws.merge_cells(start_row=r1 + 1, end_row=r2, start_column=c1 + 1, end_column=c2)
        if sh.visibility:
            ws.sheet_state = "hidden"
    return wb


def _load_xlsb(path: str) -> "openpyxl.Workbook":
    import openpyxl
    from pyxlsb import open_workbook

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    with open_workbook(path) as book:
        for name in book.sheets:
            ws = wb.create_sheet(sheet_title(name, wb.sheetnames))
            with book.get_sheet(name) as sh:
                for row in sh.rows():
                    for c in row:
                        if c.v is None:
                            continue
                        v = c.v
                        if isinstance(v, float) and v.is_integer():
                            v = int(v)
                        _put(ws, c.r + 1, c.c + 1, v)
    return wb
