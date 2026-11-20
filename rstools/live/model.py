"""What the Live View shows, whatever was compared: a list of items (trains / rows), each with a
side-by-side table of its details and the differences marked."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# item states (filtering and colours)
SAME, CHANGED, ADDED, REMOVED, ISSUE = "same", "changed", "added", "removed", "issue"
DIFF_STATES = (CHANGED, ADDED, REMOVED, ISSUE)


@dataclass
class LiveRow:
    cells: List[str]                    # what is shown in each detail column
    state: str = SAME                   # SAME / CHANGED / ADDED / REMOVED / ISSUE, or 'muted' (not compared)
    group: str = ""                     # 'details': a train-detail row (shown under a heading that folds)


@dataclass
class LiveItem:
    key: str                            # stable across refreshes (keeps the selection)
    group: str                          # section / location tab / stats tab
    label: str                          # train or row name
    state: str                          # SAME / CHANGED / ADDED / REMOVED / ISSUE
    status: str                         # short text for the list ('Platform changed', 'Missing from GTR'...)
    rows: List[LiveRow] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)      # the differences in words (as in the report)
    order: int = 0

    def signature(self) -> tuple:
        """Changes when anything shown for the item changes (to mark items updated by a refresh)."""
        return (self.state, self.status, tuple((tuple(r.cells), r.state) for r in self.rows), tuple(self.notes))


@dataclass
class LiveResult:
    title: str
    columns: List[str]                  # detail table headings
    items: List[LiveItem]
    warnings: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if not self.counts:
            for it in self.items:
                self.counts[it.state] = self.counts.get(it.state, 0) + 1


PAIRED = "paired"                       # error checking off: put side by side, not judged


def view(result: LiveResult, ignore_source_only: bool = False, check: bool = True) -> LiveResult:
    """The result as the Live View should show it.

    ignore_source_only: leave out trains / rows that are only in the source (the first file - the
    original or the reference) and not in the file compared with it, e.g. trains outside a print that
    only covers part of a timetable.
    check=False: error checking off - matched trains are just put side by side for checking by eye
    (state PAIRED, nothing coloured or described as a difference). Trains found on one side only are
    still listed, so nothing can be missed."""
    if not ignore_source_only and check:
        return result
    items = []
    for it in result.items:
        if ignore_source_only and it.state == REMOVED:
            continue
        if not check and it.state in (SAME, CHANGED, ISSUE):
            it = LiveItem(it.key, it.group, it.label, PAIRED, "Paired - check by eye",
                          [LiveRow(r.cells, SAME if r.state != "muted" else r.state, r.group) for r in it.rows], [],
                          it.order)
        items.append(it)
    notes = list(result.warnings)
    if ignore_source_only:
        notes.append("Trains only in the source (first) file are left out.")
    if not check:
        notes.append("Error checking is off: trains are paired for checking by eye; differences are not marked.")
    return LiveResult(result.title, result.columns, items, notes)
