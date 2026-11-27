"""Run a timetable comparison: read the inputs (in parallel where it pays), compare, save.

Three comparisons share one entry point:

* ``timetables`` - GTR timetable check workbook against the Network Rail timetable (the reference),
  written into the approved 'Consolidated TT Comparison' template;
* ``print_tt`` / ``list_tt`` - Attune train prints / an Attune train list as the reference, against a
  timetable (GTR or Network Rail), by the same rules and into the same template;
* ``prints``     - two sets of train prints (PDF / Word);
* ``lists``      - two Attune train list exports (Excel / CSV);
* ``s4docs``     - two sets of Network Rail Section 4 PDFs (times, dates, locations and notes);
* ``tprs``       - two sets of Timetable Planning Rules PDFs (every table row and paragraph).
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import Callable, List, Optional, Sequence

from rstools.docexport import ext_for
from rstools.naming import clip, compare_name

MODES = ("timetables", "print_tt", "list_tt", "prints", "lists", "s4docs", "tprs")
PARALLEL_BYTES = 4 * 1024 * 1024        # below this, starting helper processes costs more than it saves


class TimetableRunError(Exception):
    pass


@dataclass
class RunResult:
    path: str
    lines: List[str] = field(default_factory=list)      # summary for the log
    warnings: List[str] = field(default_factory=list)
    differences: int = 0
    extra: List[str] = field(default_factory=list)      # other files saved (the highlighted PDFs)


def _workers(paths: Sequence[str]) -> int:
    """Helper processes for reading `paths`: one per file, leaving a core free for the window."""
    try:
        size = sum(os.path.getsize(p) for p in paths)
    except OSError:
        return 0
    cores = os.cpu_count() or 1
    if len(paths) < 2 or cores < 2 or size < PARALLEL_BYTES:
        return 0
    return min(len(paths), cores - 1)


def read_all(reader: Callable, paths: Sequence[str], step: Optional[Callable[[int, int], None]] = None) -> list:
    """reader(path) for every path, across CPU cores when the files are big enough to benefit.
    Falls back to reading here if helper processes cannot be started. Results keep the input order.
    step(done, total) is called as each file is read (for the progress bar)."""
    return read_jobs([(reader, p) for p in paths], step)


def _reading(p, start: float, end: float):
    """A step callback moving the progress bar from `start` to `end` as files are read."""
    return lambda done, total: p(start + (end - start) * done / max(total, 1), f"Read {done} of {total} file(s)...")


def read_jobs(jobs: Sequence[tuple], step: Optional[Callable[[int, int], None]] = None) -> list:
    """reader(path) for each (reader, path), in parallel when it pays; results in the same order.
    A file read before and unchanged since (same time stamp and size) is not read again - the Live
    view re-compares within a moment of one file being saved."""
    from rstools import filecache
    out: list = [None] * len(jobs)
    todo = []
    for i, (reader, path) in enumerate(jobs):
        key, stamp = filecache.key_of(reader, path)
        hit = filecache.get(key, stamp)
        if hit is not None:
            out[i] = hit
        else:
            todo.append((i, reader, path, key, stamp))
    total, cached = len(jobs), len(jobs) - len(todo)
    if todo:
        each = (lambda n: step(cached + n, total)) if step else None
        results = _read_jobs([(reader, path) for _i, reader, path, _k, _s in todo], each)
        for (i, _reader, _path, key, stamp), res in zip(todo, results):
            out[i] = res
            filecache.put(key, stamp, res)
    return out


def _sendable(reader) -> bool:
    """Whether a reader can run in a helper process (it must be a module-level function)."""
    import pickle
    try:
        pickle.dumps(reader)
        return True
    except Exception:
        return False


def _read_jobs(jobs: Sequence[tuple], each: Optional[Callable[[int], None]] = None) -> list:
    paths = [p for _r, p in jobs]
    workers = _workers(paths)
    if workers:
        try:
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
        except Exception:
            pool = None
        if pool is not None and not all(_sendable(reader) for reader, _p in jobs):
            pool.shutdown()                            # a reader that cannot go to a helper: read here
            pool = None
        if pool is not None:
            try:
                futures = [pool.submit(reader, p) for reader, p in jobs]
                out = []
                for (reader, p), fut in zip(jobs, futures):
                    try:
                        out.append(fut.result())
                        if each:
                            each(len(out))
                    except (OSError, RuntimeError, EOFError) as exc:
                        if type(exc).__name__ == "BrokenProcessPool" or isinstance(exc, EOFError):
                            out.append(reader(p))              # helper died: read this one here
                            if each:
                                each(len(out))
                        else:
                            raise
                return out
            finally:
                pool.shutdown(cancel_futures=True)
    out = []
    for reader, p in jobs:
        out.append(reader(p))
        if each:
            each(len(out))
    return out


def default_name(mode: str, first: Sequence[str], second: Sequence[str]) -> str:
    """Default output name. The timetable comparison's name comes from the NR timetable identifier,
    known once it has been read, so it is filled in when the run starts."""
    if mode in ("timetables", "print_tt", "list_tt"):
        return ""
    a, b = (first[0] if first else ""), (second[0] if second else "")
    what = {"prints": "Train Print Comparison", "s4docs": "Section 4 Comparison",
            "tprs": "TPR Comparison"}.get(mode, "Train List Comparison")
    return clip(f"{compare_name(a, b)} {what}") if a and b else ""


def _out(folder: str, name: str, fmt: str) -> str:
    """The output path: shortened if needed so Excel can open it, and never over an existing file."""
    from rstools.fsutil import unique_stem             # also makes the name a safe file name
    name = name.strip() or "Comparison"
    return os.path.join(folder, unique_stem(folder, name, (ext_for(fmt),)) + ext_for(fmt))


def _check(first: Sequence[str], second: Sequence[str]):
    first, second = [f for f in first if f], [f for f in second if f]
    if not first or not second:
        raise TimetableRunError("Choose the files on both sides of the comparison.")
    for f in list(first) + list(second):
        if not os.path.isfile(f):
            raise TimetableRunError(f"This file could not be found:\n{f}")
    return first, second


def compare_files(mode: str, first: Sequence[str], second: Sequence[str],
                  progress: Optional[Callable[[float, str], None]] = None,
                  log: Optional[Callable[[str], None]] = None, passenger_only: bool = False):
    """Read and compare (no output written). Returns the comparison object: a timetable Comparison for
    'timetables' / 'print_tt' / 'list_tt', a PrintComparison for 'prints', a ListComparison for 'lists'.
    Used by the comparison runs and by the Live View, so both always agree."""
    p = progress or (lambda _f, _m: None)
    lg = log or (lambda _m: None)
    first, second = _check(first, second)
    if mode == "timetables":
        return _cmp_timetables(first[0], second[0], p, lg)
    if mode in ("print_tt", "list_tt"):
        return _cmp_base(mode, first, second[0], p, lg)
    if mode == "prints":
        return _cmp_prints(first, second, p, lg, passenger_only)
    if mode == "lists":
        return _cmp_lists(first[0], second[0], p, lg)
    if mode in ("s4docs", "tprs"):
        return _cmp_docs(mode, first, second, p, lg)
    raise TimetableRunError(f"Unknown comparison '{mode}'.")


def run(mode: str, first: Sequence[str], second: Sequence[str], out_dir: str, name: str = "", fmt: str = "xlsx",
        progress: Optional[Callable[[float, str], None]] = None,
        log: Optional[Callable[[str], None]] = None, passenger_only: bool = False,
        highlight_pdfs: bool = False) -> RunResult:
    """Compare and save. `passenger_only` (train prints): leave out passing times and calls without a public
    time, for prints where one side does not show the intermediate timing points. `highlight_pdfs` (Section 4 and
    TPR comparisons): also save copies of the PDFs with what changed highlighted."""
    p = progress or (lambda _f, _m: None)
    lg = log or (lambda _m: None)
    first, second = _check(first, second)
    if not out_dir or not os.path.isdir(out_dir):
        raise TimetableRunError(f"The output folder does not exist:\n{out_dir or '(none chosen)'}")
    cmp = compare_files(mode, first, second, p, lg, passenger_only)
    p(0.8, "Writing the comparison...")
    if mode == "prints":
        from .prints import build_workbook
        path = _out(out_dir, clip(name or default_name("prints", first, second)), fmt)
        _save(build_workbook(cmp), path)
        changed = sum(1 for pr in cmp.pairs if pr[3])
        lines = [f"{len(cmp.pairs)} train(s) paired: {changed} changed, {len(cmp.pairs) - changed} unchanged",
                 f"{len(cmp.added)} added, {len(cmp.removed)} removed, {len(cmp.changes)} individual change(s)"]
        return RunResult(path, lines, list(cmp.warnings), len(cmp.changes) + len(cmp.added) + len(cmp.removed))
    if mode == "lists":
        from .trainlist import build_workbook as lists_workbook
        path = _out(out_dir, clip(name or default_name("lists", first, second)), fmt)
        _save(lists_workbook(cmp), path)
        changed = len({i for i, *_ in cmp.changes})
        lines = [f"{len(cmp.pairs)} train(s) paired by {', '.join(cmp.key_headers)}"
                 + (f" ({cmp.retimed} retimed, paired by {', '.join(cmp.loose_headers)})" if cmp.retimed else "")
                 + f": {changed} changed",
                 f"{len(cmp.added)} added, {len(cmp.removed)} removed, {len(cmp.changes)} changed cell(s)"]
        return RunResult(path, lines, list(cmp.warnings), len(cmp.changes) + len(cmp.added) + len(cmp.removed))
    if mode in ("s4docs", "tprs"):
        from .doccompare import build_workbook as docs_workbook, summary_lines as doc_lines
        path = _out(out_dir, clip(name or default_name(mode, first, second)), fmt)
        _save(docs_workbook(cmp), path)
        diffs = sum(1 for i in cmp.items if i.status != "same")
        extra: List[str] = []
        if highlight_pdfs:
            from .pdfmark import highlight_pdfs as make_highlights
            p(0.9, "Highlighting the PDFs...")
            extra = make_highlights(cmp, os.path.dirname(path), lg)
        return RunResult(path, doc_lines(cmp), list(cmp.warnings), diffs, extra)
    from .output import build_workbook as timetable_workbook, document_sections, output_name, summary_lines
    path = _out(out_dir, clip(name or output_name(cmp)), fmt)
    wb = timetable_workbook(cmp)
    _save(wb, path, None if path.endswith(".xlsx") else document_sections(wb))
    diffs = sum(len(r.missing) + len(r.gaps) + len(r.headcode_mismatches) + sum(len(m.issues) for m in r.matched)
                for r in cmp.sections)
    return RunResult(path, summary_lines(cmp), list(cmp.warnings), diffs)


def _save(wb, path: str, sections=None):
    from .xlstyle import save
    from rstools.fsutil import save_output
    save_output(lambda: save(wb, path, os.path.splitext(os.path.basename(path))[0], sections), path,
                TimetableRunError)


def _cmp_timetables(gtr_path, nr_path, p, lg):
    from .compare import compare_timetables
    from .parse import read_timetable
    p(0.05, "Reading the two timetables...")
    lg(f"Reading {os.path.basename(gtr_path)} and {os.path.basename(nr_path)}")
    gtr, nr = read_all(read_timetable, [gtr_path, nr_path], _reading(p, 0.05, 0.4))
    if gtr.identifier and not nr.identifier:            # chosen the other way round
        gtr, nr = nr, gtr
        lg("WARNING: the files looked to be the other way round (the Network Rail table was in the GTR box) "
           "- they have been swapped.")
    for label, tt in (("GTR", gtr), ("Network Rail", nr)):
        lg(f"{label}: {os.path.basename(tt.path)} - " + ", ".join(
            f"{sec} {len(trains)}" for sec, trains in tt.sections.items()) + " trains")
    p(0.45, "Matching trains...")
    cmp = compare_timetables(gtr, nr)
    for w in cmp.warnings:
        lg("WARNING: " + w)
    return cmp


def _cmp_prints(first, second, p, lg, passenger_only=False):
    from .prints import compare_prints, read_print
    p(0.05, "Reading the train prints...")
    lg(f"Reading {len(first)} original and {len(second)} updated print file(s)")
    results = read_all(read_print, list(first) + list(second), _reading(p, 0.05, 0.6))
    orig = [t for r in results[:len(first)] for t in r]
    upd = [t for r in results[len(first):] for t in r]
    warnings = []
    for path, trains in zip(list(first) + list(second), results):
        lg(f"{os.path.basename(path)}: {len(trains)} train(s)")
        if not trains:
            warnings.append(f"{os.path.basename(path)}: no trains were recognised (no heading lines with a "
                            "headcode and a UID or the word 'Train'). Check it is a train print.")
        lost = [(t.ident or t.headcode, line) for t in trains for line in getattr(t, "skipped", [])]
        if lost:
            warnings.append(f"{os.path.basename(path)}: {len(lost)} location line(s) could not be read (a time "
                            "printed on to the station name), so those calls are not compared - check them by eye "
                            "(e.g. " + "; ".join(f"{tid}: '{line}'" for tid, line in lost[:3]) + ").")
    if not orig or not upd:
        raise TimetableRunError("No trains were recognised on one side of the comparison.\n\n"
                                + "\n".join(warnings))
    if {bool(t.kind) for t in orig} != {bool(t.kind) for t in upd}:
        if any(not t.kind and not t.info for t in orig + upd):
            raise TimetableRunError("A VPT export can be compared with Attune 'Single Train Report' prints, which name "
                                    "every location and time, but not with other kinds of train print.")
        warnings.append("A VPT export has no public times or activities, and lays out lines, dwells and allowances "
                        "differently from a train print, so against a print only the calls, working times, "
                        "platforms, days, train ID and dates are compared.")
    p(0.5, "Comparing trains...")
    cmp = compare_prints(orig, upd, warnings, passenger_only)
    for w in warnings:
        lg("WARNING: " + w)
    return cmp


def _cmp_lists(a_path, b_path, p, lg):
    from .trainlist import compare_train_lists, describe, read_train_list
    p(0.05, "Reading the train lists...")
    a, b = read_all(read_train_list, [a_path, b_path], _reading(p, 0.05, 0.45))
    lg(describe(a))
    lg(describe(b))
    p(0.5, "Comparing trains...")
    cmp = compare_train_lists(a, b)
    if cmp.only_original or cmp.only_updated:
        cmp.warnings.append("Columns in only one list are not compared: "
                            + ", ".join(cmp.only_original + cmp.only_updated))
    for w in cmp.warnings:
        lg("WARNING: " + w)
    return cmp


def read_section4_pdf(path: str):
    """One Section 4 PDF's possessions (a module-level reader, so it can run in a helper process)."""
    from .section4 import read_statement
    return read_statement([path])


def read_tpr_pdf(path: str):
    from .tpr import read_tpr
    return read_tpr([path])


def _cmp_docs(mode, first, second, p, lg):
    from .section4 import Section4Error, Statement
    from .tpr import TPRDoc, TPRError
    s4 = mode == "s4docs"
    p(0.05, "Reading the documents...")
    lg(f"Reading {len(first)} original and {len(second)} updated PDF(s)")
    try:
        results = read_all(read_section4_pdf if s4 else read_tpr_pdf, list(first) + list(second),
                           _reading(p, 0.05, 0.6))
    except (Section4Error, TPRError) as exc:
        raise TimetableRunError(str(exc))
    sides = []
    for paths, res in ((first, results[:len(first)]), (second, results[len(first):])):
        if s4:
            st = Statement()
            for path, r in zip(paths, res):
                st.possessions += r.possessions
                st.notes += r.notes
                st.info += r.info
                st.files.append(path)
                st.warnings += r.warnings
                lg(f"{os.path.basename(path)}: {len(r.possessions)} possession row(s)")
            sides.append(st)
        else:
            doc = TPRDoc()
            for path, r in zip(paths, res):
                doc.tables += r.tables
                doc.paragraphs += r.paragraphs
                doc.para_refs += r.para_refs
                doc.info += r.info
                doc.skipped += r.skipped
                doc.deleted += r.deleted
                doc.files.append(path)
                doc.warnings += r.warnings
                lg(f"{os.path.basename(path)}: {len(r.tables)} table(s), {len(r.paragraphs)} paragraph(s)")
            sides.append(doc)
    if s4 and (not sides[0].possessions or not sides[1].possessions):
        raise TimetableRunError("No Section 4 possessions were found on one side. Use Network Rail's Engineering "
                                "Access Statement Section 4 (Standard Possession Opportunities) PDFs.")
    if not s4 and any(not (d.tables or d.paragraphs) for d in sides):
        raise TimetableRunError("Nothing could be read from the TPR PDFs on one side (scanned images?).")
    p(0.5, "Comparing...")
    if s4:
        from .s4compare import compare_statements
        cmp = compare_statements(sides[0], sides[1])
    else:
        from .tprcompare import compare_tprs
        cmp = compare_tprs(sides[0], sides[1])
    for w in cmp.warnings:
        lg("WARNING: " + w)
    return cmp


def read_attune_print(path: str) -> list:
    """The trains of an Attune Single Train Report print (the only print layout with public times)."""
    from .attune_print import is_attune_report, parse_attune
    from .prints import PrintError, read_pages
    if os.path.splitext(path)[1].lower() == ".vpt":
        raise PrintError(f"'{os.path.basename(path)}' is a VPT export, which has no public times, so it cannot be "
                         "checked against a timetable. Use the Attune 'Single Train Report' print (PDF or Word).")
    pages = read_pages(path)
    if not is_attune_report(pages):
        raise PrintError(f"'{os.path.basename(path)}' is not an Attune 'Single Train Report' print. That layout is "
                         "needed to compare with a timetable, because it shows each train's public times.")
    return parse_attune(pages, os.path.basename(path))


def _cmp_base(mode, base_paths, tt_path, p, lg):
    from rstools.naming import short_label
    from .base import build_base, learn_tiplocs, trains_from_list, trains_from_prints
    from .compare import compare_timetables
    from .parse import read_timetable
    from .trainlist import describe, read_train_list
    prints = mode == "print_tt"
    p(0.05, "Reading the files...")
    lg(f"Reading {len(base_paths)} base file(s) and {os.path.basename(tt_path)}")
    reader = read_attune_print if prints else read_train_list
    results = read_jobs([(reader, b) for b in base_paths] + [(read_timetable, tt_path)])
    other = results[-1]
    from .parse import has_halves
    working = has_halves(other)         # a working timetable (half minutes): compare to the half minute
    if working:
        lg("The timetable shows half minutes, so working times are compared to the half minute.")
    if prints:
        atrains = [t for r in results[:-1] for t in r]
        for path, r in zip(base_paths, results[:-1]):
            lg(f"{os.path.basename(path)}: {len(r)} train(s), {sum(t.public for t in r)} with public times")
        learn_tiplocs(atrains)
        trains, notes = trains_from_prints(atrains, working)
        from .attune_print import skipped_note
        lost = skipped_note(atrains)
        if lost:
            notes.append(lost)
            lg("WARNING: " + lost)
        base_label, base_name = "Print", "train print(s)"
    else:
        lg(describe(results[0]))
        try:
            trains, notes = trains_from_list(results[0], working)
        except ValueError as exc:
            raise TimetableRunError(str(exc))
        base_label, base_name = "Attune", "Attune train list"
    other_label, other_name = ("NR", "Network Rail timetable") if other.identifier else ("GTR", "GTR timetable")
    lg(f"{other_name}: {os.path.basename(tt_path)} - " + ", ".join(
        f"{sec} {len(ts)}" for sec, ts in other.sections.items()) + " trains")
    ident = f"{short_label(base_paths[0])} vs {other.identifier or short_label(tt_path)}"
    base = build_base(trains, other, base_paths[0], ident, notes)
    lg("Base: " + (", ".join(f"{sec} {len(ts)}" for sec, ts in base.sections.items()) or "no trains") + " trains")
    if not base.sections:
        raise TimetableRunError(f"None of the trains in the {base_name} call at a station shown in "
                                f"{os.path.basename(tt_path)}, so there is nothing to compare.\n\n"
                                "Check the right timetable was chosen.\n\n" + "\n".join(base.warnings))
    p(0.45, "Matching trains...")
    cmp = compare_timetables(other, base, base_label=base_label, other_label=other_label, base_name=base_name,
                             other_name=other_name)
    for w in cmp.warnings:
        lg("WARNING: " + w)
    return cmp
