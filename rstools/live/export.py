"""Save what the Live View lists - with its filter and search - to Excel, PDF or Word."""
from __future__ import annotations

import time
from typing import Iterable

from .model import ADDED, CHANGED, ISSUE, REMOVED, SAME

STATE_TEXT = {SAME: "No change", CHANGED: "Changed", ADDED: "Added", REMOVED: "Removed / missing", ISSUE: "Issue",
              "muted": "Not compared"}
STATE_FILL = {CHANGED: "review", ADDED: "ok", REMOVED: "bad", ISSUE: "bad"}


def export(path: str, result, items: Iterable, filt: str, find: str, confirmed: Iterable[str] = ()):
    """`confirmed`: keys of the items ticked as confirmed in the Live View (shown in a Confirmed column)."""
    from rstools.timetable.xlstyle import add_sheet, new_workbook, save
    items = list(items)
    done = set(confirmed)
    wb = new_workbook()
    about = [["Comparison", result.title], ["Exported", time.strftime("%d/%m/%Y %H:%M")],
             ["Shown", filt + (f", containing '{find}'" if find else "")], ["Items", len(items)],
             ["Confirmed", sum(1 for it in items if it.key in done)]]
    about += [[STATE_TEXT.get(k, k), v] for k, v in sorted(result.counts.items())]
    add_sheet(wb, "What Was Compared", ["Item", "Detail"], about + [["Note", w] for w in result.warnings], [24, 100])
    add_sheet(wb, "Trains Listed", ["Section / tab", "Train", "Result", "Status", "Differences", "Confirmed"],
              [[it.group, it.label, STATE_TEXT.get(it.state, it.state), it.status, "\n".join(it.notes[:12]),
                "Yes" if it.key in done else ""] for it in items], [18, 18, 16, 36, 80, 11],
              fills={i: STATE_FILL[it.state] for i, it in enumerate(items) if it.state in STATE_FILL})
    rows: list = []
    fills: dict = {}
    for it in items:
        for row in it.rows:
            if row.state in (SAME, "muted"):
                continue
            fills[len(rows)] = STATE_FILL.get(row.state, "review")
            rows.append([it.group, it.label] + [str(c) for c in row.cells] + [STATE_TEXT.get(row.state, "")])
    add_sheet(wb, "Differences in Detail", ["Section / tab", "Train"] + list(result.columns) + ["Result"], rows,
              [18, 18] + [22] * len(result.columns) + [16], fills=fills)
    save(wb, path, f"Live View - {result.title}")
