"""Comparing two sets of rule documents (Section 4, TPR): the shared result and its report.

Each document is read into keyed items (a Section 4 possession row, a TPR table row or paragraph). Items are
paired by key and their fields compared; the report lists what changed (old -> new), what was added and what was
removed. The Live View shows the same result.
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

CHANGED, ADDED, REMOVED, SAME = "changed", "added", "removed", "same"


_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = re.compile(rf"\b\d{{1,2}}\s*[/.\-]\s*\d{{1,2}}\s*[/.\-]\s*\d{{2,4}}\b"
                   rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?:\s*,?\s*\d{{4}})?"
                   rf"|\b{_MONTH}\s+(?:\d{{1,2}}(?:st|nd|rd|th)?,?\s+)?\d{{4}}\b"
                   rf"|\b20\d\d\s*[/-]\s*\d{{2,4}}\b", re.I)
_WORDS = {"junction": "jn", "jcn": "jn", "jct": "jn", "street": "st", "road": "rd", "station": "stn", "sta": "stn",
          "approx": "approximately", "no": "no"}


def content_tokens(text: str) -> List[str]:
    """The words of a text as compared between two issues: dates blanked out (a new issue's dates always move),
    case, punctuation and spacing ignored, and common abbreviations unified."""
    t = _DATE.sub(" ", (text or "").replace("&", " and "))
    t = norm(t).lower()
    return [_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", t)]


def content_key(text: str) -> str:
    return " ".join(content_tokens(text))


def same_text(a: str, b: str) -> bool:
    """True when two texts say the same thing: equal as content_tokens, or differing only by a spelling slip in a
    word (never in a number: times, section numbers, platforms and line numbers must match exactly)."""
    ta, tb = content_tokens(a), content_tokens(b)
    if ta == tb or "".join(ta) == "".join(tb):
        return True
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if any(ch.isdigit() for ch in x + y) or len(x) < 4 or len(y) < 4:
            return False
        if difflib.SequenceMatcher(None, x, y).ratio() < 0.85:
            return False
    return True


_BOOK_NOISE = re.compile(r"\b(?:20\d\d(?:[-/]\d{2,4})?|v\d+(?:\.\d+)?|issue\s*\d+|s4|tpr|eas|timetable|planning|"
                         r"rules|section|standard|possession|opportunities|pdf)\b", re.I)


def book_of(source: str) -> str:
    """The book (region) a file or a 'file pN' source is from: '2027 EAS V4 S4 - EC.pdf p12' -> 'EC'."""
    name = os.path.splitext(os.path.basename(re.sub(r"\s+p\d+(?:[,-]\d+)*$", "", source or "")))[0]
    name = _BOOK_NOISE.sub(" ", name)
    name = re.sub(r"[_\-\s]+", " ", name).strip()
    return name


def books_of(*sources: str) -> str:
    out = []
    for s in sources:
        b = book_of(s)
        if b and b not in out:
            out.append(b)
    return " / ".join(out)


@dataclass
class DocItem:
    key: str                                # stable identity ('110.3 MID WEEK #1', 'Headways | Brighton | ...')
    group: str                              # what it belongs to (line of route, TPR section and table)
    label: str                              # how it is named in lists
    status: str = SAME
    fields: List[Tuple[str, str, str]] = field(default_factory=list)    # (field, original, updated), every field
    where: str = ""                         # file and page(s), e.g. 'KS.pdf p12 / KS v2.pdf p13'
    book: str = ""                          # the region the item is from ('EC', 'KS / EC')
    refs_a: List[Tuple] = field(default_factory=list)    # where it is in the original PDFs: (path, page, rect)
    refs_b: List[Tuple] = field(default_factory=list)    # ...and in the updated ones

    @property
    def changes(self) -> List[Tuple[str, str, str]]:
        return [f for f in self.fields if f[1] != f[2] and not same_text(f[1], f[2])]


@dataclass
class DocComparison:
    kind: str                               # 'Section 4' / 'TPR'
    first: List[str]                        # the files on each side
    second: List[str]
    items: List[DocItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    compared: List[str] = field(default_factory=list)       # what was compared, in words
    not_compared: List[str] = field(default_factory=list)   # what was left out (headers and the like)
    info: List[Tuple[str, str]] = field(default_factory=list)   # (label, text): what the documents' headers say

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
                rows.append([it.book, it.group, it.label, name, old or "-", new or "-", it.where])
    add_sheet(wb, "Changes", ["Book", "Where", "Item", "What changed", "Original", "Updated", "Pages"], rows,
              [12, 36, 34, 20, 50, 50, 26])
    for title, status, side in (("Added", ADDED, 2), ("Removed", REMOVED, 1)):
        part = []
        for it in cmp.items:
            if it.status == status:
                values = [(n, o if side == 1 else u) for n, o, u in it.fields]
                part.append([it.book, it.group, it.label, "; ".join(f"{n}: {v}" for n, v in values if v), it.where])
        add_sheet(wb, title, ["Book", "Where", "Item", "Details", "Pages"], part, [12, 36, 34, 100, 26])
    audit = [["Original", "; ".join(os.path.basename(f) for f in cmp.first)],
             ["Updated", "; ".join(os.path.basename(f) for f in cmp.second)]]
    audit += [[label, text] for label, text in cmp.info]
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
