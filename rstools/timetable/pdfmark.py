"""Copies of the compared Section 4 / TPR PDFs with what changed highlighted.

The updated PDFs get the changed items in yellow and the added ones in green; the original PDFs get the items that
were removed in red. Each highlight carries a note saying what changed (open it in a PDF viewer). The source files
are never touched: the copies are new files ('<name> - highlighted.pdf') in the output folder.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Callable, Dict, List, Tuple

from .doccompare import ADDED, CHANGED, REMOVED, DocComparison

COLOURS = {CHANGED: "FFEB3B", ADDED: "8BE08B", REMOVED: "FF8A8A"}
WORDS = {CHANGED: "Changed", ADDED: "Added", REMOVED: "Removed"}
Mark = Tuple[Tuple[float, float, float, float], str, str]           # (rect, colour, note)


def _note(item) -> str:
    if item.status == CHANGED:
        text = "; ".join(f"{n}: {o or '-'} -> {u or '-'}" for n, o, u in item.changes)
    else:
        text = "; ".join(f"{n}: {o or u}" for n, o, u in item.fields if o or u)
    return f"{WORDS[item.status]} - {item.label}. {text}"[:1500]


def marks_by_file(cmp: DocComparison) -> Tuple[Dict[str, Dict[int, List[Mark]]], Dict[str, Dict[int, List[Mark]]], int]:
    """({original path: {page index: marks}}, {updated path: {...}}, items with nowhere to put a highlight)."""
    old: Dict[str, Dict[int, List[Mark]]] = defaultdict(lambda: defaultdict(list))
    new: Dict[str, Dict[int, List[Mark]]] = defaultdict(lambda: defaultdict(list))
    lost = 0
    for it in cmp.items:
        if it.status == REMOVED:
            refs, side = it.refs_a, old
        elif it.status in (CHANGED, ADDED):
            refs, side = it.refs_b, new
        else:
            continue
        if not refs:
            lost += 1
            continue
        note = _note(it)
        for path, page, rect in refs:
            side[path][page].append((tuple(rect), COLOURS[it.status], note))      # type: ignore[arg-type]
    return old, new, lost


def _annotate(src: str, dest: str, pages: Dict[int, List[Mark]]) -> int:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject,
                               TextStringObject)
    reader = PdfReader(src)
    writer = PdfWriter(clone_from=reader)
    count = 0
    for pno, marks in pages.items():
        if not 0 <= pno < len(writer.pages):
            continue
        refs = ArrayObject()
        for (x0, y0, x1, y1), colour, note in marks:
            lo_x, hi_x, lo_y, hi_y = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
            annot = DictionaryObject({
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Highlight"),
                NameObject("/Rect"): ArrayObject(FloatObject(v) for v in (lo_x, lo_y, hi_x, hi_y)),
                NameObject("/QuadPoints"): ArrayObject(FloatObject(v) for v in (
                    lo_x, hi_y, hi_x, hi_y, lo_x, lo_y, hi_x, lo_y)),
                NameObject("/C"): ArrayObject(FloatObject(int(colour[i:i + 2], 16) / 255) for i in (0, 2, 4)),
                NameObject("/Contents"): TextStringObject(note),
                NameObject("/T"): TextStringObject("Train Planning Tools"),
                NameObject("/F"): NumberObject(4),
            })
            refs.append(writer._add_object(annot))
            count += 1
        page = writer.pages[pno]
        existing = page.get("/Annots")
        existing = existing.get_object() if existing is not None else ArrayObject()
        existing.extend(refs)
        page[NameObject("/Annots")] = existing
    with open(dest, "wb") as fh:
        writer.write(fh)
    return count


def highlight_pdfs(cmp: DocComparison, out_dir: str, log: Callable[[str], None] = lambda m: None) -> List[str]:
    """Write the highlighted copies; returns their paths."""
    from rstools.fsutil import atomic_path, unique_stem
    old, new, lost = marks_by_file(cmp)
    out: List[str] = []
    for label, files, marks in (("original", cmp.first, old), ("updated", cmp.second, new)):
        for src in files:
            pages = marks.get(src)
            if not pages:
                log(f"No highlights needed in the {label} PDF {os.path.basename(src)}.")
                continue
            base = os.path.splitext(os.path.basename(src))[0]
            stem = unique_stem(out_dir, f"{base} - highlighted", (".pdf",))
            dest = os.path.join(out_dir, stem + ".pdf")
            try:
                with atomic_path(dest) as tmp:
                    n = _annotate(src, tmp, pages)
            except Exception as exc:
                log(f"WARNING: could not highlight {os.path.basename(src)} ({exc}).")
                continue
            log(f"Saved: {dest} ({n} highlight(s))")
            out.append(dest)
    if lost:
        log(f"{lost} change(s) could not be placed in a PDF (rule sets saved without the PDFs, or text the reader "
            "could not locate): they are in the Excel report only.")
    if not out and not lost:
        log("No PDFs to highlight: nothing changed.")
    return out
