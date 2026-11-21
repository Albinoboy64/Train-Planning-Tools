"""PDF and Word versions of the app's outputs.

Every output is a list of Sections (a titled table, optionally with highlighted cells), written
to A4 landscape pages with the heading row repeated on each page. Tables too wide for a page are
split into parts, each repeating the identifying columns.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as _escape
import re as _re

from .branding import APP_NAME
from .zipw import write_zip

_BAD_XML = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def escape(text) -> str:
    """Text made safe for Word / PDF markup: &, < and > escaped, and the control characters XML does
    not allow (e.g. a stray character pasted into a spreadsheet cell) dropped, so they can never make
    the document unopenable."""
    return _escape(_BAD_XML.sub("", str(text)))


HEAD_FILL = "99CCFF"
MAX_COLS = 16                       # columns per page part (A4 landscape stays readable)


@dataclass
class Section:
    title: str
    headers: List[str]
    rows: List[List[str]]
    fills: Dict[Tuple[int, int], str] = field(default_factory=dict)   # (row, col or -1) -> 'RRGGBB'
    bold_rows: set = field(default_factory=set)
    note: str = ""
    key_cols: int = 1               # columns repeated when a wide table is split
    strike_rows: set = field(default_factory=set)


def _cell(v) -> str:
    return "" if v is None else str(v)


def split_wide(sec: Section, max_cols: int = MAX_COLS) -> List[Section]:
    """A table wider than a page becomes several, each repeating the key columns."""
    n = len(sec.headers)
    if n <= max_cols:
        return [sec]
    keys = list(range(min(sec.key_cols, max_cols - 1)))
    rest = [c for c in range(n) if c not in keys]
    step = max_cols - len(keys)
    chunks = [rest[i:i + step] for i in range(0, len(rest), step)]
    out = []
    for k, chunk in enumerate(chunks, start=1):
        cols = keys + chunk
        pos = {c: i for i, c in enumerate(cols)}
        fills = {}
        for (r, c), colour in sec.fills.items():
            if c == -1:
                fills[(r, -1)] = colour
            elif c in pos:
                fills[(r, pos[c])] = colour
        out.append(Section(f"{sec.title} (part {k} of {len(chunks)})", [sec.headers[c] for c in cols],
                           [[row[c] if c < len(row) else "" for c in cols] for row in sec.rows], fills,
                           set(sec.bold_rows), sec.note if k == 1 else "", len(keys), set(sec.strike_rows)))
    return out


# --------------------------------------------------------------------------- #
# Word (.docx) - written directly (WordprocessingML)
# --------------------------------------------------------------------------- #
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_STYLES = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles xmlns:w="{W}">'
           '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
           '<w:sz w:val="16"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="0"/></w:pPr>'
           '</w:pPrDefault></w:docDefaults>'
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
           '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
           '<w:pPr><w:spacing w:after="120"/></w:pPr><w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="36"/></w:rPr>'
           '</w:style>'
           '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
           '<w:pPr><w:keepNext/><w:spacing w:before="120" w:after="80"/><w:outlineLvl w:val="0"/></w:pPr>'
           '<w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="26"/></w:rPr></w:style>'
           '<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/>'
           '<w:pPr><w:spacing w:after="80"/></w:pPr><w:rPr><w:i/><w:color w:val="595959"/></w:rPr></w:style>'
           '<w:style w:type="table" w:styleId="Grid"><w:name w:val="Grid"/><w:tblPr><w:tblBorders>'
           + "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>'
                     for b in ("top", "left", "bottom", "right", "insideH", "insideV")) +
           '</w:tblBorders><w:tblCellMar><w:left w:w="57" w:type="dxa"/><w:right w:w="57" w:type="dxa"/>'
           '</w:tblCellMar></w:tblPr></w:style></w:styles>')


def _para(text: str, style: str = "", page_break: bool = False) -> str:
    inner = ('<w:pStyle w:val="%s"/>' % style if style else "") + ("<w:pageBreakBefore/>" if page_break else "")
    ppr = f"<w:pPr>{inner}</w:pPr>" if inner else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def column_weights(sec: Section) -> List[float]:
    """Relative column widths from the longest text in each (headings count less - they wrap)."""
    n = len(sec.headers)
    want = [max([len(sec.headers[c]) * 0.6] + [len(_cell(r[c])) for r in sec.rows[:2000] if c < len(r)]) + 2
            for c in range(n)]
    want = [min(w, 60) for w in want]
    total = sum(want) or 1
    return [w / total for w in want]


PAGE_TWIPS = 16838 - 2 * 567           # A4 landscape less the margins


def _docx_table(sec: Section) -> str:
    widths = [max(int(PAGE_TWIPS * w), 300) for w in column_weights(sec)]

    def cell(c, text, fill=None, bold=False, strike=False):
        shade = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
        rpr = ("<w:b/>" if bold else "") + ("<w:strike/>" if strike else "")
        return (f'<w:tc><w:tcPr><w:tcW w:w="{widths[c]}" w:type="dxa"/>{shade}</w:tcPr><w:p><w:r>'
                f'{f"<w:rPr>{rpr}</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
                "</w:tc>")
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="Grid"/>'
           f'<w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>'
           + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>",
           '<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>'
           + "".join(cell(c, h, HEAD_FILL, True) for c, h in enumerate(sec.headers)) + "</w:tr>"]
    for r, row in enumerate(sec.rows):
        row_fill = sec.fills.get((r, -1))
        bold, strike = r in sec.bold_rows, r in sec.strike_rows
        cells = [cell(c, _cell(v), sec.fills.get((r, c), row_fill), bold, strike)
                 for c, v in enumerate(row[:len(widths)])]
        cells += [cell(c, "") for c in range(len(row), len(sec.headers))]
        out.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>' + "".join(cells) + "</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def write_docx(path: str, title: str, sections: Sequence[Section]):
    from .zipw import Deflated
    doc = Deflated()                    # compressed section by section: never the whole document in memory
    doc.write(f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{W}"><w:body>')
    doc.write(_para(title, "Title") + _para(f"Created {_dt.datetime.now():%d/%m/%Y %H:%M} by {APP_NAME}", "Note"))
    first = True
    for sec in sections:
        for part in split_wide(sec):
            doc.write(_para(part.title, "Heading1", page_break=not first))
            first = False
            if part.note:
                doc.write(_para(part.note, "Note"))
            if part.headers:
                doc.write(_docx_table(part))
    doc.write('<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
              '<w:pgMar w:top="567" w:right="567" w:bottom="567" w:left="567" w:header="284" w:footer="284" '
              'w:gutter="0"/></w:sectPr></w:body></w:document>')
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006"
    main = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    write_zip(path, [
        ("[Content_Types].xml", (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="{pkg}/'
                                 'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
                                 'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                                 f'<Override PartName="/word/document.xml" ContentType="{main}.document.main+xml"/>'
                                 f'<Override PartName="/word/styles.xml" ContentType="{main}.styles+xml"/>'
                                 '</Types>').encode()),
        ("_rels/.rels", (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{pkg}/'
                         f'relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" '
                         'Target="word/document.xml"/></Relationships>').encode()),
        ("word/_rels/document.xml.rels", (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships '
                                          f'xmlns="{pkg}/relationships"><Relationship Id="rId1" Type="{rel}/styles" '
                                          'Target="styles.xml"/></Relationships>').encode()),
        ("word/document.xml", doc.close()),
        ("word/styles.xml", _STYLES.encode("utf-8")),
    ])


# --------------------------------------------------------------------------- #
# PDF (reportlab)
# --------------------------------------------------------------------------- #
def write_pdf(path: str, title: str, sections: Sequence[Section]):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    page = landscape(A4)
    margin = 10 * mm
    width = page[0] - 2 * margin
    h_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, leading=20,
                             textColor=colors.HexColor("#1F3864"), spaceAfter=4)
    h_sec = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12, leading=15,
                           textColor=colors.HexColor("#1F3864"), spaceAfter=3)
    note = ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8, leading=10,
                          textColor=colors.HexColor("#595959"), spaceAfter=4)
    stamp = f"Created {_dt.datetime.now():%d/%m/%Y %H:%M} by {APP_NAME}"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#7F7F7F"))
        canvas.drawString(margin, 6 * mm, title)
        canvas.drawRightString(page[0] - margin, 6 * mm, f"Page {doc.page}")
        canvas.restoreState()

    story = [Paragraph(escape(title), h_title), Paragraph(escape(stamp), note)]
    first = True
    for sec in sections:
        for part in split_wide(sec):
            if not first:
                story.append(PageBreak())
            first = False
            story.append(Paragraph(escape(part.title), h_sec))
            if part.note:
                story.append(Paragraph(escape(part.note), note))
            if part.headers:
                story.append(_Deferred(lambda part=part: _pdf_table(part, width, colors, LongTable, TableStyle,
                                                                     Paragraph, ParagraphStyle)))
            story.append(Spacer(1, 4))
    from .fsutil import atomic_path
    with atomic_path(path) as tmp:              # the PDF replaces an older one only once complete
        SimpleDocTemplate(tmp, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=margin,
                          bottomMargin=12 * mm, title=title, author=APP_NAME).build(
            story, onFirstPage=footer, onLaterPages=footer)


def _deferred_class():
    from reportlab.platypus import Flowable

    class Deferred(Flowable):
        """A table built only when the page layout reaches it (and dropped once drawn), so a document of
        thousands of pages never holds every table's cells and cell styles in memory at once."""

        def __init__(self, make):
            super().__init__()
            self._make, self._table = make, None

        def _real(self):
            if self._table is None:
                self._table = self._make()
            return self._table

        def wrap(self, availWidth, availHeight):
            return self._real().wrap(availWidth, availHeight)

        def split(self, availWidth, availHeight):
            return self._real().split(availWidth, availHeight)

        def drawOn(self, canvas, x, y, _sW=0):
            return self._real().drawOn(canvas, x, y, _sW)
    return Deferred


def _Deferred(make):
    global _DEFERRED
    if _DEFERRED is None:
        _DEFERRED = _deferred_class()
    return _DEFERRED(make)


_DEFERRED = None


def _pdf_table(sec: Section, width: float, colors, LongTable, TableStyle, Paragraph, ParagraphStyle):
    ncols = len(sec.headers)
    size = 7 if ncols <= 10 else 6
    cell_style = ParagraphStyle("c", fontName="Helvetica", fontSize=size, leading=size + 1.5)
    head_style = ParagraphStyle("hc", parent=cell_style, fontName="Helvetica-Bold")
    rows = [[_cell(v) for v in row] + [""] * (ncols - len(row)) for row in sec.rows]
    widths = [w * width for w in column_weights(sec)]
    wrap_at = [w / (size * 0.5) for w in widths]          # roughly how many characters fit

    def para(text, c, style):
        return Paragraph(escape(text), style) if len(text) > wrap_at[c] else text
    data = [[Paragraph(escape(h), head_style) for h in sec.headers]]
    data += [[para(v, c, cell_style) for c, v in enumerate(r)] for r in rows]
    cmds = [("FONT", (0, 0), (-1, -1), "Helvetica", size), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#A6A6A6")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + HEAD_FILL)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    for (r, c), colour in sec.fills.items():
        start, end = ((0, r + 1), (-1, r + 1)) if c == -1 else ((c, r + 1), (c, r + 1))
        cmds.append(("BACKGROUND", start, end, colors.HexColor("#" + colour)))
    for r in sec.bold_rows:
        cmds.append(("FONT", (0, r + 1), (-1, r + 1), "Helvetica-Bold", size))
    table = LongTable(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(cmds))
    # every row's height worked out once and given to the table: otherwise each page split works out the
    # heights of all the rows still to come again (minutes for a stats pack of thousands of pages)
    table.wrap(width, 1e12)
    heights = list(getattr(table, "_rowHeights", None) or [])
    if len(heights) == len(data) and None not in heights:
        table = LongTable(data, colWidths=widths, rowHeights=heights, repeatRows=1)
        table.setStyle(TableStyle(cmds))
    return table


def sections_from_workbook(wb) -> List[Section]:
    """Sections from an openpyxl workbook: each block of rows (split by blank rows) becomes a table,
    a one-cell row above it becomes its heading, and solid cell fills are kept."""
    out: List[Section] = []
    for ws in wb.worksheets:
        heading = ws.title
        block: List[tuple] = []

        def flush(heading, block):
            if block:
                head, *body = block
                width = max(len(r) for r, _f in block)
                out.append(Section(heading, [_cell(v) for v in head[0]] + [""] * (width - len(head[0])),
                                   [[_cell(v) for v in r] for r, _f in body],
                                   {(ri, ci): f for ri, (_r, fills) in enumerate(body) for ci, f in fills.items()}))
                block.clear()
        for row in ws.iter_rows():
            values = [c.value for c in row]
            while values and values[-1] in (None, ""):
                values.pop()
            if not values:
                flush(heading, block)
                continue
            filled = [v for v in values if v not in (None, "")]
            if len(filled) == 1 and values[0] not in (None, "") and not block:
                heading = f"{ws.title} - {values[0]}" if values[0] != ws.title else ws.title
                continue
            fills = {}
            for ci, c in enumerate(row[:len(values)]):
                f = c.fill
                if f is not None and f.fill_type == "solid" and isinstance(f.fgColor.rgb, str):
                    fills[ci] = f.fgColor.rgb[-6:]
            block.append((values, fills))
        flush(heading, block)
    return out


def write_document(path: str, title: str, sections: Sequence[Section]):
    (write_pdf if path.lower().endswith(".pdf") else write_docx)(path, title, sections)


def ext_for(fmt: Optional[str]) -> str:
    return {"pdf": ".pdf", "docx": ".docx"}.get(fmt or "", ".xlsx")
