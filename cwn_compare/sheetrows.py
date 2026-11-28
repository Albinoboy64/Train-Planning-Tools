"""Inserting rows into a worksheet with everything below moving with its rows. openpyxl's insert_rows moves
cell values and styles only: merged cells, row heights / hidden / outline levels and each hyperlink's own cell
reference stay behind, so they would land on the wrong rows."""
from __future__ import annotations

from typing import Dict, Iterable, Tuple


def shift_merged(ws, from_row: int, by: int) -> None:
    """Move the merged ranges starting at or below `from_row` down by `by` rows. Each range is taken out, shifted
    and put back: changing it in place would break openpyxl's set of ranges (it is hashed on its coordinates)."""
    moved = [m for m in ws.merged_cells.ranges if m.min_row >= from_row]
    for m in moved:
        ws.merged_cells.remove(m)
    for m in moved:
        m.shift(0, by)
        ws.merged_cells.add(m)


def insert_rows(ws, at: int, n: int) -> None:
    """Insert `n` empty rows above row `at`; merged cells, row formats and hyperlinks below move with their rows."""
    if n <= 0:
        return
    dims = {r: (d.height, d.hidden, d.outlineLevel) for r, d in ws.row_dimensions.items()
            if r >= at and (d.height or d.hidden or d.outlineLevel)}
    moved = [m for m in ws.merged_cells.ranges if m.min_row >= at]
    for m in moved:
        ws.merged_cells.remove(m)
    ws.insert_rows(at, n)
    for r in dims:
        d = ws.row_dimensions[r]
        d.height, d.hidden, d.outlineLevel = None, False, 0
    for r, (height, hidden, level) in dims.items():
        d = ws.row_dimensions[r + n]
        d.height, d.hidden, d.outlineLevel = height, hidden, level
    for m in moved:
        m.shift(0, n)
        ws.merged_cells.add(m)
    for cell in list(ws._cells.values()):
        if cell.row >= at + n and cell.hyperlink is not None:
            cell.hyperlink = cell.hyperlink          # the setter points the link at the cell's new address


def row_map(inserts: Iterable[Tuple[int, int]], last_row: int) -> Dict[int, int]:
    """{old row: new row} after inserting (at, n) blocks given bottom-up (each `at` in the sheet's original rows,
    highest first), for the rows that moved. Used to re-point links from other tabs (writer._fix_hyperlinks)."""
    points = sorted(inserts)
    out: Dict[int, int] = {}
    for r in range(1, last_row + 1):
        shift = sum(n for at, n in points if at <= r)
        if shift:
            out[r] = r + shift
    return out
