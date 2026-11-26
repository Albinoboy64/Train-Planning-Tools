"""Comparing two sets of rule documents (Section 4, TPR): the shared result and its report.

Each document is read into keyed items (a Section 4 possession row, a TPR table row or paragraph). Items are
paired by key and their fields compared; the report lists what changed (old -> new), what was added and what was
removed. The Live View shows the same result.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

CHANGED, ADDED, REMOVED, SAME = "changed", "added", "removed", "same"


@dataclass
class DocItem:
    key: str                                # stable identity ('110.3 MID WEEK #1', 'Headways | Brighton | ...')
    group: str                              # what it belongs to (line of route, TPR section and table)
    label: str                              # how it is named in lists
    status: str = SAME
    fields: List[Tuple[str, str, str]] = field(default_factory=list)    # (field, original, updated), every field
    where: str = ""                         # file and page(s), e.g. 'KS.pdf p12 / KS v2.pdf p13'

    @property
    def changes(self) -> List[Tuple[str, str, str]]:
        return [f for f in self.fields if f[1] != f[2]]


@dataclass
class DocComparison:
    kind: str                               # 'Section 4' / 'TPR'
    first: List[str]                        # the files on each side
    second: List[str]
    items: List[DocItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    compared: List[str] = field(default_factory=list)       # what was compared, in words
    not_compared: List[str] = field(default_factory=list)   # what was left out (headers and the like)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)


def pair_fields(names: Sequence[str], a: Dict[str, str], b: Dict[str, str]) -> List[Tuple[str, str, str]]:
    return [(n, a.get(n, ""), b.get(n, "")) for n in names]


def norm(text: str) -> str:
    """Text as compared: spacing and the dashes / quotes PDFs vary on do not count."""
    t = (text or "").replace("–", "-").replace("—", "-").replace("‘", "'").replace("’", "'")
    t = t.replace("“", '"').replace("”", '"').replace("\xa0", " ")
    return " ".join(t.split())


def build_workbook(cmp: DocComparison):
    from .xlstyle import add_sheet, new_workbook
    wb = new_workbook()
    changed, added, removed = cmp.count(CHANGED), cmp.count(ADDED), cmp.count(REMOVED)
    summary = [[f"{cmp.kind} items in both", changed + cmp.count(SAME)],
               ["...changed", changed],
               ["...unchanged", cmp.count(SAME)],
               ["Added (only in the updated documents)", added],
               ["Removed (only in the original documents)", removed],
               ["Individual changes", sum(len(i.changes) for i in cmp.items if i.status == CHANGED)]]
    add_sheet(wb, "Summary", ["Figure", "Count"], summary, [52, 12], center=[2],
              fills={1: "review" if changed else "ok", 3: "info" if added else "ok", 4: "bad" if removed else "ok"})
    rows = []
    for it in cmp.items:
        if it.status == CHANGED:
            for name, old, new in it.changes:
                rows.append([it.group, it.label, name, old or "-", new or "-", it.where])
    add_sheet(wb, "Changes", ["Where", "Item", "What changed", "Original", "Updated", "Pages"], rows,
              [36, 34, 20, 50, 50, 26])
    for title, status, side in (("Added", ADDED, 2), ("Removed", REMOVED, 1)):
        part = []
        for it in cmp.items:
            if it.status == status:
                values = [(n, o if side == 1 else u) for n, o, u in it.fields]
                part.append([it.group, it.label, "; ".join(f"{n}: {v}" for n, v in values if v), it.where])
        add_sheet(wb, title, ["Where", "Item", "Details", "Pages"], part, [36, 34, 100, 26])
    audit = [["Original", "; ".join(os.path.basename(f) for f in cmp.first)],
             ["Updated", "; ".join(os.path.basename(f) for f in cmp.second)]]
    audit += [["Compared", c] for c in cmp.compared]
    audit += [["Not compared", c] for c in cmp.not_compared]
    audit += [["Note", w] for w in cmp.warnings]
    add_sheet(wb, "What Was Compared", ["Item", "Detail"], audit, [20, 110])
    return wb


def summary_lines(cmp: DocComparison) -> List[str]:
    changed = cmp.count(CHANGED)
    return [f"{changed + cmp.count(SAME)} {cmp.kind} item(s) in both: {changed} changed",
            f"{cmp.count(ADDED)} added, {cmp.count(REMOVED)} removed, "
            f"{sum(len(i.changes) for i in cmp.items if i.status == CHANGED)} individual change(s)"]
