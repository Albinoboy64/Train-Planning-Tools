"""Excel change report summarising every change found."""
from __future__ import annotations

import datetime as _dt
import os
import re
from collections import defaultdict, Counter
from typing import Dict, List

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .compare import Change, CATEGORIES, CATEGORY_LABELS, CATEGORY_ORDER, tab_order
from .model import FIELD_LABELS
from rstools.fsutil import clean_cell
from rstools.timetable.xlstyle import HEAD_FILL as _HEAD, print_setup     # the shared report look

from .xlsxfix import save_workbook

HEAD_FILL = PatternFill("solid", fgColor=_HEAD)
HEAD_FONT = Font(bold=True, color="FFFFFFFF")
THIN = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _fill(c):
    from rstools.xlsave import fill
    return fill(c)


def _tabs(cs) -> str:
    """The tabs a train's changes are on, in tab order."""
    return ", ".join(sorted({c.sheet_title.strip() for c in cs}, key=tab_order))


def _table(ws, start_row, headers, rows, widths=None, fills=None):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=start_row, column=i, value=h)
        c.fill, c.font, c.border = HEAD_FILL, HEAD_FONT, BORDER
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for ri, row in enumerate(rows, start=start_row + 1):
        for ci, v in enumerate(row, start=1):
            c = ws.cell(row=ri, column=ci, value=clean_cell(v))
            c.border = BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
        if fills and fills[ri - start_row - 1]:
            col, f = fills[ri - start_row - 1]
            ws.cell(row=ri, column=col).fill = f
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    return start_row + len(rows) + 1


_CHANGED = re.compile(r"^(?:.+ )?changed from .* to .*$", re.S)
_BLOCK = re.compile(r"^(?:Train cancelled|New train) \((.*)\)$")


def _without_train(c: Change) -> str:
    """The description without the train name at its start (the Train column already shows it); any
    extra label (e.g. 'former MO variant') is kept."""
    d = c.description or ""
    head, sep, rest = d.partition(": ")
    if not sep or not head.startswith(c.train.split(" (")[0]):
        return d
    extra = head[len(c.train):].strip() if head.startswith(c.train) else ""
    return f"{extra} {rest}".strip() if extra else rest


def _details(c: Change) -> str:
    """Only what the Train / Category / Field / Was / Now columns do not already say."""
    m = _BLOCK.match(c.description or "")
    if m:
        return m.group(1)                              # e.g. '07.11 Seaford'
    rest = _without_train(c)
    head = rest.split(" changed from ")[0] if " changed from " in rest else ""
    if _CHANGED.match(rest) and c.kind == "modify" and c.old and c.new and "(" not in head:
        return ""                                      # plain 'Time changed from 05.23 to 05.25'
    return rest


def write_report(path: str, changes: List[Change], rounds: List[dict], info: dict):
    """The change report: Excel, or a PDF / Word document when `path` ends .pdf / .docx."""
    wb = openpyxl.Workbook()
    wb.properties.creator = wb.properties.lastModifiedBy = "Train Planning Tools"
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Carriage Working Notice - Change Report"
    ws["A1"].font = Font(bold=True, size=16, color=_HEAD)
    r = 3
    meta = [
        ("Generated", _dt.datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Comparison type", info.get("mode_label", "")),
        ("Original CWN", info.get("original", "")),
        ("Updated CWN", info.get("updated", "")),
        ("Output CWN", info.get("output", "")),
        ("Output format", info.get("output_type_label", "")),
        ("Days checked", info.get("days_label", "All days in the CWNs")),
        ("Total changes in this report", len(changes)),
        ("Trains affected", len({c.train for c in changes})),
        ("Location tabs affected", len({c.sheet_title.strip() for c in changes})),
    ]
    for k, v in meta:
        ws.cell(row=r, column=1, value=k).font = Font(bold=True)
        ws.cell(row=r, column=2, value=clean_cell(v))
        r += 1
    r += 1

    # colour key
    ws.cell(row=r, column=1, value="Highlight colour key").font = Font(bold=True, size=12)
    r += 1
    key_rows, key_fills = [], []
    for rd in rounds:
        key_rows.append([f"Round {rd['round']}", "",
                         f"{os.path.basename(rd.get('original', ''))} -> {os.path.basename(rd.get('updated', ''))}",
                         rd.get("created", "")])
        key_fills.append((2, _fill(rd["colour"])))
    r = _table(ws, r, ["Round", "Colour", "Comparison", "Run on"], key_rows, fills=key_fills) + 1

    # by category
    ws.cell(row=r, column=1, value="Changes by category").font = Font(bold=True, size=12)
    r += 1
    rnds = sorted({c.round for c in changes}) or [1]
    multi = len(rnds) > 1                          # one round: no round columns (they would repeat the total)
    cnt = Counter((c.category, c.round) for c in changes)
    cat_rows = []
    for k, lbl, _h, _d in CATEGORIES:
        total = sum(cnt.get((k, rd), 0) for rd in rnds)
        if total:                                  # categories with no changes are left out
            cat_rows.append([lbl] + ([cnt.get((k, rd), 0) for rd in rnds] if multi else []) + [total])
    if not cat_rows:
        cat_rows = [["No changes", 0]]
    heads = ["Category"] + ([f"Round {rd}" for rd in rnds] if multi else []) + ["Changes" if not multi else "Total"]
    r = _table(ws, r, heads, cat_rows) + 1

    # by location
    ws.cell(row=r, column=1, value="Changes by location tab").font = Font(bold=True, size=12)
    r += 1
    loc: Dict[str, Counter] = defaultdict(Counter)
    for c in changes:
        loc[c.sheet_title.strip()][c.category] += 1
    loc_rows = [[t, sum(cn.values()), ", ".join(f"{CATEGORY_LABELS[k]} ({v})" for k, v in
                                               sorted(cn.items(), key=lambda kv: CATEGORY_ORDER[kv[0]]))]
                for t, cn in sorted(loc.items(), key=lambda kv: tab_order(kv[0]))]
    _table(ws, r, ["Tab", "Changes", "Breakdown"], loc_rows)
    for col, w in zip("ABCD", (30, 16, 70, 22)):
        ws.column_dimensions[col].width = w

    # all changes
    ws2 = wb.create_sheet("All Changes")
    rows, fills = [], []
    colour_of = {rd["round"]: rd["colour"] for rd in rounds}
    for c in sorted(changes, key=lambda c: (c.round, tab_order(c.sheet_title),
                                            c.sort_time if c.sort_time is not None else 9999, c.train)):
        rows.append(([c.round] if multi else []) + [
            c.sheet_title.strip(), c.train, CATEGORY_LABELS.get(c.category, c.category),
            FIELD_LABELS.get(c.field, c.field) if c.field else "Whole train",
            c.old if c.kind == "modify" or c.kind == "remove_row" else "",
            c.new if c.kind == "modify" or c.kind == "add_row" else "", _details(c)])
        fills.append((1, _fill(colour_of.get(c.round, c.colour or "FFFF00"))))
    heads = (["Round"] if multi else []) + ["Tab", "Train", "Category", "Field", "Was", "Now", "Details"]
    end = _table(ws2, 1, heads, rows, widths=([8] if multi else []) + [12, 16, 28, 20, 18, 18, 60],
                 fills=fills if multi else None)              # round colours only matter with rounds
    ws2.auto_filter.ref = f"A1:{get_column_letter(len(heads))}{max(end - 1, 2)}"
    ws2.freeze_panes = "A2"

    # by train
    ws3 = wb.create_sheet("Changes by Train")
    tr = defaultdict(list)
    for c in changes:
        tr[c.train].append(c)
    trows = []
    for t in sorted(tr):
        cs = tr[t]
        cats = sorted({c.category for c in cs}, key=lambda k: CATEGORY_ORDER[k])
        trows.append([t, ", ".join(CATEGORY_LABELS[k] for k in cats),
                      _tabs(cs), len(cs),
                      "\n".join(dict.fromkeys(_without_train(c) for c in cs))])
    end = _table(ws3, 1, ["Train", "Change types", "Tabs", "Count", "Details"], trows,
                 widths=[16, 40, 40, 8, 90])
    ws3.auto_filter.ref = f"A1:E{max(end - 1, 2)}"
    ws3.freeze_panes = "A2"

    # new and cancelled trains, in time order
    w = wb.create_sheet("New and Cancelled Trains")
    seen: Dict[tuple, list] = {}
    for c in changes:
        if c.category in ("NEW", "CANCELLED"):
            seen.setdefault((c.category, c.train), []).append(c)
    entries = sorted(seen.items(), key=lambda kv: (min((c.sort_time for c in kv[1] if c.sort_time is not None),
                                                       default=9999), kv[0][1]))
    rws, nfills = [], []
    for (cat, t), cs in entries:
        rws.append(["New" if cat == "NEW" else "Cancelled", t, _tabs(cs),
                    _details(cs[0])] + ([cs[0].round] if multi else []))
        nfills.append((5, _fill(colour_of.get(cs[0].round, cs[0].colour or "FFFF00"))) if multi else None)
    if not rws:
        rws = [["None", "", "", ""] + ([""] if multi else [])]
        nfills = []
    heads = ["Status", "Train", "Tabs", "Time and destination"] + (["Round"] if multi else [])
    end = _table(w, 1, heads, rws, widths=[12, 16, 30, 40] + ([8] if multi else []), fills=nfills if multi else None)
    w.freeze_panes = "A2"
    w.auto_filter.ref = f"A1:{get_column_letter(len(heads))}{max(end - 1, 2)}"
    ws.freeze_panes = "A2"                       # the Summary's title stays in view
    print_setup(ws, 0, gridlines=True)
    for sheet in (ws2, ws3, w):
        print_setup(sheet, 1)

    if path.lower().endswith((".pdf", ".docx")):
        from rstools.docexport import sections_from_workbook, write_document
        write_document(path, "Carriage Working Notice - Change Report", sections_from_workbook(wb))
    else:
        save_workbook(wb, path)          # stores text from the CWNs as text, never as a formula
