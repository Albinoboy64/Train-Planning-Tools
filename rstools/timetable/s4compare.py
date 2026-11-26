"""Two sets of Section 4 (Standard Possession Opportunities) documents compared.

Possession rows are paired by section number and night (the section number is Network Rail's stable reference;
the section's name is compared as its locations). Where a section has several possessions for a night (different
periods, or a cell holding two possessions) they are paired by the periods they cover, then in order. Compared:
the periods (names and dates), the windows (times and days), the locations (section name and ends), what is
blocked, and the remarks / notes. Page headings, the line of route title and page numbers are not compared.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .doccompare import ADDED, CHANGED, REMOVED, SAME, DocComparison, DocItem, norm, pair_fields
from .section4 import Possession, Statement

FIELDS = ("Section", "Locations", "Periods", "Dates", "Windows", "Blocked", "Remarks")


def _values(p: Possession) -> Dict[str, str]:
    return {"Section": norm(p.section),
            "Locations": " / ".join(norm(e) for e in p.ends),
            "Periods": "; ".join(norm(x.name) for x in p.periods),
            "Dates": "; ".join(f"{x.start:%d/%m/%Y} to {x.end:%d/%m/%Y}" for x in p.periods),
            "Windows": "; ".join(w.text for w in p.windows),
            "Blocked": norm(p.blocked),
            "Remarks": norm(p.remarks)}


def _key(p: Possession) -> Tuple[str, str]:
    return (p.number or norm(p.section).lower(), p.night)


def _num_key(k: Tuple[str, str]):
    parts = re.findall(r"\d+|[a-z]+", k[0].lower())
    return [int(x) if x.isdigit() else 0 for x in parts] + [k[1]]


def compare_statements(a: Statement, b: Statement) -> DocComparison:
    cmp = DocComparison("Section 4", list(a.files), list(b.files), warnings=list(a.warnings) + list(b.warnings))
    groups_a: Dict[Tuple[str, str], List[Possession]] = defaultdict(list)
    groups_b: Dict[Tuple[str, str], List[Possession]] = defaultdict(list)
    for p in a.possessions:
        groups_a[_key(p)].append(p)
    for p in b.possessions:
        groups_b[_key(p)].append(p)
    for key in sorted(set(groups_a) | set(groups_b), key=_num_key):
        left, right = list(groups_a.get(key, [])), list(groups_b.get(key, []))
        pairs: List[Tuple[Possession | None, Possession | None]] = []
        # same periods first, then same windows, then in order
        for same in (lambda x, y: _values(x)["Periods"] == _values(y)["Periods"]
                     and _values(x)["Windows"] == _values(y)["Windows"],
                     lambda x, y: _values(x)["Periods"] == _values(y)["Periods"],
                     lambda x, y: True):
            for pa in list(left):
                pb = next((q for q in right if same(pa, q)), None)
                if pb is not None:
                    pairs.append((pa, pb))
                    left.remove(pa)
                    right.remove(pb)
        pairs += [(pa, None) for pa in left] + [(None, pb) for pb in right]
        for n, (x, y) in enumerate(pairs, start=1):
            ref = x or y
            assert ref is not None
            label = f"{ref.number} {ref.night}".strip() + (f" ({n})" if len(pairs) > 1 else "")
            va, vb = (_values(x) if x else {}), (_values(y) if y else {})
            item = DocItem(f"{key[0]}|{key[1]}|{n}", ref.route or "Section 4", label,
                           fields=pair_fields(FIELDS, va, vb),
                           where=" / ".join(s for s in ((x.source if x else ""), (y.source if y else "")) if s))
            item.status = ADDED if x is None else REMOVED if y is None else (CHANGED if item.changes else SAME)
            cmp.items.append(item)
    cmp.compared = ["Each possession row, paired by section number and night: the section name and its end "
                    "locations, the periods and their dates, the possession windows (times and days), what is "
                    "blocked, and the remarks / notes.",
                    f"{len(a.possessions)} possession row(s) in the original, {len(b.possessions)} in the updated."]
    cmp.not_compared = ["Page headings and footers, the line of route title, version and publication details, "
                        "and page numbers (they change with every issue)."]
    return cmp


def read_side(paths: Sequence[str], log=lambda m: None) -> Statement:
    from .section4 import read_statement
    return read_statement(paths, log)
