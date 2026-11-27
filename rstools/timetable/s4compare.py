"""Two sets of Section 4 (Standard Possession Opportunities) documents compared.

Possession rows are paired by section number and night (the section number is Network Rail's stable reference;
the section's name is compared as its locations). Where a section has several possessions for a night (different
periods, or a cell holding two possessions) they are paired by the periods they cover, then in order. Compared:
the periods (names; their dates always move between issues so are not compared), the windows (times and days),
the locations (section name and ends), what is blocked, and the remarks / notes (by content: dates, case,
punctuation and spelling slips do not count). Page headings, the line of route title and page numbers are not
compared.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .doccompare import ADDED, CHANGED, REMOVED, SAME, DocComparison, DocItem, books_of, norm, pair_fields
from .section4 import Possession, Statement
from rstools.naming import plural

FIELDS = ("Section", "Locations", "Periods", "Windows", "Blocked", "Remarks")


def _values(p: Possession) -> Dict[str, str]:
    return {"Section": norm(p.section),
            "Locations": " / ".join(norm(e) for e in p.ends),
            "Periods": "; ".join(norm(x.name) for x in p.periods),
            "Windows": "; ".join(w.text for w in p.windows),
            "Blocked": norm(p.blocked),
            "Remarks": norm(p.remarks)}


def _key(p: Possession) -> Tuple[str, str, str]:
    """Section number, night and what is blocked: the section's several possessions for a night differ by the line
    blocked (Down Slow No1, Down Slow No2, Down and Up Fast...), so the number and night alone repeat."""
    return (p.number or norm(p.section).lower(), p.night, norm(p.blocked).lower())


def _num_key(k: Tuple[str, ...]):
    parts = re.findall(r"\d+|[a-z]+", k[0].lower())
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in parts] + [(2, 0, x) for x in k[1:]]


def _pair_group(left: List[Possession], right: List[Possession], fallback: bool):
    """Pair two lists of possessions: same periods and windows first, then same periods, then (fallback, for rows
    whose blocked text changed) same windows and then the only one left on each side."""
    pairs: List[Tuple[Optional[Possession], Optional[Possession]]] = []
    rules = [lambda x, y: _values(x)["Periods"] == _values(y)["Periods"] and _values(x)["Windows"] ==
             _values(y)["Windows"],
             lambda x, y: _values(x)["Periods"] == _values(y)["Periods"]]
    if fallback:
        rules = [lambda x, y: _values(x)["Windows"] == _values(y)["Windows"]] + rules[1:]
    else:
        rules.append(lambda x, y: True)
    for same in rules:
        for pa in list(left):
            pb = next((q for q in right if same(pa, q)), None)
            if pb is not None:
                pairs.append((pa, pb))
                left.remove(pa)
                right.remove(pb)
    if fallback and len(left) == 1 and len(right) == 1:
        pairs.append((left.pop(), right.pop()))
    return pairs, left, right


def compare_statements(a: Statement, b: Statement) -> DocComparison:
    cmp = DocComparison("Section 4", list(a.files), list(b.files), warnings=list(a.warnings) + list(b.warnings))
    groups_a: Dict[Tuple[str, str, str], List[Possession]] = defaultdict(list)
    groups_b: Dict[Tuple[str, str, str], List[Possession]] = defaultdict(list)
    for p in a.possessions:
        groups_a[_key(p)].append(p)
    for p in b.possessions:
        groups_b[_key(p)].append(p)
    matched: Dict[Tuple[str, str, str], list] = {}
    rest_a: List[Possession] = []
    rest_b: List[Possession] = []
    for key in sorted(set(groups_a) | set(groups_b), key=_num_key):
        pairs, left, right = _pair_group(list(groups_a.get(key, [])), list(groups_b.get(key, [])), False)
        matched[key] = pairs
        rest_a += left
        rest_b += right
    # rows whose blocked text changed: pair what is left by section number and night
    by_a: Dict[Tuple[str, str], List[Possession]] = defaultdict(list)
    by_b: Dict[Tuple[str, str], List[Possession]] = defaultdict(list)
    for p in rest_a:
        by_a[_key(p)[:2]].append(p)
    for p in rest_b:
        by_b[_key(p)[:2]].append(p)
    for nk in sorted(set(by_a) | set(by_b), key=_num_key):
        pairs, left, right = _pair_group(by_a.get(nk, []), by_b.get(nk, []), True)
        key = (nk[0], nk[1], "~")
        matched[key] = pairs + [(x, None) for x in left] + [(None, y) for y in right]
    for key in sorted(matched, key=_num_key):
        pairs = matched[key]
        for n, (x, y) in enumerate(pairs, start=1):
            ref = x or y
            assert ref is not None
            label = f"{ref.number} {ref.night}".strip() + (f" - {norm(ref.blocked)}" if ref.blocked else "")
            if len(pairs) > 1:
                label += f" ({n})"
            va, vb = (_values(x) if x else {}), (_values(y) if y else {})
            item = DocItem(f"{key[0]}|{key[1]}|{key[2]}|{n}", ref.route or "Section 4", label,
                           fields=pair_fields(FIELDS, va, vb),
                           where=" / ".join(s for s in ((x.source if x else ""), (y.source if y else "")) if s),
                           book=books_of(x.source if x else "", y.source if y else ""),
                           refs_a=list(x.refs) if x else [], refs_b=list(y.refs) if y else [])
            item.status = ADDED if x is None else REMOVED if y is None else (CHANGED if item.changes else SAME)
            cmp.items.append(item)
    _compare_notes(a, b, cmp)
    cmp.compared = ["Each possession row, paired by section number, night and what is blocked: the section name and "
                    "its end locations, the period names, the possession windows (times and days), what "
                    "is blocked, and the remarks.",
                    "Each route's NOTES and Timetable Construction Notes, and other text outside the possession "
                    "tables (such as track patrolling plans), route by route and sentence by sentence.",
                    f"{plural(len(a.possessions), 'possession row')} and {plural(len(a.notes), 'note')} in the "
                    "original, "
                    f"{len(b.possessions)} and {len(b.notes)} in the updated."]
    cmp.not_compared = ["Page headings and footers (found by repetition: version, date, page numbers, next issue - "
                        "shown above for information), and the line of route title."]
    for side, st in (("Original", a), ("Updated", b)):
        cmp.info += [(f"{side} document", f"{name}: {what}") for name, what in st.info]
    if not a.notes and not b.notes:
        cmp.warnings.append("These Section 4 sets come from saved rule sets, which hold the possession rows only, so "
                            "notes were not compared. Choose the PDFs to compare notes as well.")
    return cmp


def _compare_notes(a: Statement, b: Statement, cmp: DocComparison):
    from .tprcompare import _compare_text

    def blocks(st: Statement):
        return [(" > ".join(x for x in (n.route, n.kind, n.scope) if x), n.text, int(n.source.rsplit("p", 1)[-1])
                 if n.source.rsplit("p", 1)[-1].isdigit() else 0, n.refs) for n in st.notes]
    _compare_text(blocks(a), blocks(b), cmp)
