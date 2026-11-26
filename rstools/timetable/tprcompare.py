"""Two sets of Timetable Planning Rules (TPR) PDFs compared: every table row and every paragraph.

Tables are paired by section heading and title (section numbers left out, so a renumbered section still pairs),
then rows by their first column (with the next column where the first repeats). Each cell is compared under its
column heading. Paragraphs outside tables are compared section by section, sentence by sentence, so an edited
note shows as changed rather than as one removed and one added. Running headers, footers and page numbers are
not compared.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple, cast

from .doccompare import ADDED, CHANGED, REMOVED, SAME, DocComparison, DocItem, norm
from .tpr import Table, TPRDoc


def _plain_heading(text: str) -> str:
    """A section path without its numbers ('5 Running Times > 5.3 Junction Margins' -> 'running times > junction
    margins'), so a renumbered section still pairs."""
    parts = [re.sub(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\d*(?:\.\d+)*)\s+", "", p) for p in (text or "").split(" > ")]
    return norm(" > ".join(parts)).lower()


def _table_id(t: Table) -> str:
    return f"{_plain_heading(t.section)}|{norm(t.title).lower() or ' / '.join(norm(h).lower() for h in t.headers)}"


def _labels(t: Table) -> List[str]:
    """A name for each row: its first cell, or (where a merged first cell leaves it blank) the one above."""
    out, carry = [], ""
    for r in t.rows:
        first = norm(r[0]) if r else ""
        carry = first or carry
        out.append(first or carry or "(row)")
    return out


def _cells(t: Table, row: List[str]) -> Dict[str, str]:
    heads = [norm(h) or f"Column {i + 1}" for i, h in enumerate(t.headers)]
    out: Dict[str, str] = {}
    for i, v in enumerate(row):
        name = heads[i] if i < len(heads) else f"Column {i + 1}"
        out[name] = norm(v) if name not in out else out[name] + " " + norm(v)
    return out


def _sentences(text: str) -> List[str]:
    return [s for s in (norm(x) for x in re.split(r"(?<=[.;:])\s+(?=[A-Z0-9(])", text)) if s]


def compare_tprs(a: TPRDoc, b: TPRDoc) -> DocComparison:
    cmp = DocComparison("TPR", list(a.files), list(b.files), warnings=list(a.warnings) + list(b.warnings))
    _compare_tables(a.tables, b.tables, cmp)
    _compare_text(a.paragraphs, b.paragraphs, cmp)
    cmp.compared = ["Every table row: tables paired by section heading and table title, rows by their first "
                    "column, and each cell compared under its column heading (times, locations, values, notes).",
                    "Every paragraph and note outside the tables, section by section, sentence by sentence.",
                    f"{len(a.tables)} table(s) and {len(a.paragraphs)} paragraph(s) in the original, "
                    f"{len(b.tables)} and {len(b.paragraphs)} in the updated."]
    cmp.not_compared = ["Running page headers and footers (found by repetition, whatever the page size), page numbers, "
                        "contents pages, and section numbers in headings (so a renumbered section still pairs)."]
    for side, doc in (("Original", a), ("Updated", b)):
        cmp.info += [(f"{side} document", f"{name}: {what}") for name, what in doc.info]
        cmp.not_compared += [f"{side}: {note}" for note in doc.skipped]
        if doc.deleted:
            cmp.not_compared.append(f"{side}: {doc.deleted} piece(s) of text deleted in the issue (green, struck "
                                    "through) were ignored, so the document is compared as its final wording.")
    return cmp


def _by_id(tables: Sequence[Table]) -> Dict[str, List[Table]]:
    out: Dict[str, List[Table]] = defaultdict(list)
    for t in tables:
        out[_table_id(t)].append(t)
    return out


def _align(x: Table, y: Table):
    """Pair the rows of two versions of a table in sequence: [(row index in x or None, row index in y or None)].
    Runs of identical rows stay together; in a block that changed, rows with the same first cell are paired first
    and the rest in order, so one edited, inserted or deleted row never shifts the pairing of the others (first
    cells repeat a lot in real tables, so they cannot be keys)."""
    ra = [tuple(norm(c) for c in r) for r in x.rows]
    rb = [tuple(norm(c) for c in r) for r in y.rows]
    out: List[Tuple[Optional[int], Optional[int]]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ra, rb, autojunk=False).get_opcodes():
        if op == "equal":
            out += list(zip(range(i1, i2), range(j1, j2)))
            continue
        left, right = list(range(i1, i2)), list(range(j1, j2))
        pairs: List[Tuple[Optional[int], Optional[int]]] = []
        for i in list(left):
            first = ra[i][0] if ra[i] else ""
            j = next((j for j in right if first and rb[j] and rb[j][0] == first), None)
            if j is not None:
                pairs.append((i, j))
                left.remove(i)
                right.remove(j)
        for i in list(left):                    # a first cell edited a little ('Brighton Jn' -> 'Brighton Jn.')
            first = ra[i][0] if ra[i] else ""
            best, score = None, 0.0
            for j in right:
                other = rb[j][0] if rb[j] else ""
                ratio = 1.0 if not first and not other else difflib.SequenceMatcher(None, first, other).ratio()
                if ratio >= 0.5 and ra[i][1:] == rb[j][1:] and any(ra[i][1:]):
                    ratio = max(ratio, 0.75)            # only the identifier changed ('4' -> '4A')
                if ratio > score:
                    best, score = j, ratio
            if best is not None and score >= 0.75:
                pairs.append((i, best))
                left.remove(i)
                right.remove(best)
        pairs += [(i, None) for i in left] + [(None, j) for j in right]
        out += sorted(pairs, key=lambda p: (p[0] if p[0] is not None else i2, p[1] if p[1] is not None else j2))
    return out


def _compare_tables(left: Sequence[Table], right: Sequence[Table], cmp: DocComparison):
    la, lb = _by_id(left), _by_id(right)
    order = list(dict.fromkeys([_table_id(t) for t in left] + [_table_id(t) for t in right]))
    for tid in order:
        ta, tb = la.get(tid, []), lb.get(tid, [])
        for n in range(max(len(ta), len(tb))):
            x = ta[n] if n < len(ta) else None
            y = tb[n] if n < len(tb) else None
            ref = x or y
            assert ref is not None
            group = " - ".join(s for s in (norm(ref.section), norm(ref.title)) if s) or "Table"
            names_a, names_b = (_labels(x) if x else []), (_labels(y) if y else [])
            if x is not None and y is not None:
                pairs = _align(x, y)
            else:
                pairs = [(i, None) for i in range(len(x.rows))] if x is not None else \
                    [(None, j) for j in range(len(cast(Table, y).rows))]
            seen: Counter = Counter()
            for i, j in pairs:
                va = _cells(cast(Table, x), x.rows[i]) if x is not None and i is not None else {}
                vb = _cells(cast(Table, y), y.rows[j]) if y is not None and j is not None else {}
                names = list(dict.fromkeys(list(va) + list(vb)))
                label = names_b[j] if j is not None else names_a[cast(int, i)]
                seen[label] += 1
                where = " / ".join(f"p{','.join(map(str, t.pages))}" for t in (x, y) if t is not None)
                item = DocItem(f"T|{tid}|{n}|{label.lower()}|{seen[label]}", group, label,
                               fields=[(c, va.get(c, ""), vb.get(c, "")) for c in names], where=where)
                item.status = ADDED if i is None else REMOVED if j is None else CHANGED if item.changes else SAME
                cmp.items.append(item)


def _compare_text(left: Sequence[Tuple[str, str, int]], right: Sequence[Tuple[str, str, int]], cmp: DocComparison):
    def by_section(paras):
        out: Dict[str, Tuple[str, List[Tuple[str, int]]]] = {}
        for sec, text, page in paras:
            key = _plain_heading(sec)
            head, sents = out.setdefault(key, (norm(sec), []))
            sents += [(s, page) for s in _sentences(text)]
        return out
    sa, sb = by_section(left), by_section(right)
    for key in dict.fromkeys(list(sa) + list(sb)):
        head = (sa.get(key) or sb.get(key) or ("", []))[0] or "Text before the first heading"
        xa: List[Tuple[str, int]] = (sa.get(key) or ("", []))[1]
        xb: List[Tuple[str, int]] = (sb.get(key) or ("", []))[1]
        ta, tb = [s for s, _p in xa], [s for s, _p in xb]
        n = 0
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
            if op == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    n += 1
                    cmp.items.append(DocItem(f"P|{key}|{n}", head, _short(ta[i]), SAME, [("Text", ta[i], tb[j])],
                                             f"p{xa[i][1]} / p{xb[j][1]}"))
                continue
            pairs = list(zip(range(i1, i2), range(j1, j2))) if op == "replace" else []
            for i, j in pairs:
                n += 1
                cmp.items.append(DocItem(f"P|{key}|{n}", head, _short(ta[i]), CHANGED, [("Text", ta[i], tb[j])],
                                         f"p{xa[i][1]} / p{xb[j][1]}"))
            for i in range(i1 + len(pairs), i2):
                n += 1
                cmp.items.append(DocItem(f"P|{key}|{n}", head, _short(ta[i]), REMOVED, [("Text", ta[i], "")],
                                         f"p{xa[i][1]}"))
            for j in range(j1 + len(pairs), j2):
                n += 1
                cmp.items.append(DocItem(f"P|{key}|{n}", head, _short(tb[j]), ADDED, [("Text", "", tb[j])],
                                         f"p{xb[j][1]}"))


def _short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"
