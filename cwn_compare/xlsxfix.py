"""Post-save clean-up so output files open quickly and are strictly schema-valid.

* openpyxl writes every text cell as an *inline* string.  Excel's own files keep
  each distinct text once in a shared-string table; a CWN has ~300,000 text
  cells but only a few thousand distinct values, so inline strings make Excel
  much slower to open the file.  They are converted to a shared-string table.
* openpyxl asks Excel to recalculate the whole workbook on open
  (fullCalcOnLoad); CWNs hold no formulas, so that flag is removed.
* openpyxl writes the child elements of <font> in a non-standard order; they
  are re-ordered to the schema sequence (Excel's own order).
* row "spans" (a loading hint Excel itself always writes) are added.
* formatting outside the data (styled empty cells, whole-row and whole-column styles running far past the
  last train - common in CWNs) is trimmed, so Excel's Check Performance finds no unused formatting.
"""
from __future__ import annotations

import io
import re
import zipfile
from copy import copy

from rstools.zipw import write_zip

_FONT_ORDER = ["b", "i", "strike", "condense", "extend", "outline", "shadow", "u", "vertAlign",
               "sz", "color", "name", "family", "charset", "scheme"]
_FONT_RANK = {n: i for i, n in enumerate(_FONT_ORDER)}
_FONT_RE = re.compile(r"<font>(.*?)</font>", re.S)
_CHILD_RE = re.compile(r"<(\w+)\b[^>]*?(?:/>|>.*?</\1>)", re.S)
_ROW_RE = re.compile(r"<row ([^>]*?)>(.*?)</row>", re.S)
_CELL_COL_RE = re.compile(r'<c r="([A-Z]{1,3})\d+"')
_INLINE_RE = re.compile(r'<c ([^>]*?)t="inlineStr"([^>]*)><is>(.*?)</is></c>', re.S)

SST_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings"
SST_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _add_spans(m: re.Match) -> str:
    """Excel writes spans="first:last" on every row as a loading hint; openpyxl does not."""
    attrs, body = m.group(1), m.group(2)
    cols = _CELL_COL_RE.findall(body)
    if not cols or "spans=" in attrs:
        return m.group(0)
    return f'<row {attrs} spans="{_col_index(cols[0])}:{_col_index(cols[-1])}">{body}</row>'


def _sort_font(m: re.Match) -> str:
    children = [(c.group(1), c.group(0)) for c in _CHILD_RE.finditer(m.group(1))]
    children.sort(key=lambda nc: _FONT_RANK.get(nc[0], len(_FONT_RANK)))
    return "<font>" + "".join(x for _n, x in children) + "</font>"


class _SharedStrings:
    def __init__(self):
        self.index = {}
        self.items = []
        self.count = 0

    def ref(self, inner: str) -> int:
        self.count += 1
        i = self.index.get(inner)
        if i is None:
            i = self.index[inner] = len(self.items)
            self.items.append(inner)
        return i

    def convert(self, sheet_xml: str) -> str:
        def sub(m):
            return f'<c {m.group(1)}t="s"{m.group(2)}><v>{self.ref(m.group(3))}</v></c>'
        xml = _INLINE_RE.sub(sub, sheet_xml)
        return xml.replace(' t="n"></c>', "/>")   # empty styled cells, written the way Excel does

    def xml(self) -> bytes:
        body = "".join(f"<si>{s}</si>" for s in self.items)
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<sst xmlns="{MAIN_NS}" count="{self.count}" uniqueCount="{len(self.items)}">'
                f"{body}</sst>").encode("utf-8")


MAX_AUTO_WIDTH = 60


def text_width(text: str, font) -> float:
    """Approximate Excel column width needed to show text on one line."""
    sz = float(font.sz or 11)
    mono = (font.name or "").lower() in ("courier new", "courier", "consolas", "lucida console")
    em = 0.60 if mono else 0.55
    if font.b and not mono:
        em += 0.04
    px = len(text) * em * sz * 96 / 72
    return px / 7.0 + 1.5


def col_dim(ws, c: int):
    """Column dimension for column c, splitting a grouped <col min..max> range if needed
    (two overlapping column definitions make Excel repair the file)."""
    from copy import copy
    from openpyxl.utils import get_column_letter
    for dim in list(ws.column_dimensions.values()):
        if dim.min and dim.max and dim.min <= c <= dim.max:
            if dim.min == dim.max:
                return dim
            for i in range(dim.min, dim.max + 1):
                nd = copy(dim)
                nd.index = get_column_letter(i)
                nd.min = nd.max = i
                ws.column_dimensions[nd.index] = nd
            return ws.column_dimensions[get_column_letter(c)]
    return ws.column_dimensions[get_column_letter(c)]


def fit_column(ws, c: int, cells):
    """Widen column c (never narrow it, and not past MAX_AUTO_WIDTH unless it already is) so the text of
    `cells` shows in full on one line - e.g. a longer DAYS code after variants were merged."""
    from .model import cell_text
    need = max((text_width(cell_text(cell.value), cell.font) for cell in cells if cell.value not in (None, "")),
               default=0)
    if not need:
        return
    dim = col_dim(ws, c)
    cur = dim.width if dim.width else 8.43
    if need > cur:
        dim.width = min(round(need, 1), max(cur, MAX_AUTO_WIDTH))


def data_extent(ws):
    """(last row, last column) holding anything: a value, merged cells, a link, a comment or a drop-down."""
    rows = cols = 0
    for (r, c), cell in ws._cells.items():
        v = cell._value
        if (v is not None and v != "") or getattr(cell, "_hyperlink", None) is not None \
                or getattr(cell, "_comment", None) is not None:
            if r > rows:
                rows = r
            if c > cols:
                cols = c
    ranges = list(ws.merged_cells.ranges)
    for dv in ws.data_validations.dataValidation:
        ranges += list(dv.sqref.ranges)
    for rng in ranges:
        rows, cols = max(rows, rng.max_row), max(cols, rng.max_col)
    return rows, cols


def _visible(cell_or_dim) -> bool:
    """Formatting that shows on an empty cell: a fill or a border."""
    try:
        fill, border = cell_or_dim.fill, cell_or_dim.border
    except AttributeError:
        return False
    if fill is not None and fill.fill_type not in (None, "none"):
        return True
    return border is not None and any(getattr(border, side) is not None and getattr(border, side).style
                                      for side in ("left", "right", "top", "bottom"))


def trim_unused_formatting(ws, keep_visible: bool = True):
    """Remove formatting outside the data: styled empty cells beyond the last row and column with data, and
    row and column styles (which Excel applies to every one of the row's 16,384 cells / the column's million
    rows). Fills and borders a row or column style showed inside the data are kept on those cells.
    keep_visible: empty cells with a fill or border just past the data (an output's own frame) count as data."""
    from openpyxl.styles.cell_style import StyleArray
    rows, cols = data_extent(ws)
    cells_of = ws._cells
    if keep_visible:
        for (r, c), cell in cells_of.items():
            if (r > rows or c > cols) and cell.has_style and _visible(cell):
                rows, cols = max(rows, r), max(cols, c)
    if not rows or not cols:
        rows = cols = 0
    for key in [k for k in cells_of if k[0] > rows or k[1] > cols]:
        del cells_of[key]
    # row styles: carried onto the row's empty cells inside the data if they show, then removed
    for r in list(ws.row_dimensions):
        dim = ws.row_dimensions[r]
        if r > rows:
            del ws.row_dimensions[r]
            continue
        if dim.has_style:
            if _visible(dim):
                for c in range(1, cols + 1):
                    if (r, c) not in cells_of:
                        ws.cell(row=r, column=c)._style = copy(dim._style)
            dim._style = StyleArray()
    from openpyxl.utils import column_index_from_string
    for key in list(ws.column_dimensions):
        dim = ws.column_dimensions[key]
        lo = dim.min or column_index_from_string(dim.index)
        hi = dim.max or lo
        if lo > cols:
            del ws.column_dimensions[key]
            continue
        if hi > cols:
            dim.max = cols
        if dim.has_style:
            if _visible(dim):
                for c in range(lo, min(hi, cols) + 1):
                    for r in range(1, rows + 1):
                        if (r, c) not in cells_of:
                            ws.cell(row=r, column=c)._style = copy(dim._style)
            dim._style = StyleArray()


def save_workbook(wb, path: str, progress=None, trim: str = "visible"):
    """Save an openpyxl workbook straight into the tidy form Excel opens without complaint.
    openpyxl writes it uncompressed in memory; it is then fixed up and compressed once, on all
    cores (instead of compressing, re-reading and compressing again).
    trim: 'visible' trims formatting outside the data but keeps fills and borders just past it (an output's
    own frame); 'data' trims everything outside the data (a CWN read in, whose formatting can run to the
    end of the sheet); '' trims nothing. progress(fraction) is called as each tab is written."""
    import datetime
    from openpyxl.writer.excel import ExcelWriter
    if trim:
        for ws in wb.worksheets:
            trim_unused_formatting(ws, keep_visible=trim == "visible")
    total = max(len(wb.worksheets), 1)
    done = [0]

    class Writer(ExcelWriter):
        def write_worksheet(self, ws):
            super().write_worksheet(ws)
            done[0] += 1
            if progress:
                progress(0.8 * done[0] / total)
    buf = io.BytesIO()
    archive = zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED, allowZip64=True)
    wb.properties.modified = datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)
    Writer(wb, archive).save()
    with zipfile.ZipFile(buf) as zin:
        write_zip(path, _fixed_parts(zin))
    if progress:
        progress(1.0)


def _fixed_parts(zin: zipfile.ZipFile):
    sst = _SharedStrings()
    names = zin.namelist()
    has_sst = "xl/sharedStrings.xml" in names
    parts = []
    for name in names:
        data = zin.read(name)
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
            xml = data.decode("utf-8")
            if not has_sst:
                xml = sst.convert(xml)
            data = _ROW_RE.sub(_add_spans, xml).encode("utf-8")
        elif name == "xl/styles.xml":
            data = _FONT_RE.sub(_sort_font, data.decode("utf-8")).encode("utf-8")
        elif name == "xl/workbook.xml":
            data = data.replace(b' fullCalcOnLoad="1"', b"")
        elif name == "[Content_Types].xml" and not has_sst:
            data = data.replace(
                b"</Types>",
                f'<Override PartName="/xl/sharedStrings.xml" ContentType="{SST_CT}"/></Types>'.encode())
        elif name == "xl/_rels/workbook.xml.rels" and not has_sst:
            data = data.replace(
                b"</Relationships>",
                f'<Relationship Id="rIdSharedStrings" Type="{SST_TYPE}" '
                f'Target="sharedStrings.xml"/></Relationships>'.encode())
        parts.append((name, data))
    if not has_sst:
        parts.append(("xl/sharedStrings.xml", sst.xml()))
    return parts
