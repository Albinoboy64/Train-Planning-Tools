"""Compare the same reports made from two timetables (original and updated plans).

Rows are matched by their key columns (e.g. Day + Train, or Fleet). Each report becomes a
'what changed' table: one line per figure that differs - Original, Updated, the change and the
change in percent - plus lines for rows found in only one timetable. Summary reports (per day,
per fleet, per hour) list every figure, changed or not, so the totals can be read side by side.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Sequence, Tuple, cast

from .units import Report

# report name -> (number of key columns, list every figure (summary) or only changes (detail))
SPEC: Dict[str, Tuple[int, bool]] = {
    "Capacity Summary": (1, True), "Capacity by Hour": (1, True), "Capacity by Train": (2, False),
    "Washes by Fleet": (1, True), "Washes by Diagram": (2, False), "Washes by Unit": (1, False),
    "CETs by Fleet": (1, True), "CETs by Diagram": (2, False), "CETs by Unit": (1, False),
    "Inferred Links": (3, False), "Next-Day Checks": (3, False),
    "Possible Washes, CETs, Fuel": (5, False),
    "Depot Moves by Day": (1, True), "Depot Moves by Depot": (3, True), "Depot Moves by Diagram": (2, False),
    "Captive Diagrams": (2, False), "Captive Units": (1, False), "Fuel Check (171s)": (1, False),
}
# descriptive columns left out of the comparison (they change whenever diagrams are renumbered)
SKIP = {"Diagrams worked", "Linked by", "Matched on", "Why it was inferred", "Stabled at", "Could be added at"}
ONLY_OLD, ONLY_NEW = "Only in the original", "Only in the updated"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _keyed(rows: Sequence[Sequence], nkeys: int) -> Dict[tuple, Sequence]:
    """Rows by key; a key seen again gets a running number so no row is lost."""
    seen: Counter = Counter()
    out = {}
    for r in rows:
        k = tuple("" if v is None else v for v in r[:nkeys])
        seen[k] += 1
        out[k + ((seen[k],) if seen[k] > 1 else ())] = r
    return out


def _pct(old, new):
    if not (_num(old) and _num(new)) or old == 0:
        return ""
    return round((new - old) / abs(old) * 100, 1)


def compare_report(old: Report, new: Report) -> Tuple[Report, Counter]:
    nkeys, show_all = SPEC.get(new.name, (1, False))
    if new.name.endswith("by Fleet") and new.headers and new.headers[0] == "Day":
        nkeys = 2                                       # each day's fleets
    nkeys = min(nkeys, len(new.headers))
    figures = new.headers[nkeys:]
    a, b = _keyed(old.rows, nkeys), _keyed(new.rows, nkeys)
    order = list(a) + [k for k in b if k not in a]
    if show_all:                                   # keep the updated plan's order (totals last)
        order = [k for k in b] + [k for k in a if k not in b]
    rows: List[list] = []
    kinds: List[str] = []
    counts: Counter = Counter()
    for k in order:
        key = list(k[:nkeys])
        if k not in b:
            rows.append(key + ["(whole row)", "Present", "-", ONLY_OLD, ""])
            counts["only_old"] += 1
            kinds.append("body")
            continue
        if k not in a:
            rows.append(key + ["(whole row)", "-", "Present", ONLY_NEW, ""])
            counts["only_new"] += 1
            kinds.append("body")
            continue
        ra, rb = a[k], b[k]
        changed = False
        total = str(key[0]).startswith(("Total", "Week total", "Average"))
        for i, fig in enumerate(figures, start=nkeys):
            if fig in SKIP:
                continue
            va = ra[i] if i < len(ra) else None
            vb = rb[i] if i < len(rb) else None
            same = va == vb
            if same and not show_all:
                continue
            changed |= not same
            change: object
            if _num(va) and _num(vb):
                diff = round(cast(float, vb) - cast(float, va), 2)
                change = diff if diff != int(diff) else int(diff)
            else:
                change = "" if same else "Changed"
            rows.append(key + [fig, "" if va is None else va, "" if vb is None else vb, change, _pct(va, vb)])
            kinds.append("total" if total else "body")
        counts["changed" if changed else "same"] += 1
    head = new.headers[:nkeys] + ["Figure", "Original", "Updated", "Change", "Change %"]
    note = ("Every figure, original and updated." if show_all else
            "Only figures that differ, and rows found in one timetable only.")
    return Report(new.name, f"Original vs updated - {new.title}", head, rows, kinds, note), counts


def compare_reports(old: List[Report], new: List[Report], old_label: str, new_label: str,
                    notes: Sequence[str] = ()) -> List[Report]:
    """A summary of what changed, then each report compared, then notes."""
    by_old = {r.name: r for r in old}
    out, summary = [], []
    for rep in new:
        if rep.name == "Notes":
            continue
        base = by_old.get(rep.name, Report(rep.name, rep.title, rep.headers, []))
        cmp, counts = compare_report(base, rep)
        out.append(cmp)
        summary.append([rep.name, counts["same"] + counts["changed"], counts["changed"], counts["only_old"],
                        counts["only_new"]])
    first = Report("Comparison Summary", "What changed between the two timetables",
                   ["Report", "Rows in both", "Rows with changes", ONLY_OLD, ONLY_NEW], summary,
                   ["body"] * len(summary), f"Original: {old_label}. Updated: {new_label}.")
    note_rows = [[n] for n in notes]
    for rep in (r for r in old + new if r.name == "Notes"):
        note_rows += [list(r[:1]) for r in rep.rows]
    seen, uniq = set(), []
    for r in note_rows:
        if r and r[0] not in seen:
            seen.add(r[0])
            uniq.append(r)
    return [first] + out + [Report("Notes", "How this comparison was made", ["Note"], uniq, ["body"] * len(uniq))]
