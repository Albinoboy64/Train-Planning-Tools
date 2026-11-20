"""Write the timetable comparison into a copy of the approved TT Comparison template.

The template's sheets, order, headings, column widths, header style, frozen panes and notes are
kept; results go beneath the headings. Readability improvements on top of the template: thin
borders on result rows, numbers kept as numbers (confidence as a percentage), times kept as
four-digit text, the Result column coloured, 'None identified' on empty sheets, filters covering
every result, and print settings (landscape, fit to width, heading row repeated on each page).
"""
from __future__ import annotations

import copy
import os
from typing import List, Sequence

from .compare import Comparison, service_groups

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.xlsx")
NONE = "None identified"


def _role(role: str) -> str:
    return "Arr" if role == "arr" else "Dep"


def output_name(cmp: Comparison) -> str:
    ident = cmp.nr.identifier or os.path.splitext(os.path.basename(cmp.nr.path))[0][:40]
    return f"{ident} Consolidated TT Comparison"


def build_workbook(cmp: Comparison):
    """The filled template as an openpyxl workbook."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, Side
    from openpyxl.worksheet.properties import PageSetupProperties

    from rstools.fsutil import clean_cell
    wb = openpyxl.load_workbook(TEMPLATE)
    B, O = cmp.base_label, cmp.other_label
    if (B, O) != ("NR", "GTR"):                    # a train print / train list is the reference
        import re
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.value = re.sub(r"\bGTR\b", "\x00", re.sub(r"\bNR\b", B, cell.value)).replace("\x00", O)
    thin = Side(style="thin", color="FFBFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    top = Alignment(vertical="top", wrap_text=True)

    def write(ws, rows: Sequence[Sequence], formats=None, start=2, total=False):
        """Rows under the heading, each cell taking the template's row-2 style (or a plain style)."""
        formats = formats or {}
        template_row = {c.column: c for c in ws[2]} if ws.max_row >= 2 else {}
        if not rows:
            cell = ws.cell(start, 1, NONE)
            cell.font = Font(italic=True, color="FF595959")
            return
        styles = {}                                 # each column's finished style, built once and copied
        for r, row in enumerate(rows, start=start):
            for c, value in enumerate(row, start=1):
                cell = ws.cell(r, c, clean_cell(value))
                if c in styles:
                    cell._style = copy.copy(styles[c])
                    continue
                src = template_row.get(c)
                if src is not None and src.has_style:
                    cell._style = copy.copy(src._style)
                cell.border = border
                cell.alignment = top
                if c in formats:
                    cell.number_format = formats[c]
                styles[c] = copy.copy(cell._style)
        last = start + len(rows) - 1 - (1 if total and len(rows) > 1 else 0)
        ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(ws.max_column)}{last}"

    sections = cmp.sections
    # Summary (one row per section, then an all-sections total)
    ws = wb["Summary"]
    totals = [0] * 7
    for r in range(2, 8):
        name = ws.cell(r, 1).value
        res = next((s for s in sections if s.section == name), None)
        if res is None:
            vals = ["-"] * 7 + ["Not in both timetables"]
        else:
            issues = sum(len(m.issues) for m in res.matched)
            counts = [len(res.nr_trains), len(res.gtr_trains), len(res.matched), len(res.missing), len(res.gaps),
                      issues, len(res.headcode_mismatches)]
            totals = [a + b for a, b in zip(totals, counts)]
            vals = counts + ["Differences found" if sum(counts[3:]) else "No differences"]
        _summary_row(ws, r, vals)
    ws.cell(8, 1, "All sections")
    _summary_row(ws, 8, totals + ["Differences found" if sum(totals[3:]) else "No differences"])
    for c in range(1, 10):
        ws.cell(8, c).font = Font(bold=True)
    for r in range(9, 14, 2):                      # the notes (merged, wrapped) need room to show in full
        ws.row_dimensions[r].height = 48
        ws.cell(r, 1).alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(r, 1).font = Font(bold=True)
        ws.cell(r, 2).alignment = Alignment(vertical="top", wrap_text=True)
    # Issues (section order, NR timetable order, station sequence)
    rows = []
    for res in sections:
        for m in res.matched:
            for i in m.issues:
                rows.append([res.section, m.nr.headcode, m.gtr.headcode, m.gtr.days, i.location, _role(i.role),
                             i.nr_time, i.gtr_time or "-", i.summary, i.others, m.confidence])
    write(wb["Issues"], rows, {7: "@", 8: "@", 11: '0.0"%"'})
    # Missing Trains: per section, NR trains missing from GTR then isolated GTR gaps, in timetable order
    rows = []
    for res in sections:
        for direction, trains in ((f"Missing from {O}", [m.nr for m in res.missing]),
                                  (f"Isolated {O} gap in {B}", [gap.gtr for gap in res.gaps])):
            for t in sorted(trains, key=lambda t: t.column):
                rows.append([direction, res.section, t.headcode or t.label(), t.days, t.origin or t.events[0].name,
                             t.destination or t.events[-1].name, len(t.events)])
    write(wb["Missing Trains"], rows)
    # Headcode Mismatches
    rows = []
    for res in sections:
        for m in res.headcode_mismatches:
            finding = (f"All {m.nr_points} timings match; headcode differs ({B} {m.nr.headcode}, {O} {m.gtr.headcode})"
                       if not m.issues else f"Headcode differs ({B} {m.nr.headcode}, {O} {m.gtr.headcode}); "
                       f"{len(m.issues)} timing issue(s) on the Issues sheet")
            rows.append([res.section, m.nr.headcode, m.gtr.headcode, m.gtr.days, finding, m.confidence])
    write(wb["Headcode Mismatches"], rows, {6: '0.0"%"'})
    # Service Group Review
    rows = [[res.section, *row] for res in sections for row in service_groups(res)]
    write(wb["Service Group Review"], rows)
    # Match Audit
    rows = []
    for res in sections:
        for m in res.matches:
            rows.append([res.section, m.nr.headcode, m.gtr.headcode if m.gtr else "-", m.gtr.days if m.gtr else "-",
                         m.confidence if m.gtr else None, m.nr_points, m.gtr_points if m.gtr else 0,
                         len(m.issues) + (1 if m.gtr and m.gtr.headcode != m.nr.headcode else 0), m.status])
    write(wb["Match Audit"], rows, {5: '0.0"%"'})
    # Audit Totals (reconciles: compared + not compared = NR timing cells in scope)
    rows = []
    for res in sections:
        if res.not_compared:
            status = (f"Not complete - {res.not_compared} cell(s) belong to {len(res.missing)} {B} train(s) missing "
                      f"from {O} (see Missing Trains)")
        else:
            status = "Complete"
        if res.out_of_scope:
            status += f". {res.out_of_scope} other-operator train(s) out of scope"
        if res.not_in_table:
            status += f". {res.not_in_table} {B} train(s) not at any location shown in the {O} table"
        rows.append([res.section, res.cells, res.compared, res.not_compared, status])
    cells, compared = sum(r.cells for r in sections), sum(r.compared for r in sections)
    rows.append(["All sections", cells, compared, cells - compared,
                 "Complete" if cells == compared else f"Not complete - {cells - compared} cell(s) not compared"])
    ws = wb["Audit Totals"]
    ws.column_dimensions["E"].width = 70
    write(ws, rows, total=True)
    for c in range(1, 6):
        ws.cell(len(rows) + 1, c).font = Font(bold=True)
    notes = [f"Operators compared: {', '.join(sorted(cmp.operators))} (other operators are out of scope)."]
    notes += list(cmp.warnings)
    ws.cell(len(rows) + 3, 1, "Notes").font = Font(bold=True)
    for i, text in enumerate(notes, start=len(rows) + 4):
        ws.cell(i, 1, text).alignment = Alignment(vertical="top")
    # print settings: landscape, fit to one page wide, heading row on every page
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.print_title_rows = "1:1"
        ws.row_dimensions[1].height = max(ws.row_dimensions[1].height or 0, 30)
        for cell in ws[1]:
            cell.alignment = Alignment(vertical="center", horizontal=cell.alignment.horizontal, wrap_text=True)
    from rstools.fsutil import plain_text
    for ws in wb.worksheets:
        plain_text(ws)                   # text from the timetables is never stored as a formula
    return wb


def document_sections(wb):
    """The filled template as PDF / Word sections: one table per sheet, the Summary notes and the
    Audit Totals notes shown as text under their tables (not as tables of their own)."""
    from rstools.docexport import Section

    def text(v):
        if isinstance(v, float):
            return f"{v:.1f}%" if v != int(v) else f"{int(v)}%"
        return "" if v is None else str(v)
    out = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        headers = [text(h) for h in rows[0]]
        body, rest = [], []
        for r in rows[1:]:
            (rest if (rest or not any(v not in (None, "") for v in r)) else body).append(r)
        if ws.title == "Summary":                   # section rows and the total; the notes follow
            body, rest = rows[1:8], rows[8:]
        notes = [" - ".join(text(v) for v in r if v not in (None, "")) for r in rest
                 if any(v not in (None, "") for v in r)]
        pct = {i for i, h in enumerate(headers) if h == "Confidence"}
        data = [[text(v) if i in pct else ("" if v is None else str(v)) for i, v in enumerate(r[:len(headers)])]
                for r in body]
        fills, bold = {}, set()
        if ws.title == "Summary":
            colours = {"Differences found": "F4CCCC", "No differences": "C6EFCE"}
            fills = {(i, 8): colours.get(r[8], "FFEB9C") for i, r in enumerate(data)}
            bold = {len(data) - 1}
        elif ws.title == "Audit Totals" and data:
            bold = {len(data) - 1}
        out.append(Section(ws.title, headers, data, fills, bold, note="\n".join(notes) if ws.title != "Summary"
                           else ""))
        if ws.title == "Summary" and notes:
            out.append(Section("Comparison rules", ["Rule", "Detail"],
                               [n.split(" - ", 1) + [""] * (1 - n.count(" - ")) for n in notes]))
    return out


def _summary_row(ws, r, vals):
    from openpyxl.styles import Alignment, Border, PatternFill, Side
    thin = Side(style="thin", color="FFBFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c, v in enumerate(vals, start=2):
        cell = ws.cell(r, c, v)
        cell.alignment = Alignment(vertical="top", horizontal="center" if c < 9 else "left", wrap_text=True)
    for c in range(1, 10):
        ws.cell(r, c).border = border
    colour = {"Differences found": "FFF4CCCC", "No differences": "FFC6EFCE"}.get(vals[-1], "FFFFEB9C")
    ws.cell(r, 9).fill = PatternFill("solid", fgColor=colour)
    ws.column_dimensions["I"].width = max(ws.column_dimensions["I"].width or 0, 20)


def summary_lines(cmp: Comparison) -> List[str]:
    lines = []
    for res in cmp.sections:
        issues = sum(len(m.issues) for m in res.matched)
        B, O = cmp.base_label, cmp.other_label
        lines.append(f"{res.section}: {len(res.nr_trains)} {B} / {len(res.gtr_trains)} {O} trains, "
                     f"{len(res.matched)} matched, {len(res.missing)} missing from {O}, {issues} issue(s), "
                     f"{len(res.headcode_mismatches)} headcode mismatch(es)")
    return lines
