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
"""
from __future__ import annotations

import io
import re
import zipfile

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


def save_workbook(wb, path: str):
    """Save an openpyxl workbook straight into the tidy form Excel opens without complaint.
    openpyxl writes it uncompressed in memory; it is then fixed up and compressed once, on all
    cores (instead of compressing, re-reading and compressing again)."""
    import datetime
    from openpyxl.writer.excel import ExcelWriter
    buf = io.BytesIO()
    archive = zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED, allowZip64=True)
    wb.properties.modified = datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)
    ExcelWriter(wb, archive).save()
    with zipfile.ZipFile(buf) as zin:
        write_zip(path, _fixed_parts(zin))


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
