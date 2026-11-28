"""Telling what kind of timetable file was chosen or dropped, quickly (the Timing Tools tab puts each file in the
box that takes it): a Section 4 PDF from its first page, a Network Rail or GTR timetable workbook from its sheet
names."""
from __future__ import annotations

import re


def is_section4(path: str) -> bool:
    """A Section 4 (Engineering Access Statement) PDF, judged from its first page."""
    if not path.lower().endswith(".pdf"):
        return False
    try:                                    # pypdf (pure Python): PDFium only ever runs in helper processes
        from pypdf import PdfReader

        from rstools import limits
        limits.check_pdf(path)
        reader = PdfReader(path)
        text = reader.pages[0].extract_text() if len(reader.pages) else ""
    except Exception:
        return False
    return "Engineering Access Statement" in text and "Section 4" in text


def sheet_names(path: str) -> list[str]:
    """The workbook's sheet names, in order, read from its index part alone - the same names openpyxl
    gives, without loading the shared strings and styles (a big workbook took up to half a second)."""
    import zipfile
    from rstools import safexml
    from rstools.fsutil import check_zip
    with zipfile.ZipFile(path) as z:
        check_zip(z, "xl/workbook.xml")     # refuse a 'zip bomb' before unpacking
        root = safexml.fromstring(z.read("xl/workbook.xml"), "xl/workbook.xml")
    return [el.get("name") or "" for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "sheet"]


def sniff_timetable(path: str) -> str:
    """'nr' for a Network Rail timetable table, 'gtr' for a GTR timetable check workbook, '' otherwise
    (judged from the sheet names, which is quick)."""
    try:
        names = sheet_names(path)
    except Exception:
        return ""
    if any(re.search(r"notes$", n, re.I) or re.match(r"^(OUT|RTN)_", n) for n in names):
        return "nr"
    if any(re.search(r"\b(OUT|RTN)\s+(SX|SO|SUO|SU)\b", n, re.I) for n in names):
        return "gtr"
    return ""
