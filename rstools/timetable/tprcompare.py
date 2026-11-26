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
from typing import Dict, List, Sequence, Tuple

from .doccompare import ADDED, CHANGED, REMOVED, SAME, DocComparison, DocItem, norm
from .tpr import Table, TPRDoc


def _plain_heading(text: str) -> str:
    return norm(re.sub(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\d*(?:\.\d+)*)\s+", "", text or "")).lower()


def _table_id(t: Table) -> str:
    return f"{_plain_heading(t.section)}|{norm(t.title).lower() or ' / '.join(norm(h).lower() for h in t.headers)}"


def _row_keys(t: Table) -> List[str]:
    firsts = Counter(norm(r[0]).lower() if r else "" for r in t.rows)
    keys: List[str] = []
    seen: Counter = Counter()
    for r in t.rows:
        k = norm(r[0]).lower() if r else ""
        if firsts[k] > 1 and len(r) > 1:
            k += " | " + norm(r[1]).lower()
        seen[k] += 1
        keys.append(k + (f" #{seen[k]}" if seen[k] > 1 else ""))
    return keys


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
    cmp.not_compared = ["Running page headers and footers (the top and bottom strip of each page), page numbers, "
                        "and section numbers in headings (so a renumbered section still pairs)."]
    return cmp


def _by_id(tables: Sequence[Table]) -> Dict[str, List[Table]]:
    out: Dict[str, List[Table]] = defaultdict(list)
    for t in tables:
        out[_table_id(t)].append(t)
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
            rows_a = dict(zip(_row_keys(x), x.rows)) if x else {}
            rows_b = dict(zip(_row_keys(y), y.rows)) if y else {}
            keys = list(dict.fromkeys(list(rows_a) + list(rows_b)))
            for k in keys:
                ra, rb = rows_a.get(k), rows_b.get(k)
                va = _cells(x, ra) if x is not None and ra is not None else {}
                vb = _cells(y, rb) if y is not None and rb is not None else {}
                names = list(dict.fromkeys(list(va) + list(vb)))
                label = norm((ra or rb or [""])[0]) or "(row)"
                where = " / ".join(f"p{','.join(map(str, t.pages))}" for t in (x, y) if t is not None)
                item = DocItem(f"T|{tid}|{n}|{k}", group, label, fields=[(c, va.get(c, ""), vb.get(c, ""))
                                                                       for c in names], where=where)
                item.status = (ADDED if ra is None else REMOVED if rb is None
                               else CHANGED if item.changes else SAME)
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
