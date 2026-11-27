"""Orchestrates a comparison run (used by the GUI and the command line)."""
from __future__ import annotations

import dataclasses
import datetime as _dt
import os
import re
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import Callable, Optional

from .days import coverage, filter_model, label as day_label
from .compare import CATEGORY_LABELS, Change, compare_models
from .loader import load_any
from .meta import is_comparison_output, read_meta_file, write_meta
from .model import CWNModel, leave_out_unread, parse_workbook, model_to_dict, model_from_dict
from rstools.docexport import ext_for
from rstools.naming import clip

from .options import Options, default_name
from .report import write_report
from .writer import apply_changes
from .xlsxfix import save_workbook

NOTHING_LEFT = ("No tabs are left to compare: every tab that could be read in one CWN could not be read in the "
                "other (see the warnings). Open the damaged file in Excel, save it and run again.")
NO_TABS = "No CWN or platform workings location tabs (with an ID / TIME heading row) were found in {}."


class RunError(Exception):
    pass


def _safe(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip().rstrip(".")
    if name.lower().endswith(".xlsx"):
        name = name[:-5]
    return clip(name) or default_name()


OUTPUT_LABELS = {"full": "Full CWN (changes highlighted and noted)",
                 "highlight": "Full CWN (new and changed items highlighted only)",
                 "acwn": "ACWN (changes only)"}


def writing_options(opts: Options) -> Options:
    """The options the output CWN is written with. 'Highlighted only' shows the updated CWN as it is, with
    anything new or changed highlighted: no previous values struck through, no change notes and no
    cancelled trains put back (they are still listed in the change report)."""
    if opts.output_type != "highlight":
        return opts
    cats = {k: dict(v, show_old=False) for k, v in opts.categories.items()}
    cats["CANCELLED"] = dict(cats.get("CANCELLED", {}), cwn=False, show_old=False)
    return dataclasses.replace(opts, categories=cats)


def output_paths(opts: Options):
    from rstools.fsutil import output_folder
    folder = output_folder(opts.output_dir)
    name = opts.output_name.strip() or default_name(opts.original, opts.updated)
    if opts.days and not opts.output_name.strip():
        name += f" ({day_label(opts.days)})"
    from rstools.fsutil import unique_stem
    tails = (".xlsx", " - Change Report" + ext_for(opts.report_format))
    stem = unique_stem(folder, _safe(name), tails)    # short enough for Excel to open; never overwrites
    return os.path.join(folder, stem + tails[0]), os.path.join(folder, stem + tails[1])


def load_model(path: str) -> CWNModel:
    """Read a CWN that is only compared (not written): read-only mode, file closed afterwards."""
    wb = load_any(path, read_only=True)
    try:
        return parse_workbook(wb)
    finally:
        close = getattr(wb, "close", None)
        if close:
            close()


def _baseline(meta: dict, path: str) -> CWNModel:
    try:
        return model_from_dict(meta["baseline"])
    except (KeyError, ValueError, TypeError) as exc:
        raise RunError(f"The comparison data inside '{os.path.basename(path)}' could not be used: {exc}")


def _save(fn, path):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fn()
    except PermissionError:
        raise RunError(f"Cannot save {path}\nThe folder may be read-only, or a file with that name is open in Excel.")
    except OSError as exc:
        hint = ("\n\nThe folder path is very long. Choose a shorter 'Save to folder' (e.g. Documents) and run "
                "again." if len(os.path.abspath(path)) > 240 else "")
        raise RunError(f"Cannot save {path}\n{exc.strerror or exc}{hint}")


def _colour_word(hex_colour: str) -> str:
    from cwn_compare.options import PRESET_COLOURS
    h = hex_colour.upper()[-6:]
    return next((n for n, v in PRESET_COLOURS.items() if v.upper() == h), "#" + h)


def _workings_finish(wb, model: CWNModel, full: Optional[CWNModel], rounds: list):
    """Platform workings only: tabs of days that were not chosen are left out, and the cover's 'UPDATES
    HIGHLIGHTED IN <colour>' line names the colours of the rounds."""
    from .days import sheet_day
    if not any(sheet_day(sh) is not None for sh in model.sheets.values()):
        return
    if full is not None:
        for key, sh in full.sheets.items():
            if key not in model.sheets and sheet_day(sh) is not None and sh.title in wb.sheetnames:
                wb.remove(wb[sh.title])
    words = list(dict.fromkeys(_colour_word(r["colour"]) for r in rounds))
    for ws in wb.worksheets:
        if ws.title in {sh.title for sh in model.sheets.values()}:
            continue
        for row in ws.iter_rows(max_row=40):
            for cell in row:
                v = cell.value
                if isinstance(v, str) and re.match(r"(?i)^\s*updates highlighted in\b", v):
                    text = "Updates highlighted in " + " and ".join(w.lower() for w in words)
                    cell.value = text.upper() if v.strip().isupper() else text


def run(opts: Options, progress: Optional[Callable[[float, str], None]] = None,
        log: Optional[Callable[[str], None]] = None) -> dict:
    def p(frac, msg):
        if progress:
            progress(frac, msg)

    def lg(msg):
        if log:
            log(msg)

    if not opts.original or not opts.updated:
        raise RunError("Choose both files.")
    for path in (opts.original, opts.updated):
        if not os.path.isfile(path):
            raise RunError(f"This file could not be found:\n{path}")
    if os.path.abspath(opts.original) == os.path.abspath(opts.updated):
        raise RunError("The two files selected are the same file.")
    if is_comparison_output(opts.updated):
        raise RunError("The updated file is a comparison output produced by this app.\n"
                       "Choose the clean updated CWN instead.")
    cumulative = opts.mode == "cumulative"

    # ---- first file: a previous comparison (use its stored clean data) or the original CWN
    p(0.02, "Reading first file...")
    lg(f"Reading {os.path.basename(opts.original)}")
    meta = read_meta_file(opts.original) if is_comparison_output(opts.original) else None
    if cumulative and not meta:
        raise RunError("The first file is not a comparison CWN generated by this app.\n"
                       "Choose a comparison CWN made earlier by this app (Stock Tools tab), or use "
                       "'Compare two CWNs' mode.")
    prev_changes, rounds = [], []
    executor = pending = None
    m_old: Optional[CWNModel] = None
    if meta:
        m_old = _baseline(meta, opts.original)
        if cumulative:
            prev_changes = [c for c in (Change.from_dict(d) for d in meta.get("changes", []))
                            if c.category in CATEGORY_LABELS]
            rounds = meta.get("rounds", [])
            lg(f"Previous comparison contains {len(rounds)} round(s) and {len(prev_changes)} change(s)")
            if opts.colour.upper()[-6:] in {r["colour"].upper()[-6:] for r in rounds}:
                lg("WARNING: the highlight colour chosen is already used by a previous round - "
                   "new changes will not be distinguishable. Consider choosing another colour.")
        else:
            lg("The original file is a comparison output - using the clean CWN data stored inside it.")
    else:
        # read the original in a second process while the updated CWN loads here (not when this run
        # is itself one of a batch running in helper processes - each already has its own core)
        import multiprocessing
        if multiprocessing.parent_process() is None:
            try:
                executor = ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"))
                pending = executor.submit(load_model, opts.original)
            except Exception:
                executor = pending = None

    # ---- updated CWN (loaded fully - it becomes the output)
    p(0.15, "Reading updated CWN...")
    lg(f"Reading {os.path.basename(opts.updated)}")
    try:
        wb_new = load_any(opts.updated, progress=lambda f: p(0.15 + 0.3 * f, "Reading updated CWN..."))
        p(0.46, "Reading the trains...")
        m_new = parse_workbook(wb_new)
        if m_old is None:
            try:
                m_old = pending.result() if pending else None
            except Exception:
                m_old = None
            if m_old is None:                  # parallel read unavailable - read it here instead
                m_old = load_model(opts.original)
    finally:
        if executor:
            executor.shutdown(cancel_futures=True)
    for w in m_old.warnings + m_new.warnings:
        lg("WARNING: " + w)
    if not m_old.sheets:
        raise RunError(NO_TABS.format("the first file"))
    if not m_new.sheets:
        raise RunError(NO_TABS.format("the updated file"))
    for w in leave_out_unread(m_old, m_new):
        lg("WARNING: " + w)
    if not m_old.sheets or not m_new.sheets:
        raise RunError(NOTHING_LEFT)
    full_old = full_new = None
    if opts.days:                                   # only the trains running on the chosen days
        base_old, guess_old = coverage(m_old, opts.original)
        base_new, guess_new = coverage(m_new, opts.updated)
        chosen = set(opts.days)
        for label, base, guess in (("original", base_old, guess_old), ("updated", base_new, guess_new)):
            lg(f"The {label} CWN covers {day_label(base)}" + (" (assumed from its DAYS codes)" if guess else ""))
            missing = chosen - base
            if missing:
                lg(f"WARNING: the {label} CWN does not cover {day_label(missing)}.")
        full_old, full_new = m_old, m_new
        m_old, m_new = filter_model(m_old, chosen, base_old), filter_model(m_new, chosen, base_new)
        lg(f"Checking {day_label(chosen)} only: {sum(len(s.blocks) for s in m_new.sheets.values())} of "
           f"{sum(len(s.blocks) for s in full_new.sheets.values())} train entries in the updated CWN run then")
    lg(f"Found {len(m_new.sheets)} location tabs, "
       f"{sum(len(s.blocks) for s in m_new.sheets.values())} train entries")

    # ---- compare
    p(0.5, "Comparing trains...")
    this_round = max((r["round"] for r in rounds), default=0) + 1
    changes = compare_models(m_old, m_new,
                             progress=lambda i, n, t: p(0.5 + 0.15 * i / max(n, 1), f"Comparing {t}..."),
                             loose=opts.ignore_spacing, full_old=full_old, full_new=full_new)
    for c in changes:
        c.round = this_round
        c.colour = opts.colour

    # carry forward earlier rounds that are still relevant
    kept_prev = []
    for c in prev_changes:
        sm = m_new.sheets.get(c.sheet)
        if sm is None:
            continue
        if c.target == "footer":                      # a berthing arrangements line of platform workings
            if any(e["label"] == c.target_key for e in sm.footer):
                kept_prev.append(c)
            continue
        present = c.block_key in sm.block_by_key()
        if (c.kind == "remove_block") != present:     # skip re-instated trains and vanished ones
            kept_prev.append(c)
    all_changes = kept_prev + changes
    lg(f"Round {this_round}: {len(changes)} change(s) found"
       + (f"; {len(kept_prev)} earlier change(s) carried forward" if cumulative else ""))

    # ---- output CWN
    p(0.7, "Writing output CWN...")
    acwn = opts.output_type == "acwn"
    summary = apply_changes(wb_new, m_new, all_changes, writing_options(opts), acwn=acwn,
                            only_blocks=bool(opts.days))
    rounds = rounds + [{
        "round": this_round, "colour": opts.colour, "created": _dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "original": os.path.basename(opts.original), "updated": os.path.basename(opts.updated),
        "days": day_label(opts.days) if opts.days else "",
    }]
    _workings_finish(wb_new, m_new, full_new, rounds)
    write_meta(wb_new, {"rounds": rounds, "baseline": model_to_dict(m_new),
                        "changes": [c.to_dict() for c in all_changes]})
    if acwn and not summary:
        lg("No changes to show - the ACWN contains only the cover/non-train tabs.")
    if not any(ws.sheet_state == "visible" for ws in wb_new.worksheets):
        wb_new.create_sheet("No Changes", 0)["A1"] = "No changes were found between the two CWNs."
    first_visible = next(i for i, ws in enumerate(wb_new.worksheets) if ws.sheet_state == "visible")
    wb_new.active = first_visible
    for i, ws in enumerate(wb_new.worksheets):
        ws.sheet_view.tabSelected = i == first_visible

    cwn_path, rep_path = output_paths(opts)
    p(0.82, "Saving output CWN...")
    _save(lambda: save_workbook(wb_new, cwn_path, trim="data",
                                progress=lambda f: p(0.82 + 0.1 * f, "Saving output CWN...")), cwn_path)
    lg(f"Saved CWN: {cwn_path}")

    result = {"cwn": cwn_path, "report": None, "changes": len(changes),
              "carried": len(kept_prev), "tabs": len(summary)}
    if opts.make_report:
        p(0.93, "Writing change report...")
        rep_changes = [c for c in all_changes if opts.cat(c.category, "report")]
        info = {
            "mode_label": ("Add a new round to an earlier comparison CWN"
                           if cumulative else "Compare two CWNs"),
            "original": opts.original, "updated": opts.updated, "output": cwn_path,
            "output_type_label": OUTPUT_LABELS.get(opts.output_type, "Full CWN"),
            "days_label": day_label(opts.days) if opts.days else "All days in the CWNs",
        }
        _save(lambda: write_report(rep_path, rep_changes, rounds, info), rep_path)
        result["report"] = rep_path
        lg(f"Saved report: {rep_path}")
    p(1.0, "Done")
    return result
