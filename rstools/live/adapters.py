"""Every comparison in the app, turned into what the Live View shows.

Each adapter runs the same reading and matching code as its tab (Stock Tools, Stats Pack,
Timing Tools), so the Live View always agrees with the reports; it only lays the result
out train by train (or row by row) instead of writing a file.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from typing import Callable, Dict, List, Optional, Sequence, cast

from .model import ADDED, CHANGED, ISSUE, REMOVED, SAME, LiveItem, LiveResult, LiveRow

MODES = {
    "cwn": "Stock Tools: two CWNs",
    "berthing": "Stock Tools: two berthing charts",
    "sp_packs": "Stats Pack: two stats pack files",
    "sp_plans": "Stats Pack: two plans (XML + TRENT print each)",
    "units": "Stats Pack: unit reports, two plans",
    "timetables": "Timing Tools: GTR timetable against Network Rail",
    "print_tt": "Timing Tools: train prints against a timetable",
    "list_tt": "Timing Tools: Attune train list against a timetable",
    "prints": "Timing Tools: two sets of train prints or VPT exports",
    "lists": "Timing Tools: two Attune train lists",
    "s4check": "Timing Tools: Section 4 check (Attune XML, optional VPTs)",
    "s4docs": "Timing Tools: two sets of Section 4 documents",
    "tprs": "Timing Tools: two sets of Timetable Planning Rules",
}
MODE_GROUPS = [        # the Task list: a group for each tab, its tasks in the order of that tab's own list
    ("Stock Tools", [("cwn", "Two CWNs"), ("berthing", "Two berthing charts")]),
    ("Stats Pack", [("sp_plans", "Two plans (XML + TRENT print each)"), ("sp_packs", "Two stats pack files"),
                    ("units", "Unit reports, two plans")]),
    ("Timing Tools", [("timetables", "GTR timetable against Network Rail"),
                      ("print_tt", "Train prints against a timetable"),
                      ("list_tt", "Attune train list against a timetable"),
                      ("prints", "Two sets of train prints or VPT exports"), ("lists", "Two Attune train lists"),
                      ("s4check", "Section 4 check (Attune XML, optional VPTs)"),
                      ("s4docs", "Two sets of Section 4 documents"), ("tprs", "Two sets of Timetable Planning Rules")]),
]
Log = Callable[[str], None]


def compute(mode: str, files: Dict[str, List[str]], days: Optional[Sequence[int]] = None,
            log: Log = lambda m: None, passenger_only: bool = False, loose: bool = True,
            header: bool = True, timing: bool = True) -> LiveResult:
    """files: box key -> paths (see the Live tab's FILES). passenger_only: leave out passing times and times shown
    in one file only (intermediate timing points). loose: CWN text compared ignoring spacing and punctuation, as
    the Stock Tools option 'Ignore spacing' (on by default). header / timing: whether train header differences and
    timing differences are checked (train prints and timetables)."""
    if mode == "cwn":
        return cwn(files["a"][0], files["b"][0], days, log, passenger_only, loose)
    if mode == "sp_packs":
        return stats_packs(files["a"][0], files["b"][0], log)
    if mode == "sp_plans":
        return stats_plans(files["xa"][0], " ; ".join(files["ta"]), files["xb"][0], " ; ".join(files["tb"]), log)
    if mode == "s4check":
        return section4_check(files["xa"][0], files.get("a", []), log, (files.get("xb") or [""])[0],
                              files.get("tb", []))
    if mode == "berthing":
        return berthing_charts(files["a"][0], files["b"][0], log)
    if mode == "units":
        return unit_plans((files.get("xa") or [""])[0], " ; ".join(files["ta"]), (files.get("xb") or [""])[0],
                          " ; ".join(files["tb"]), log)
    from rstools.timetable.engine import compare_files
    cmp = compare_files(mode, files["a"], files["b"], log=log, passenger_only=passenger_only)
    if mode == "prints":
        return prints(cmp, header, timing)
    if mode == "lists":
        return lists(cmp)
    if mode in ("s4docs", "tprs"):
        return documents(cmp)
    return timetables(cmp, passenger_only, header, timing)


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
        meta = read_meta_file(path) or {}
        if "baseline" not in meta:
            raise ValueError(f"'{os.path.basename(path)}' is a comparison CWN without its stored data, so it cannot "
                             "be compared here. Compare the original CWNs instead.")
        return model_from_dict(meta["baseline"])
    return load_model(path)


def _unmatched(left: List[str], right: List[str]):
    """Positions on each side whose key has no partner on the other side (each partner used once)."""
    pool: Dict[str, List[int]] = defaultdict(list)
    for j, k in enumerate(right):
        pool[k].append(j)
    odd_left, used = set(), set()
    for i, k in enumerate(left):
        if pool[k]:
            used.add(pool[k].pop(0))
        else:
            odd_left.add(i)
    return odd_left, {j for j in range(len(right)) if j not in used}


def _unit_text(u) -> str:
    """An extra unit row of a coupled train: its stock, berths, diagram and portion."""
    parts = [(u.raw.get("unit") or u.unit), u.raw.get("am") and f"AM {u.raw.get('am')}",
             u.raw.get("pm") and f"PM {u.raw.get('pm')}", (u.raw.get("diag") or u.diag) and
             f"diagram {u.raw.get('diag') or u.diag}", u.raw.get("portion") or u.portion]
    return "  ".join(str(p) for p in parts if p)


def _passes(blk) -> bool:
    """The train only passes this location tab (Start/Call/Pass column 'p')."""
    return blk is None or str(blk.raw.get("loc", "") or "").strip().lower().startswith("p")


def cwn(orig: str, upd: str, days: Optional[Sequence[int]], log: Log, passenger_only: bool = False,
        loose: bool = True) -> LiveResult:
    from cwn_compare.compare import compare_models, match_blocks
    from cwn_compare.days import coverage, filter_model, label as day_label
    from cwn_compare.model import FIELD_LABELS
    from rstools.timetable.engine import read_jobs

    log(f"Reading {os.path.basename(orig)} and {os.path.basename(upd)}")
    m_old, m_new = read_jobs([(model_of, orig), (model_of, upd)])
    from cwn_compare.model import leave_out_unread
    warnings = list(m_old.warnings) + list(m_new.warnings)
    for label, m, path in (("original", m_old, orig), ("updated", m_new, upd)):
        if not m.sheets:
            raise ValueError(f"No CWN location tabs (with an ID / TIME heading row) were found in the {label} CWN, "
                             f"{os.path.basename(path)}.")
    warnings += leave_out_unread(m_old, m_new)
    if not m_old.sheets or not m_new.sheets:
        from cwn_compare.engine import NOTHING_LEFT
        raise ValueError(NOTHING_LEFT)
    full_old = full_new = None
    if days:
        b_old, b_new = coverage(m_old, orig)[0], coverage(m_new, upd)[0]
        full_old, full_new = m_old, m_new
        m_old, m_new = filter_model(m_old, days, b_old), filter_model(m_new, days, b_new)
        warnings.append(f"Showing the trains running on {day_label(days)} only.")
    changes = compare_models(m_old, m_new, full_old=full_old, full_new=full_new, loose=loose)
    if passenger_only:
        warnings.append("Passenger times only: trains that only pass a location are left out of that tab.")
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
            if passenger_only and _passes(o) and _passes(n):
                continue
            mine = by_block.get((sk, blk.key, n is None), [])
            fields_changed = {c.field for c in mine if c.target == "main"}
            other_changed = any(c.target != "main" for c in mine)
            rows: List[LiveRow] = []
            for f in cols:
                a = o.raw.get(f, "") if o else ""
                b = n.raw.get(f, "") if n else ""
                if not a and not b:
                    continue
                state = ADDED if o is None else REMOVED if n is None else (CHANGED if f in fields_changed else SAME)
                rows.append(LiveRow([FIELD_LABELS.get(f, f), str(a), str(b)], state))
            # extra rows, highlighted as the comparison judged them: notes and next-day workings are compared
            # as sets (order and day codes are not changes), so a line is marked only when that kind of change
            # was reported for the train and the line has no match on the other side
            for kind, get, key, reported in (
                    ("Unit", lambda x: [(_unit_text(u), _unit_text(u)) for u in x.units[1:]],     # unit 1 = main
                     lambda t: " ".join(t.split()).casefold(),
                     lambda c: c.target == "unit" or (c.target == "block_end" and c.field == "unit")),
                    ("Note", lambda x: [(t[2], t[1]) for t in x.notes], lambda t: t,
                     lambda c: c.field == "note"),
                    ("Next-day working", lambda x: [(t[2], t[1]) for t in x.nw], lambda t: t,
                     lambda c: c.target == "nw" or (c.target == "block_end" and c.field == "dest"))):
                left, right = (get(o) if o else []), (get(n) if n else [])
                odd_left: set = set()
                odd_right: set = set()
                if o is not None and n is not None and other_changed and any(reported(c) for c in mine):
                    odd_left, odd_right = _unmatched([key(k) for _t, k in left], [key(k) for _t, k in right])
                for i in range(max(len(left), len(right))):
                    a = left[i][0] if i < len(left) else ""
                    b = right[i][0] if i < len(right) else ""
                    state = (ADDED if o is None else REMOVED if n is None else
                             CHANGED if i in odd_left or i in odd_right else SAME)
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
        if (so and so.footer) or (sn and sn.footer):         # also when only one file has the day's tab
            _footer_item(items, sk, title, so, sn, by_block)
    return LiveResult(f"{os.path.basename(orig)}  vs  {os.path.basename(upd)}",
                      ["Field", "Original", "Updated"], items, warnings)


def _footer_item(items: List[LiveItem], sk: str, title: str, so, sn, by_block):
    """Platform workings: a day's berthing arrangements as one entry, a row per platform or siding."""
    old = {e["label"].casefold(): e for e in (so.footer if so else [])}
    new = {e["label"].casefold(): e for e in (sn.footer if sn else [])}
    changed = {c.target_key.casefold(): c for c in _footer_changes(by_block, sk)}
    rows = []
    for k in list(new) + [k for k in old if k not in new]:          # lines only in the original come last
        if "berthing arrangements" in k:
            continue
        o, e = old.get(k), new.get(k)
        state = REMOVED if e is None else ADDED if o is None else CHANGED if k in changed else SAME
        label = (e or o or {}).get("label", "")
        rows.append(LiveRow([label, o["text"] if o else "", e["text"] if e else ""], state))
    differs = bool(changed) or any(r.state != SAME for r in rows)
    head = next((e["label"] for e in list(new.values()) + list(old.values())
                 if "berthing arrangements" in e["label"].casefold()), f"{title} berthing arrangements")
    items.append(LiveItem(f"{sk}|footer|n", title, head.rstrip(":- "), CHANGED if differs else SAME,
                          "Berthing arrangements changed" if differs else "No change", rows,
                          [c.description for c in changed.values()], len(items)))


def _footer_changes(by_block, sk):
    return [c for k, v in by_block.items() if k[0] == sk for c in v if c.target == "footer"]


# --------------------------------------------------------------------------- timetables (all three kinds)
def timetables(cmp, passenger_only: bool = False, header: bool = True, timing: bool = True) -> LiveResult:
    from rstools.timetable.compare import ISSUE_MISSING, ISSUE_TIME
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
                    if passenger_only:
                        continue
                rows.append(LiveRow([e.name, "Arr" if e.role == "arr" else "Dep", e.time,
                                     (issue.gtr_time if issue and issue.gtr_time else other.time if other else ""),
                                     result], state))
            for e in (g.events if g else []) if not passenger_only else []:
                if (e.loc, e.role) not in seen:
                    rows.append(LiveRow([e.name, "Arr" if e.role == "arr" else "Dep", "", e.time,
                                         f"{O} only (not compared)"], "muted"))
            checked = [i for i in m.issues if timing or i.summary != ISSUE_TIME]
            if g is None:
                state, status = REMOVED, f"Missing from {O}"
            elif checked:
                kinds = list(dict.fromkeys("Timing" if i.summary == ISSUE_TIME else "Missing time" if
                                           i.summary == ISSUE_MISSING else "Time shown wrongly" for i in checked))
                state, status = ISSUE, ", ".join(kinds) + " difference"
            elif header and g.headcode != n.headcode:
                state, status = CHANGED, f"TID difference ({O} {g.headcode})"
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
    notes = list(cmp.warnings)
    if passenger_only:
        notes.append("Passenger times only: times shown in one file only (not compared) are left out.")
    if not header or not timing:
        notes.append("Not checked: " + " and ".join(w for w, on in (("header differences (TID)", header),
                                                                  ("timing differences", timing)) if not on) + ".")
    return LiveResult(f"{B} against {O}", ["Location", "Arr/Dep", B, O, "Result"], items, notes)


# --------------------------------------------------------------------------- train prints
def prints(cmp, header: bool = True, timing: bool = True) -> LiveResult:
    """Each pair of trains laid out like the timetable comparison (a row per location and time, both
    prints side by side) with the prints' own details: public times, platform, line, activity codes,
    dwell and allowances; the train's days run, IDs and dates at the top."""
    from rstools.timetable.prints import SIDE_COLUMNS, _compare_pair, kinds_text, side_by_side, train_details

    pax = getattr(cmp, "passenger_only", False)

    def shown(i: int, n: int, cells, state: str) -> str:
        """The row's state: a difference in a part that is not being checked is only greyed."""
        if state != "changed":
            return state
        if i < n:
            return state if header else "muted"
        parts = [p.strip() for p in str(cells[-1]).split(",") if p.strip()]
        if not timing and parts and all(p.startswith(("Time", "Public time")) for p in parts):
            return "muted"
        return state

    def live_rows(a, b):
        n = len(train_details(a, b))                    # the train-detail rows come first
        return [LiveRow(cells, shown(i, n, cells, state), "details" if i < n else "") for i, (cells, state) in
                enumerate(side_by_side(a, b, pax))]
    items: List[LiveItem] = []
    for a, b, how, _n in cmp.pairs:
        rows = live_rows(a, b)
        changes = _compare_pair(a, b, pax, header, timing)
        items.append(LiveItem(f"pair|{a.label()}|{a.days}|{a.first_time}", a.source, f"{a.label()} {a.days}".strip(),
                              CHANGED if changes else SAME, kinds_text(changes),
                              rows, [f"{c.location}: {c.change} ({c.original} -> {c.updated})" for c in changes]
                              + [f"Paired by {how}"], len(items)))
    for t, state, word in [(t, REMOVED, "Removed") for t in cmp.removed] + [(t, ADDED, "Added") for t in cmp.added]:
        a, b = (t, None) if state == REMOVED else (None, t)
        rows = live_rows(a, b)
        items.append(LiveItem(f"{word}|{t.label()}|{t.days}|{t.first_time}", t.source, f"{t.label()} {t.days}".strip(),
                              state, f"Train {word.lower()}", rows, [], len(items)))
    notes = list(cmp.warnings)
    if pax:
        notes.append("Passenger times only: passing times and calls without a public time are left out.")
    if not header or not timing:
        notes.append("Not checked: " + " and ".join(w for w, on in (("header differences", header),
                                                                  ("timing differences", timing)) if not on)
                     + " (shown in grey).")
    return LiveResult("Train prints", list(SIDE_COLUMNS), items, notes)


# --------------------------------------------------------------------------- Attune train lists
def lists(cmp) -> LiveResult:
    from rstools.timetable.trainlist import _ident
    a, b = cmp.original, cmp.updated
    changed: Dict[tuple, dict] = defaultdict(dict)
    for i, j, h, old, new in cmp.changes:
        changed[(i, j)][h] = (old, new)
    items: List[LiveItem] = []
    cols = [(h, a.headers.index(h), b.headers.index(h)) for h in cmp.common]
    for i, j in cmp.pairs:
        diff = changed.get((i, j), {})
        ra, rb = a.rows[i], b.rows[j]
        rows = [LiveRow([h, ra[ca], rb[cb]], CHANGED if h in diff else SAME) for h, ca, cb in cols]
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
    old_pd, w_old = build_pack(old, opts, __version__)
    new_pd, w_new = build_pack(new, opts, __version__)
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
                      ["Column", "Original", "Updated"], items, list(old.warnings) + list(new.warnings)
                      + [f"Original plan - {w}" for w in w_old] + [f"Updated plan - {w}" for w in w_new])


# --------------------------------------------------------------------------- Section 4 and TPR documents
def documents(cmp) -> LiveResult:
    """Two sets of Section 4 or TPR documents: each possession row / table row / paragraph, field by field."""
    state_of = {"changed": CHANGED, "added": ADDED, "removed": REMOVED, "same": SAME}
    items: List[LiveItem] = []
    for it in cmp.items:
        state = state_of.get(it.status, SAME)
        real = {f[0] for f in it.changes}
        rows = []
        for name, old, new in it.fields:
            if not old and not new:
                continue
            rs = ADDED if state == ADDED else REMOVED if state == REMOVED else (CHANGED if name in real else SAME)
            rows.append(LiveRow([name, old, new], rs))
        if it.where:
            rows.append(LiveRow(["Pages", it.where, ""], "muted"))
        diff = [n for n, o, u in it.changes]
        status = {ADDED: "Added", REMOVED: "Removed", SAME: "No change"}.get(state, ", ".join(diff) + " changed")
        items.append(LiveItem(it.key, f"{it.book} - {it.group}" if it.book else it.group, it.label, state, status,
                              rows, [f"{n}: {o or '-'} -> {u or '-'}" for n, o, u in it.changes], len(items)))
    return LiveResult(f"{cmp.kind}: original vs updated", ["Field", "Original", "Updated"], items,
                      list(cmp.warnings))


# --------------------------------------------------------------------------- Section 4 check
def section4_check(xml: str, pdfs: Sequence[str], log: Log, vpt: str = "",
                   others: Sequence[str] = ()) -> LiveResult:
    """The trains running in a Section 4 possession window (the same check as Timing Tools), one item per train,
    day and possession; lifted clashes and trains not checked are listed too."""
    from rstools import rules
    from rstools.stationbook import read_plan
    from rstools.timetable.section4 import DAY_SHORT, check, read_statement
    from rstools.timetable.engine import read_jobs
    from rstools.timetable.s4remarks import CHECK
    if pdfs:
        log("Reading the Section 4 PDF(s)")
        statement = read_statement(list(pdfs))
    else:
        stored = rules.load_set() if rules.active_set_info() else None
        if stored is None:
            raise ValueError("Choose the Section 4 PDF(s), or add a Section 4 rule set in Options > Rules and "
                             "reference data.")
        statement = stored
    log(f"Reading {os.path.basename(xml)}")
    (plan,) = read_jobs([(read_plan, xml)])
    own = read_plan(vpt) if vpt else None
    theirs = [read_plan(o) for o in others]
    res = check(plan, statement, log, own, theirs)
    items: List[LiveItem] = []

    def rows_of(c) -> List[LiveRow]:
        p = c.possession
        return [LiveRow(["Section", f"{p.number} {p.section}", ""], SAME),
                LiveRow(["Line of route", p.route, ""], "muted"),
                LiveRow(["Period / night", f"{c.period.name} - {p.night}", ""], SAME),
                LiveRow(["Possession", c.window.text, f"Runs {DAY_SHORT[c.day]}"], ISSUE if c.all_lines else CHANGED),
                LiveRow([p.ends[0], "", c.at_a], SAME), LiveRow([p.ends[-1], "", c.at_b], SAME),
                LiveRow(["Blocked", p.blocked or "-", c.direction or "-"], SAME),
                *([LiveRow(["Line used (VPT)", c.line, c.line_why], SAME)] if c.line else []),
                *([LiveRow(["Operator", c.operator, ""], SAME)] if c.operator else []),
                LiveRow(["Remarks", p.remarks or "-", c.remark or "-"],
                        CHANGED if c.outcome == CHECK else SAME)]
    for group, clashes, exempt in (("Clashes", res.clashes, False), ("Exempt", res.exempt, True)):
        for c in clashes:
            p = c.possession
            if exempt:
                state, status = SAME, "Exempt: " + (c.remark or "remarks")
            elif c.all_lines:
                state, status = ISSUE, "Every line blocked"
            else:
                state, status = CHANGED, "Some lines: check the line used"
            if not exempt and c.outcome == CHECK:
                status += " (check remark)"
            items.append(LiveItem(f"{group}|{p.number}|{p.night}|{c.period.name}|{c.operator}|{c.train}|{c.day}", group,
                                  f"{c.train}{' [' + c.operator + ']' if c.operator else ''} "
                                  f"{DAY_SHORT[c.day]} - {p.number}", state, status, rows_of(c),
                                  [x for x in (c.remark,) if x], len(items)))
    for train, why in res.skipped:
        items.append(LiveItem(f"Skipped|{train}", "Not checked", train, SAME, why,
                              [LiveRow(["Not checked", why, ""], "muted")], [], len(items)))
    return LiveResult(f"Section 4 check - {os.path.basename(xml)}", ["Item", "Section 4", "Train"], items,
                      list(statement.warnings) + list(res.warnings))


# --------------------------------------------------------------------------- berthing charts
def berthing_charts(old_path: str, new_path: str, log: Log) -> LiveResult:
    """Two berthing charts, berth by berth (rstools.berthing.compare.diff, as the change report). Each berth with a
    difference is one item; its rows are its cells side by side - [column, older chart, newer chart] - with the
    changed, added and removed cells marked, and the berth's unchanged cells (state 'same') between them in column
    order, so a change is seen in context. Berths with no difference are not listed."""
    from rstools.berthing.compare import ADDED as B_ADDED, CHANGED as B_CHANGED, REMOVED as B_REMOVED, diff, same_cells
    from rstools.berthing.layout import read_chart
    from rstools.berthing.mapping import load as load_locations, norm
    if os.path.abspath(old_path) == os.path.abspath(new_path):
        raise ValueError("The two charts selected are the same file.")
    locations = load_locations()
    log(f"Reading {os.path.basename(old_path)} and {os.path.basename(new_path)}")
    old, new = read_chart(old_path, locations), read_chart(new_path, locations)
    changes, _marked = diff(old, new)
    unchanged = same_cells(old, new)
    by_berth: Dict[tuple, list] = defaultdict(list)
    for c in changes:
        by_berth[(c.sheet, c.berth)].append(c)
    state_of = {B_CHANGED: CHANGED, B_ADDED: ADDED, B_REMOVED: REMOVED}
    items: List[LiveItem] = []
    # chart order: by sheet, then by siding location (a sheet with several), then by berth
    for (sheet, berth), cs in sorted(by_berth.items(), key=lambda kv: (kv[0][0], kv[1][0].rank, kv[0][1])):
        kinds = {c.kind for c in cs}
        state = state_of[next(iter(kinds))] if len(kinds) == 1 else CHANGED
        rows = [(c.col, 1, LiveRow([c.column or "-", c.old, c.new], state_of.get(c.kind, CHANGED))) for c in cs]
        rows += [(col, 0, LiveRow([head, text, text], SAME))
                 for col, head, text in unchanged.get((norm(sheet), norm(berth)), [])]
        counts = Counter(c.kind for c in cs)
        status = ", ".join(f"{counts[k]} {k.lower()}" for k in (B_CHANGED, B_ADDED, B_REMOVED) if counts[k])
        place = cs[0].section                                   # the location, on a sheet that has several
        items.append(LiveItem(f"{sheet}|{berth}", f"{sheet} - {place}" if place else sheet, berth, state,
                              f"{status} cell(s)", [r for _o, _k, r in sorted(rows, key=lambda t: (t[0], t[1]))],
                              [f"{c.column}: {c.kind.lower()} ({c.old or '-'} -> {c.new or '-'})" for c in cs],
                              len(items)))
    return LiveResult(f"{os.path.basename(old_path)}  vs  {os.path.basename(new_path)}",
                      ["Column", "Older chart", "Newer chart"], items,
                      [] if items else ["No differences between the charts."])


# --------------------------------------------------------------------------- unit reports
def unit_plans(xml_a: str, trent_a: str, xml_b: str, trent_b: str, log: Log) -> LiveResult:
    """Unit reports (washes and CETs, depot moves, captive units, fuel) of two plans, row by row, matched as in
    the unit report comparison."""
    from rstools.statspack.engine import PackOptions, PlanInputs, _unit_report_list, load_plan
    from rstools.statspack.model import OPERATORS
    from rstools.statspack.report_compare import SKIP, SPEC, _keyed
    old = load_plan(PlanInputs(xml_a, trent_a), log, xml_optional=True)
    new = load_plan(PlanInputs(xml_b, trent_b), log, xml_optional=True)
    days = sorted(set(old.trent.days()) & set(new.trent.days()))
    if not days:
        raise ValueError("The two TRENT prints have no diagram days in common.")
    opts = PackOptions(days=days, operators=set(OPERATORS), fleets=None)
    which = ["washes", "cets", "depots", "captive", "fuel"]
    log("Following units in both plans...")
    old_reps, w_old = _unit_report_list(old, opts, which, True)
    new_reps, w_new = _unit_report_list(new, opts, which, True)
    by_old = {r.name: r for r in old_reps}
    items: List[LiveItem] = []
    for rep in new_reps:
        if rep.name == "Notes":
            continue
        base = by_old.get(rep.name)
        nkeys = SPEC.get(rep.name, (1, False))[0] + (1 if rep.name.endswith("by Fleet") and rep.headers[:1] == ["Day"]
                                                      else 0)
        nkeys = min(nkeys, len(rep.headers))
        a, b = _keyed(base.rows if base else [], nkeys), _keyed(rep.rows, nkeys)
        for k in list(b) + [k for k in a if k not in b]:
            ra, rb = a.get(k), b.get(k)
            rows, diff = [], []
            for i, head in enumerate(rep.headers):
                if head in SKIP and i >= nkeys:
                    continue
                va = ra[i] if ra is not None and i < len(ra) else None
                vb = rb[i] if rb is not None and i < len(rb) else None
                if va in (None, "") and vb in (None, ""):
                    continue
                st = ADDED if ra is None else REMOVED if rb is None else (SAME if va == vb else CHANGED)
                if st == CHANGED:
                    diff.append(head)
                rows.append(LiveRow([head, "" if va is None else str(va), "" if vb is None else str(vb)], st))
            state = ADDED if ra is None else REMOVED if rb is None else (CHANGED if diff else SAME)
            status = {ADDED: "Only in the updated", REMOVED: "Only in the original", SAME: "No change"}.get(
                state, ", ".join(diff) + " changed")
            label = " / ".join(str(x) for x in k[:nkeys] if x not in (None, "")) or "(row)"
            items.append(LiveItem(f"{rep.name}|{k}", rep.name, label, state, status, rows, [], len(items)))
    return LiveResult(f"Unit reports: {os.path.basename(trent_a)}  vs  {os.path.basename(trent_b)}",
                      ["Figure", "Original", "Updated"], items,
                      [f"Original plan - {w}" for w in w_old] + [f"Updated plan - {w}" for w in w_new])
