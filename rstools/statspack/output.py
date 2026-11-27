"""Where a run's tables go: an Excel workbook (the default) or a PDF / Word document.

Every Stats Pack output - packs, comparisons and the unit reports - is written through one of
these 'sinks', so all of them can be produced in any of the three formats.
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional, Sequence

from rstools.branding import APP_NAME
from rstools.docexport import Section, ext_for, write_document

from .compare import Diff, headers_of, write_differences
from .stats import Clock, Dur, Table
from .xlsxw import HIGHLIGHT, UNKNOWN, Workbook, _is_measure, fmt_clock, fmt_dur, render_report, render_table

def sink_for(fmt: str):
    return XlsxSink() if fmt in ("", "xlsx", None) else DocSink(fmt)


class XlsxSink:
    ext = ".xlsx"

    def __init__(self):
        self.wb = Workbook()

    def table(self, sheet: str, title: str, table: Table, marks=None, extra=()):
        render_table(self.wb, sheet, title, table, marks, extra)

    def differences(self, diffs: Sequence[Diff], title: str, summary=None, flag_miles: Optional[float] = None):
        write_differences(self.wb, diffs, title, summary, flag_miles)

    def report(self, rep):
        render_report(self.wb, rep.name, rep.title, rep.headers, rep.rows, rep.kinds, rep.note)

    def save(self, path: str, title: str = ""):
        self.wb.save(path)


def _show(v, unknown: bool) -> str:
    if v is None:
        return UNKNOWN if unknown else ""
    if isinstance(v, Clock):
        return fmt_clock(v)
    if isinstance(v, Dur):
        return fmt_dur(v)
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, _dt.date):
        return f"{v:%d/%m/%Y}"
    return str(v)


class DocSink:
    def __init__(self, fmt: str):
        self.ext = ext_for(fmt)
        self.sections: List[Section] = []

    def table(self, sheet: str, title: str, table: Table, marks=None, extra=()):
        if table.name == "Glossary":
            created, inputs = table.rows[0].cells if table.rows else ("", "")
            self.sections.append(Section("Glossary", ["Created", "Input files"], [[str(created), str(inputs)]]))
            return
        rows = list(table.rows) + list(extra)
        shift = 1 if table.has_day else 0
        width = max([len(headers_of(table))] + [len(r.cells) for r in rows])
        unknown = [ci >= table.key_cols and _is_measure(table, ci - shift) for ci in range(width)]
        data = [[_show(v, unknown[ci]) for ci, v in enumerate(r.cells)] for r in rows]
        fills = {}
        for (ri, ci), mark in (marks or {}).items():
            fills[(ri, ci)] = HIGHLIGHT.get(mark, "FFFFFFFF")[2:]
        n = len(table.rows)
        self.sections.append(Section(title, headers_of(table)[:width] + [""] * (width - len(headers_of(table))),
                                     data, fills, {i for i, r in enumerate(rows) if r.kind == "total"},
                                     key_cols=max(table.key_cols, 1),
                                     strike_rows=set(range(n, n + len(extra)))))

    def differences(self, diffs: Sequence[Diff], title: str, summary=None, flag_miles: Optional[float] = None):
        if summary:
            self.sections.append(Section(f"{title} - summary", ["Figure", "Original", "Updated", "Change"],
                                         [[str(c) for c in row] for row in summary]))
        if flag_miles:
            flagged = [d for d in diffs if d.flag]
            self.sections.append(Section(f"Mileage increases over {flag_miles:g} miles ({len(flagged)})",
                                         ["Tab", "Row", "Column", "Old", "New", "Change"],
                                         [[d.tab, d.key, d.column, _show(d.old, False), _show(d.new, False), d.change]
                                          for d in flagged] or [["None", "", "", "", "", ""]],
                                         {(i, -1): HIGHLIGHT["flagged"][2:] for i in range(len(flagged))}))
        self.sections.append(Section(title, ["Tab", "Row", "Column", "Old", "New", "Change"],
                                     [[d.tab, d.key, d.column, _show(d.old, False), _show(d.new, False), d.change]
                                      for d in diffs] or [["No differences found.", "", "", "", "", ""]]))

    def report(self, rep):
        rows = [[_show(v, False) for v in r] for r in rep.rows] or [["None"] + [""] * (len(rep.headers) - 1)]
        self.sections.append(Section(rep.title, list(rep.headers), rows,
                                     bold_rows={i for i, k in enumerate(rep.kinds) if k == "total"}, note=rep.note))

    def save(self, path: str, title: str = ""):
        write_document(path, title or APP_NAME, self.sections)
