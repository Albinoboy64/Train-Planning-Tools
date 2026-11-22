"""Small, fast .xlsx writer for the stats pack.

The workbook is written directly as XML (no spreadsheet library) in the same plain style
as the TRACS-RS stats pack: no formulas, no hyperlinks, a shared-string table and a
handful of cell styles - so it is quick to write and quick for Excel to open.
"""
from __future__ import annotations

import json
import math
import os
import re
from functools import cache
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from rstools.zipw import write_zip

from .stats import Clock, Dur, Row, Table

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_layout() -> Dict[str, dict]:
    """The TRACS-RS layout of each tab. Cell styles are stored once in a shared list and referred
    to as {"$": n}; they are put back as shared dicts (so equal styles are the same object)."""
    with open(os.path.join(HERE, "layout.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    styles = data["styles"]

    def expand(o):
        if isinstance(o, dict):
            return styles[o["$"]] if "$" in o else {k: expand(v) for k, v in o.items()}
        if isinstance(o, list):
            return [expand(v) for v in o]
        return o
    return {s["name"]: s for s in expand(data["sheets"])}


LAYOUT = _load_layout()

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006"
OOXML = "application/vnd.openxmlformats-officedocument.spreadsheetml"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

MAX_CELL_TEXT = 32767                     # longest text Excel allows in one cell
HIGHLIGHT = {"changed": "FFFFD966", "added": "FFC6EFCE", "removed": "FFFFC7CE",
             "flagged": "FFFF7C7C"}     # mileage increase over the comparison threshold


@cache
def col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def fmt_clock(v: int) -> str:
    return "%02d:%02d:%02d" % (v // 3600, v % 3600 // 60, v % 60)


def fmt_dur(v: int) -> str:
    sign = "-" if v < 0 else ""
    v = abs(v)
    return "%s%d:%02d:%02d" % (sign, v // 3600, v % 3600 // 60, v % 60)


_DEFAULT_STYLE = {"sz": 13.0}


class Styles:
    """Deduplicated cell formats built from layout style descriptions."""

    def __init__(self):
        self.fonts: List[tuple] = [(11.0, False, False)]
        self.fills: List[Optional[str]] = [None, "gray125"]
        self.borders: List[tuple] = [()]
        self.xfs: List[tuple] = [(0, 0, 0, 0, None, None, False)]
        self._xf_index: Dict[tuple, int] = {self.xfs[0]: 0}
        self._cache: Dict[tuple, tuple] = {}

    def _idx(self, lst, item):
        if item not in lst:
            lst.append(item)
        return lst.index(item)

    def xf(self, st: Optional[dict], fill: Optional[str] = None, strike: bool = False) -> int:
        # style dicts come from the (long-lived) layout, so cache by identity
        ck = (id(st), fill, strike)
        hit = self._cache.get(ck)
        if hit is not None and hit[0] is st:
            return hit[1]
        i = self._make_xf(st if st is not None else _DEFAULT_STYLE, fill, strike)
        self._cache[ck] = (st, i)
        return i

    def _make_xf(self, st: dict, fill: Optional[str], strike: bool) -> int:
        font = self._idx(self.fonts, (float(st.get("sz", 11)), bool(st.get("b")), strike))
        fl = fill or st.get("fill")
        fill_i = self._idx(self.fills, fl) if fl else 0
        border = tuple(sorted((st.get("border") or {}).items()))
        border_i = self._idx(self.borders, border)
        key = (font, fill_i, border_i, int(st.get("numFmt") or 0), st.get("h"), st.get("v"), bool(st.get("wrap")))
        if key not in self._xf_index:
            self._xf_index[key] = len(self.xfs)
            self.xfs.append(key)
        return self._xf_index[key]

    def xml(self) -> str:
        fonts = "".join(f'<font>{"<b/>" if b else ""}{"<strike/>" if s else ""}<sz val="{sz:g}"/>'
                        f'<color rgb="FF000000"/><name val="Calibri"/></font>' for sz, b, s in self.fonts)
        fills = []
        for f in self.fills:
            if f is None:
                fills.append('<fill><patternFill patternType="none"/></fill>')
            elif f == "gray125":
                fills.append('<fill><patternFill patternType="gray125"/></fill>')
            else:
                fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="{f}"/><bgColor indexed="64"/>'
                             f'</patternFill></fill>')
        borders = []
        for b in self.borders:
            d = dict(b)
            parts = "".join(f'<{side} style="{d[side]}"><color auto="1"/></{side}>' if side in d else f"<{side}/>"
                            for side in ("left", "right", "top", "bottom"))
            borders.append(f"<border>{parts}<diagonal/></border>")
        xfs = []
        for font, fill, border, numfmt, h, v, wrap in self.xfs:
            attrs = f'numFmtId="{numfmt}" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0"'
            if font:
                attrs += ' applyFont="1"'
            if fill:
                attrs += ' applyFill="1"'
            if border:
                attrs += ' applyBorder="1"'
            if numfmt:
                attrs += ' applyNumberFormat="1"'
            al = ""
            if h or v or wrap:
                attrs += ' applyAlignment="1"'
                al = "<alignment" + (f' horizontal="{h}"' if h else "") + (f' vertical="{v}"' if v else "") + \
                     (' wrapText="1"' if wrap else "") + "/>"
            xfs.append(f"<xf {attrs}>{al}</xf>" if al else f"<xf {attrs}/>")
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="{MAIN}">'
                f'<fonts count="{len(self.fonts)}">{fonts}</fonts><fills count="{len(fills)}">{"".join(fills)}</fills>'
                f'<borders count="{len(borders)}">{"".join(borders)}</borders>'
                f'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
                f'<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                f'</styleSheet>')


class SharedStrings:
    def __init__(self):
        self.index: Dict[str, int] = {}
        self.count = 0

    def get(self, s: str) -> int:
        self.count += 1
        i = self.index.get(s)
        if i is None:
            i = self.index[s] = len(self.index)
        return i

    def xml(self) -> str:
        items = "".join(f'<si><t xml:space="preserve">{escape(_BAD_XML.sub("", s))}</t></si>' for s in self.index)
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="{MAIN}" '
                f'count="{self.count}" uniqueCount="{len(self.index)}">{items}</sst>')


class SheetWriter:
    def __init__(self, sst: SharedStrings, styles: Styles):
        self.sst, self.styles = sst, styles
        self.rows: List[str] = []
        self.r = 0
        self.widths: Dict[int, int] = {}      # column -> characters shown, once measure() is on
        self._measure = False

    def measure(self):
        """From the next row on, record the longest value shown in each column (for its width)."""
        self._measure = True
        self.widths = {}

    def row(self, cells: Sequence[Tuple[int, Any, int]], height: Optional[float] = None):
        """cells: (column number, value, style index), in column order. Hot path: written once
        per row of every tab, so it avoids per-cell helper calls."""
        self.r += 1
        r = str(self.r)
        sst = self.sst.get
        widths = self.widths if self._measure else None
        parts: List[str] = []
        add = parts.append
        for c, v, s in cells:
            ref = col_letter(c) + r
            t = type(v)
            if t is str:
                if not v:
                    add(f'<c r="{ref}" s="{s}"/>')
                    continue
                text = v if len(v) <= MAX_CELL_TEXT else v[:MAX_CELL_TEXT]   # Excel's limit per cell
            elif v is None:
                add(f'<c r="{ref}" s="{s}"/>')
                continue
            elif t is int:
                text = str(v)
                add(f'<c r="{ref}" s="{s}"><v>{text}</v></c>')
                if widths is not None:
                    n = len(text) + (len(text) - 1) // 3
                    if n > widths.get(c, 0):
                        widths[c] = n
                continue
            elif t is float and not math.isfinite(v):
                text = "???"                                   # Excel cannot store inf / nan
            elif t is float:
                add(f'<c r="{ref}" s="{s}"><v>{round(v, 6)!r}</v></c>')
                if widths is not None:
                    n = len(f"{v:,.2f}")
                    if n > widths.get(c, 0):
                        widths[c] = n
                continue
            elif t is bool:
                add(f'<c r="{ref}" s="{s}" t="b"><v>{int(v)}</v></c>')
                continue
            elif t is Clock:
                text = fmt_clock(v)
            elif t is Dur:
                text = fmt_dur(v)
            else:
                text = str(v)
            add(f'<c r="{ref}" s="{s}" t="s"><v>{sst(text)}</v></c>')
            if widths is not None and len(text) > widths.get(c, 0):
                widths[c] = len(text)
        first = cells[0][0] if cells else 1
        last = max(cells[-1][0], first) if cells else 1
        ht = f' ht="{height}" customHeight="1"' if height else ""
        self.rows.append(f'<row r="{r}" spans="{first}:{last}"{ht}>{"".join(parts)}</row>')

    def xml(self, cols: List[Tuple[int, int, float]], merges: List[str]) -> str:
        col_xml = "".join(f'<col min="{a}" max="{b}" width="{w}" customWidth="1"/>' for a, b, w in cols)
        merge_xml = (f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges)
                     + "</mergeCells>") if merges else ""
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{MAIN}">'
                f'<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
                + (f"<cols>{col_xml}</cols>" if cols else "")
                + f'<sheetData>{"".join(self.rows)}</sheetData>{merge_xml}'
                f'<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
                f'<pageSetup paperSize="9" fitToWidth="1" fitToHeight="0" orientation="portrait"/></worksheet>')


class Workbook:
    def __init__(self):
        self.sst = SharedStrings()
        self.styles = Styles()
        self.sheets: List[Tuple[str, str]] = []

    def new_sheet(self) -> SheetWriter:
        return SheetWriter(self.sst, self.styles)

    def add(self, name: str, writer: SheetWriter, cols, merges):
        if any(n.lower() == name.lower() for n, _x in self.sheets):
            raise ValueError(f"Duplicate sheet name {name!r}")
        self.sheets.append((name, writer.xml(cols, merges)))

    def save(self, path: str):
        """Write the workbook (parts compressed on all cores; replaced only once complete)."""
        write_zip(path, self._parts())

    def _parts(self) -> List[Tuple[str, bytes]]:
        n = len(self.sheets)
        sheets = "".join(f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                         for i, (name, _x) in enumerate(self.sheets, start=1))
        ct = (f'{XML_HEAD}<Types xmlns="{PKG}/content-types">'
              f'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              f'<Override PartName="/xl/workbook.xml" ContentType="{OOXML}.sheet.main+xml"/>'
              f'<Override PartName="/xl/styles.xml" ContentType="{OOXML}.styles+xml"/>'
              f'<Override PartName="/xl/sharedStrings.xml" ContentType="{OOXML}.sharedStrings+xml"/>'
              + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{OOXML}.worksheet+xml"/>'
                        for i in range(1, n + 1)) + "</Types>")
        rels = "".join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                       for i in range(1, n + 1))
        rels += (f'<Relationship Id="rId{n + 1}" Type="{REL}/styles" Target="styles.xml"/>'
                 f'<Relationship Id="rId{n + 2}" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>')
        parts = [
            ("[Content_Types].xml", ct),
            ("_rels/.rels", f'{XML_HEAD}<Relationships xmlns="{PKG}/relationships">'
                            f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/>'
                            "</Relationships>"),
            ("xl/workbook.xml", f'{XML_HEAD}<workbook xmlns="{MAIN}" xmlns:r="{REL}">'
                                f'<bookViews><workbookView activeTab="0"/></bookViews>'
                                f'<sheets>{sheets}</sheets></workbook>'),
            ("xl/_rels/workbook.xml.rels",
             f'{XML_HEAD}<Relationships xmlns="{PKG}/relationships">{rels}</Relationships>'),
        ]
        parts += [(f"xl/worksheets/sheet{i}.xml", xml) for i, (_n, xml) in enumerate(self.sheets, start=1)]
        parts += [("xl/styles.xml", self.styles.xml()), ("xl/sharedStrings.xml", self.sst.xml())]
        return [(name, text.encode("utf-8")) for name, text in parts]


# --------------------------------------------------------------------------- #
# Stats pack rendering
# --------------------------------------------------------------------------- #
UNKNOWN = "???"


def _style(spec: dict, kind: str, c: int) -> Optional[dict]:
    group = spec["last"] if kind == "last" else spec["body"]
    return group.get(str(c)) or spec["body"].get(str(c))


def render_table(wb: Workbook, sheet_name: str, title: str, table: Table,
                 marks: Optional[Dict[Tuple[int, int], str]] = None, extra_rows: Sequence[Row] = ()):
    """Write one stats pack tab in the TRACS-RS layout.

    marks: {(row index, column index): 'changed'|'added'|'removed'} highlight colours
    (row index into table.rows + extra_rows; column index -1 = whole row)."""
    spec = LAYOUT[table.name]
    st = wb.styles
    sw = wb.new_sheet()
    marks = marks or {}
    shift = 1 if table.has_day else 0
    cols = [(a + shift, b + shift, w) for a, b, w in spec["cols"]]
    if shift:
        cols = [(1, 1, 8.0)] + cols
    merges = [_shift_ref(m, shift) for m in spec["merges"]]

    if table.name == "Glossary":
        _render_glossary(wb, sw, spec, table)
        labels = [a for a, _b in spec["text"] if a] + ["Created (version)", str(table.rows[0].cells[0])]
        wb.add(sheet_name, sw, fit_columns(cols, [max(len(x) for x in labels)], [13.0]), merges)
        return
    sw.row([(1, title, st.xf(spec["title"][0][2]))])
    for i, hdr in enumerate(spec["header"]):
        cells = [(c + shift, v, st.xf(s)) for c, v, s in hdr]
        if shift:
            cells = [(1, "Day" if i == len(spec["header"]) - 1 else None, st.xf(hdr[0][2]))] + cells
        if table.side and i == 0:
            cells += [(c + shift, v, st.xf(s)) for c, v, s in spec["side"]["header"]]
        sw.row(cells)
    all_rows = list(table.rows) + list(extra_rows)
    sw.measure()
    # per-column styles and 'unknown' flags, worked out once per tab rather than per cell;
    # data cells never wrap (each value stays on one line - the columns are widened instead)
    width = max((len(r.cells) for r in all_rows), default=0)
    col_style = {kind: [nowrap(_style(spec, kind, max(ci + 1 - shift, 1))) for ci in range(width)]
                 for kind in ("body", "last")}
    col_xf = {kind: [st.xf(x) for x in styles] for kind, styles in col_style.items()}
    unknown_ok = [ci >= table.key_cols and _is_measure(table, ci - shift) for ci in range(width)]
    n_rows = len(all_rows)
    for ri, row in enumerate(all_rows):
        kind = "last" if ri == n_rows - 1 or row.kind == "total" else "body"
        xfs = col_xf[kind]
        row_mark = marks.get((ri, -1)) if marks else None
        cells = []
        for ci, v in enumerate(row.cells):
            if v is None and unknown_ok[ci]:
                v = UNKNOWN
            mark = (marks.get((ri, ci)) or row_mark) if marks else None
            if mark:
                s_ = st.xf(col_style[kind][ci], fill=HIGHLIGHT.get(mark), strike=mark == "removed")
            else:
                s_ = xfs[ci]
            cells.append((ci + 1, v, s_))
        if table.side and ri == 0:
            for (c, v), s in zip(enumerate(table.side, start=11), ("11", "12")):
                cells.append((c + shift, v, st.xf(spec["side"]["values"][s])))
        sw.row(cells)
    if table.side and not all_rows:
        sw.row([(11 + shift, table.side[0], st.xf(spec["side"]["values"]["11"])),
                (12 + shift, table.side[1], st.xf(spec["side"]["values"]["12"]))])
    widths = [sw.widths.get(ci + 1, 0) for ci in range(width)]
    for hdr in spec["header"]:                 # a heading word is never broken across lines
        for c, v, _s in hdr:
            if v:
                ci = c + shift - 1
                if ci < width:
                    widths[ci] = max(widths[ci], max(len(w) for w in str(v).split()))
    wb.add(sheet_name, sw, fit_columns(cols, widths, sizes=[font_size(col_style["body"][ci]) for ci in range(width)]),
           merges)


_NOWRAP_CACHE: Dict[int, tuple] = {}


def nowrap(st: Optional[dict]) -> Optional[dict]:
    """The layout style without text wrapping (cached, so cell formats stay shared)."""
    if not st or not st.get("wrap"):
        return st
    hit = _NOWRAP_CACHE.get(id(st))
    if hit is None or hit[0] is not st:
        hit = _NOWRAP_CACHE[id(st)] = (st, dict(st, wrap=False))
    return hit[1]


def font_size(st: Optional[dict]) -> float:
    return float((st or _DEFAULT_STYLE).get("sz", 11))


def fit_columns(cols: List[Tuple[int, int, float]], chars: Sequence[int],
                sizes: Optional[Sequence[float]] = None, cap: float = 255.0) -> List[Tuple[int, int, float]]:
    """Column widths wide enough for the longest value in each column (never narrower than the
    layout).  Widths are in Excel character units for 11pt Calibri, so larger fonts scale up."""
    base: Dict[int, float] = {}
    for a, b, w in cols:
        for c in range(a, b + 1):
            base[c] = w
    for ci, n in enumerate(chars):
        if n:
            scale = (sizes[ci] if sizes else 11.0) / 11.0
            need = min(cap, round(n * 1.1 * scale + 2, 1))
            base[ci + 1] = max(base.get(ci + 1, 0), need)
    out: List[Tuple[int, int, float]] = []
    for c in sorted(base):
        if out and out[-1][1] == c - 1 and out[-1][2] == base[c]:
            out[-1] = (out[-1][0], c, base[c])
        else:
            out.append((c, c, base[c]))
    return out


MEASURE_COLS = {
    "Service Miles": {8},
    "Diagram Summary": {9, 11},
    "Formation Data": {13},
    "Diagram Data": {13},
}


def _is_measure(table: Table, ci: int) -> bool:
    if table.name in MEASURE_COLS:
        return ci in MEASURE_COLS[table.name]
    return table.name not in ("Fleet", "Calling Pattern (stops+passes)", "Calling Pattern (stops only)")


def _shift_ref(ref: str, shift: int) -> str:
    if not shift:
        return ref

    def mv(m):
        col = 0
        for ch in m.group(1):
            col = col * 26 + ord(ch) - 64
        return f"{col_letter(col + shift)}{m.group(2)}"
    return re.sub(r"([A-Z]+)(\d+)", mv, ref)


def _render_glossary(wb: Workbook, sw: SheetWriter, spec: dict, table: Table):
    st = wb.styles
    s = spec["styles"]
    sw.row([(1, None, st.xf(spec["title"][0][2]))])
    sw.row([(1, "Created (version)", st.xf(s["r2"][0])), (2, "Rolling Stock Input File", st.xf(s["r2"][1]))])
    created, inputs = table.rows[0].cells
    for k, line in enumerate(str(inputs).split("\n") or [""]):    # one input file per row
        sw.row([(1, created if k == 0 else None, st.xf(s["r3"][0])), (2, line, st.xf(s["r3"][1]))])
    for a, b in spec["text"]:
        if a is None and b is None:
            sw.row([(1, None, st.xf(s["blank"][0])), (2, None, st.xf(s["blank"][1]))])
        elif b is None:
            sw.row([(1, a, st.xf(s["section"][0])), (2, None, st.xf(s["section"][1]))])
        else:
            sw.row([(1, a, st.xf(s["item"][0])), (2, b, st.xf(s["item"][1]))])


def render_report(wb: Workbook, name: str, title: str, headers: Sequence[str], rows: Sequence[Sequence],
                  kinds: Sequence[str] = (), note: str = ""):
    """A plain report tab in the stats pack's look: title, optional note, heading row, rows
    (total rows in the stats pack's 'last row' style); columns sized to fit."""
    spec = LAYOUT["Service Miles"]
    st = wb.styles
    sw = wb.new_sheet()
    head = st.xf(spec["header"][0][1][2])
    body = st.xf(nowrap(spec["body"]["2"]))
    last = st.xf(nowrap(spec["last"]["2"]))
    sw.row([(1, title, st.xf(spec["title"][0][2]))])
    if note:
        sw.row([(1, note, st.xf(nowrap(spec["body"]["2"])))])
    sw.row([(i, h, head) for i, h in enumerate(headers, start=1)])
    sw.measure()
    for r, row in enumerate(rows):
        style = last if (kinds and r < len(kinds) and kinds[r] == "total") else body
        sw.row([(i, v, style) for i, v in enumerate(row, start=1)])
    if not rows:                                       # an empty tab says so rather than looking broken
        sw.row([(1, "None", body)])
    widths = [max(sw.widths.get(i + 1, 0), max((len(w) for w in str(h).split()), default=0))
              for i, h in enumerate(headers)]
    wb.add(name[:31], sw, fit_columns([(1, len(headers), 10.0)], widths, [font_size(spec["body"]["2"])] * len(headers)),
           [])
