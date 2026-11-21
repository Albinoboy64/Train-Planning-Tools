"""Every comparison in the app, turned into what the Live View shows.

Each adapter runs the same reading and matching code as its tab (Stock Tools, Stats Pack,
Timing Tools), so the Live View always agrees with the reports; it only lays the result
out train by train (or row by row) instead of writing a file.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, cast

from .model import ADDED, CHANGED, ISSUE, REMOVED, SAME, LiveItem, LiveResult, LiveRow

MODES = {
    "cwn": "Stock Tools: two CWNs",
    "sp_plans": "Stats Pack: two plans (XML + TRENT print each)",
    "sp_packs": "Stats Pack: two stats pack files",
    "timetables": "Timetable: GTR timetable against Network Rail",
    "print_tt": "Timetable: train prints against a timetable",
    "list_tt": "Timetable: Attune train list against a timetable",
    "prints": "Timetable: two sets of train prints",
    "lists": "Timetable: two Attune train lists",
}
Log = Callable[[str], None]


def compute(mode: str, files: Dict[str, List[str]], days: Optional[Sequence[int]] = None,
            log: Log = lambda m: None) -> LiveResult:
    """files: box key -> paths (see the Live tab's FILES)."""
    if mode == "cwn":
        return cwn(files["a"][0], files["b"][0], days, log)
    if mode == "sp_packs":
        return stats_packs(files["a"][0], files["b"][0], log)
    if mode == "sp_plans":
        return stats_plans(files["xa"][0], " ; ".join(files["ta"]), files["xb"][0], " ; ".join(files["tb"]), log)
    from rstools.timetable.engine import compare_files
    cmp = compare_files(mode, files["a"], files["b"], log=log)
    if mode == "prints":
        return prints(cmp)
    if mode == "lists":
        return lists(cmp)
    return timetables(cmp)


def _same(a: str, b: str) -> bool:
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


# --------------------------------------------------------------------------- CWN
def model_of(path: str):
    """A CWN's trains, or the clean data stored in a comparison CWN made by this app. Module level, so it
    can run in a helper process (big files are read on several CPU cores at once)."""
    from cwn_compare.engine import load_model
    from cwn_compare.meta import is_comparison_output, read_meta_file
    from cwn_compare.model import model_from_dict
    if is_comparison_output(path):
        return model_from_dict((read_meta_file(path) or {})["baseline"])
    return load_model(path)


def _unit_text(u) -> str:
    """An extra unit row of a coupled train: its stock, berths, diagram and portion."""
    parts = [(u.raw.get("unit") or u.unit), u.raw.get("am") and f"AM {u.raw.get('am')}",
             u.raw.get("pm") and f"PM {u.raw.get('pm')}", (u.raw.get("diag") or u.diag) and
             f"diagram {u.raw.get('diag') or u.diag}", u.raw.get("portion") or u.portion]
    return "  ".join(str(p) for p in parts if p)


def cwn(orig: str, upd: str, days: Optional[Sequence[int]], log: Log) -> LiveResult:
    from cwn_compare.compare import compare_models, match_blocks
    from cwn_compare.days import coverage, filter_model, label as day_label
    from cwn_compare.model import FIELD_LABELS
    from rstools.timetable.engine import read_jobs

    log(f"Reading {os.path.basename(orig)} and {os.path.basename(upd)}")
    m_old, m_new = read_jobs([(model_of, orig), (model_of, upd)])
    warnings = list(m_old.warnings) + list(m_new.warnings)
    full_old = full_new = None
    if days:
        b_old, b_new = coverage(m_old, orig)[0], coverage(m_new, upd)[0]
        full_old, full_new = m_old, m_new
        m_old, m_new = filter_model(m_old, days, b_old), filter_model(m_new, days, b_new)
        warnings.append(f"Showing the trains running on {day_label(days)} only.")
    changes = compare_models(m_old, m_new, full_old=full_old, full_new=full_new)
    by_block = defaultdict(list)
    for c in changes:
        by_block[(c.sheet, c.block_key, c.kind in ("remove_block",))].append(c)
    items: List[LiveItem] = []
    keys = list(m_new.sheets) + [k for k in m_old.sheets if k not in m_new.sheets]
    for sk in keys:
        so, sn = m_old.sheets.get(sk), m_new.sheets.get(sk)
        title = (sn or so).title
        cols = list((sn or so).cols)
        pairs, removed, added = match_blocks(so.blocks if so else [], sn.blocks if sn else [])
        entries = [(o, n) for o, n, _m in pairs] + [(o, None) for o in removed] + [(None, n) for n in added]
        entries.sort(key=lambda e: ((e[1] or e[0]).order if e[1] else 10 ** 6 + e[0].order))
        for o, n in entries:
            blk = n or o
            mine = by_block.get((sk, blk.key, n is None), [])
            fields_changed = {c.field for c in mine if c.target == "main"}
            other_changed = any(c.target != "main" for c in mine)
            rows: List[LiveRow] = []
            for f in cols:
                if f == "loc":
                    continue
                a = o.raw.get(f, "") if o else ""
                b = n.raw.get(f, "") if n else ""
                if not a and not b:
                    continue
                state = ADDED if o is None else REMOVED if n is None else (CHANGED if f in fields_changed else SAME)
                rows.append(LiveRow([FIELD_LABELS.get(f, f), str(a), str(b)], state))
            for kind, get in (("Unit", lambda x: [_unit_text(u) for u in x.units[1:]]),     # unit 1 = main row
                              ("Note", lambda x: [t[2] for t in x.notes]),
                              ("Next-day working", lambda x: [t[2] for t in x.nw])):
                left, right = (get(o) if o else []), (get(n) if n else [])
                for i in range(max(len(left), len(right))):
                    a = left[i] if i < len(left) else ""
                    b = right[i] if i < len(right) else ""
                    state = (ADDED if o is None else REMOVED if n is None else
                             CHANGED if other_changed and not _same(a, b) else SAME)
                    rows.append(LiveRow([f"{kind} {i + 1}" if max(len(left), len(right)) > 1 else kind, a, b], state))
            if o is None:
                state, status = ADDED, (mine[0].description if mine else "Added")
            elif n is None:
                state, status = REMOVED, (mine[0].description if mine else "Removed")
            elif mine:
                state = CHANGED
                status = ", ".join(dict.fromkeys(c.category.title().replace("_", " ") for c in mine)) + " change"
            else:
                state, status = SAME, "No change"
            items.append(LiveItem(f"{sk}|{blk.key}|{'o' if n is None else 'n'}", title, blk.label(), state, status,
                                  rows, [c.description for c in mine], len(items)))
    return LiveResult(f"{os.path.basename(orig)}  vs  {os.path.basename(upd)}",
                      ["Field", "Original", "Updated"], items, warnings)


# --------------------------------------------------------------------------- timetables (all three kinds)
def timetables(cmp) -> LiveResult:
    from rstools.timetable.compare import ISSUE_TIME
    B, O = cmp.base_label, cmp.other_label
    items: List[LiveItem] = []
    for res in cmp.sections:
        gtr_locs = {(e.loc, e.role) for g in res.gtr_trains for e in g.events}
        for m in res.matches:
            n, g = m.nr, m.gtr
            gidx = {(e.loc, e.role): e for e in g.events} if g else {}
            issues = {(i.location, i.role): i for i in m.issues}
            rows, seen = [], set()
            if g is not None:                           # the trains' days at the top, as in the prints view
                rows.append(LiveRow(["Days run", "", n.days, g.days, "Same" if n.days == g.days else "Different"],
                                    "muted" if n.days == g.days else CHANGED))
            for e in n.events:
                seen.add((e.loc, e.role))
                other = gidx.get((e.loc, e.role))
                issue = issues.get((e.name, e.role))
                if g is None:
                    state, result = REMOVED, f"Train missing from {O}"
                elif issue:
                    state, result = (CHANGED if issue.summary == ISSUE_TIME else ISSUE), issue.summary
                elif other is not None:
                    state, result = SAME, "Match"
                else:
                    state, result = "muted", f"Not in the {O} table (not compared)"
                rows.append(LiveRow([e.name, "Arr" if e.role == "arr" else "Dep", e.time,
                                     (issue.gtr_time if issue and issue.gtr_time else other.time if other else ""),
                                     result], state))
            for e in (g.events if g else []):
                if (e.loc, e.role) not in seen:
                    rows.append(LiveRow([e.name, "Arr" if e.role == "arr" else "Dep", "", e.time,
                                         f"{O} only (not compared)"], "muted"))
            if g is None:
                state, status = REMOVED, f"Missing from {O}"
            elif m.issues:
                state, status = ISSUE, f"{len(m.issues)} issue(s)"
            elif g.headcode != n.headcode:
                state, status = CHANGED, f"Headcode differs ({O} {g.headcode})"
            else:
                state, status = SAME, "Matches"
            notes = [f"{i.location} {i.role}: {i.summary} ({B} {i.nr_time}, {O} {i.gtr_time or '-'})"
                     for i in m.issues]
            if g is not None:
                notes.insert(0, f"Matched to {O} {g.raw_id or g.headcode} ({g.days}) - {m.status}, "
                                f"confidence {m.confidence:.1f}%")
            else:
                notes.append(f"No {O} train in {res.section} matches this {B} train (times, headcode, calling "
                             f"pattern and days were all checked). It is listed on the Missing Trains sheet.")
            items.append(LiveItem(f"{res.section}|{n.raw_id or n.headcode}|{n.days}|{n.column}", res.section,
                                  f"{n.headcode or n.raw_id} {n.days}".strip(), state, status, rows, notes, len(items)))
        for gap in res.gaps:
            g = gap.gtr
            rows = [LiveRow([e.name, "Arr" if e.role == "arr" else "Dep", "", e.time, f"Only in {O}"], ADDED)
                    for e in g.events if (e.loc, e.role) in gtr_locs]
            items.append(LiveItem(f"{res.section}|gap|{g.raw_id}|{g.column}", res.section, f"{g.headcode} {g.days}",
                                  ADDED, f"Isolated {O} gap in {B}", rows,
                                  [f"Not in the {B} timetable, but sits in a gap of a regular {gap.group} pattern"],
                                  len(items)))
    return LiveResult(f"{B} against {O}", ["Location", "Arr/Dep", B, O, "Result"], items, list(cmp.warnings))


# --------------------------------------------------------------------------- train prints
def prints(cmp) -> LiveResult:
    """Each pair of trains laid out like the timetable comparison (a row per location and time, both
    prints side by side) with the prints' own details: public times, platform, line, activity codes,
    dwell and allowances; the train's days run, IDs and dates at the top."""
    from rstools.timetable.prints import SIDE_COLUMNS, _compare_pair, side_by_side, train_details

    def live_rows(a, b):
        n = len(train_details(a, b))                    # the train-detail rows come first
        return [LiveRow(cells, state, "details" if i < n else "") for i, (cells, state) in
                enumerate(side_by_side(a, b))]
    items: List[LiveItem] = []
    for a, b, how, _n in cmp.pairs:
        rows = live_rows(a, b)
        changes = _compare_pair(a, b)
        items.append(LiveItem(f"pair|{a.label()}|{a.days}|{a.first_time}", a.source, f"{a.label()} {a.days}".strip(),
                              CHANGED if changes else SAME, f"{len(changes)} change(s)" if changes else "No change",
                              rows, [f"{c.location}: {c.change} ({c.original} -> {c.updated})" for c in changes]
                              + [f"Paired by {how}"], len(items)))
    for t, state, word in [(t, REMOVED, "Removed") for t in cmp.removed] + [(t, ADDED, "Added") for t in cmp.added]:
        a, b = (t, None) if state == REMOVED else (None, t)
        rows = live_rows(a, b)
        items.append(LiveItem(f"{word}|{t.label()}|{t.days}|{t.first_time}", t.source, f"{t.label()} {t.days}".strip(),
                              state, f"Train {word.lower()}", rows, [], len(items)))
    return LiveResult("Train prints", list(SIDE_COLUMNS), items, list(cmp.warnings))


# --------------------------------------------------------------------------- Attune train lists
def lists(cmp) -> LiveResult:
    from rstools.timetable.trainlist import _ident
    a, b = cmp.original, cmp.updated
    changed: Dict[tuple, dict] = defaultdict(dict)
    for i, j, h, old, new in cmp.changes:
        changed[(i, j)][h] = (old, new)
    items: List[LiveItem] = []
    for i, j in cmp.pairs:
        diff = changed.get((i, j), {})
        rows = [LiveRow([h, a.rows[i][a.headers.index(h)], b.rows[j][b.headers.index(h)]],
                        CHANGED if h in diff else SAME) for h in cmp.common]
        label = " ".join(x for x in _ident(a, i)[:3] if x)
        items.append(LiveItem(f"pair|{'|'.join(_ident(a, i))}|{i}", "Paired", label, CHANGED if diff else SAME,
                              ", ".join(diff) + " changed" if diff else "No change", rows,
                              [f"{h}: {o or '-'} -> {n or '-'}" for h, (o, n) in diff.items()], len(items)))
    for lst, idxs, state, word in ((a, cmp.removed, REMOVED, "Removed"), (b, cmp.added, ADDED, "Added")):
        for r in idxs:
            rows = [LiveRow([h, v if state == REMOVED else "", v if state == ADDED else ""], state)
                    for h, v in zip(lst.headers, lst.rows[r]) if v]
            items.append(LiveItem(f"{word}|{'|'.join(_ident(lst, r))}|{r}", word,
                                  " ".join(x for x in _ident(lst, r)[:3] if x), state, f"Train {word.lower()}", rows,
                                  [], len(items)))
    return LiveResult("Attune train lists", ["Column", "Original", "Updated"], items, list(cmp.warnings))


# --------------------------------------------------------------------------- stats packs
def _table_items(group: str, old, new, items: List[LiveItem]):
    """Rows of one stats table matched by their key columns (as in the stats pack comparison)."""
    from rstools.statspack.compare import _key_cols, _norm, _show, headers_of
    ref = new or old
    try:
        headers = headers_of(ref)
    except Exception:
        headers = []
    kc = _key_cols(ref)

    def keyed(t):
        out, seen = {}, defaultdict(int)
        for _i, r in enumerate(t.rows if t else []):
            k = tuple(_norm(r.cells[c]) if c < len(r.cells) else None for c in kc)
            seen[k] += 1
            out[k + (seen[k],)] = r
        return out

    def label(r):
        return " / ".join(str(_show(r.cells[c])) for c in kc if c < len(r.cells) and r.cells[c] not in (None, "")) \
            or "(row)"
    ko, kn = keyed(old), keyed(new)
    for k in list(kn) + [k for k in ko if k not in kn]:
        ro, rn = ko.get(k), kn.get(k)
        width = max(len(ro.cells) if ro else 0, len(rn.cells) if rn else 0)
        rows, diff = [], []
        for c in range(width):
            a = ro.cells[c] if ro and c < len(ro.cells) else None
            b = rn.cells[c] if rn and c < len(rn.cells) else None
            if a in (None, "") and b in (None, ""):
                continue
            name = headers[c] if c < len(headers) and headers[c] else f"Column {c + 1}"
            st = (ADDED if ro is None else REMOVED if rn is None
                  else SAME if a == b or _norm(a) == _norm(b) else CHANGED)
            if st == CHANGED:
                diff.append(name)
            rows.append(LiveRow([name, str(_show(a)), str(_show(b))], st))
        state = ADDED if ro is None else REMOVED if rn is None else (CHANGED if diff else SAME)
        status = {ADDED: "Row added", REMOVED: "Row removed", SAME: "No change"}.get(
            state, ", ".join(diff) + " changed")
        items.append(LiveItem(f"{group}|{k}", group, label(rn or ro), state, status, rows, [], len(items)))


def stats_packs(old_path: str, new_path: str, log: Log) -> LiveResult:
    from rstools.statspack.compare import read_pack
    from rstools.timetable.engine import read_jobs
    log(f"Reading {os.path.basename(old_path)} and {os.path.basename(new_path)}")
    old_list, new_list = read_jobs([(read_pack, old_path), (read_pack, new_path)])
    old, new = dict(old_list), dict(new_list)
    items: List[LiveItem] = []
    for name in list(new) + [n for n in old if n not in new]:
        if name == "Glossary":
            continue
        _table_items(name, old.get(name), new.get(name), items)
    return LiveResult(f"{os.path.basename(old_path)}  vs  {os.path.basename(new_path)}",
                      ["Column", "Original", "Updated"], items)


def stats_plans(xml_a: str, trent_a: str, xml_b: str, trent_b: str, log: Log) -> LiveResult:
    from cwn_compare import __version__
    from rstools.statspack.days import DAYS
    from rstools.statspack.engine import (PackOptions, PlanInputs, _info, _tables_by_key, build_pack, load_plan)
    from rstools.statspack.model import OPERATORS
    old = load_plan(PlanInputs(xml_a, trent_a), log)
    new = load_plan(PlanInputs(xml_b, trent_b), log)
    days = sorted(set(old.trent.days()) & set(new.trent.days()))
    if not days:
        raise ValueError("The two TRENT prints have no diagram days in common.")
    opts = PackOptions(days=days, operators=set(OPERATORS), fleets=None)
    log("Building both plans' stats...")
    old_pd, _w = build_pack(old, opts, __version__)
    new_pd, _w = build_pack(new, opts, __version__)
    old_t = _tables_by_key(old_pd, _info(old, __version__), True)
    new_t = _tables_by_key(new_pd, _info(new, __version__), True)
    items: List[LiveItem] = []
    keys: List[object] = ["week", *days]
    for key in keys:
        label = "Week" if key == "week" else DAYS[cast(int, key)]
        names = list(new_t.get(key, {})) + [n for n in old_t.get(key, {}) if n not in new_t.get(key, {})]
        for name in names:
            if name != "Glossary":
                _table_items(f"{label} - {name}", old_t.get(key, {}).get(name), new_t.get(key, {}).get(name), items)
    return LiveResult(f"{os.path.basename(trent_a)}  vs  {os.path.basename(trent_b)}",
                      ["Column", "Original", "Updated"], items, list(old.warnings) + list(new.warnings))
