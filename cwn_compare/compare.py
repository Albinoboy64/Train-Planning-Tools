"""Train-to-train comparison of two parsed CWNs.

Trains are matched by headcode (plus days run) within each location tab, never
by Excel row number, so re-ordered rows, re-ordered tabs and formatting-only
edits do not produce changes.  Unit diagram numbers are used only to line
units up; diagram changes themselves are not reported.
"""
from __future__ import annotations

import re

from collections import defaultdict
import dataclasses
from dataclasses import dataclass, asdict, fields
from typing import Dict, List, Optional, Tuple

from .model import Block, CWNModel, SheetModel, FIELD_LABELS, UnitRow, is_next_working
from rstools.days import DAY_CODES

# key, label, has "show previous value" option, tooltip
CATEGORIES = [
    ("CANCELLED", "Cancelled train", False,
     "Trains that no longer run at all. In the CWN they are re-inserted struck through."),
    ("NEW", "New train", False, "Trains that did not appear in the original CWN."),
    ("TIME", "Time change", True, "Departure, inbound or arrival time changed."),
    ("LOCATION", "Location change", True,
     "Destination, origin, start/call/pass or the tabs a headcode appears on changed."),
    ("PLATFORM", "Platform change", True, "Platform changed."),
    ("STOCK", "Stock / unit change", True, "Unit type changed, or units added/removed."),
    ("FORMATION", "Inbound / outbound working change", True,
     "An inbound service now forms a different outbound service (or vice versa)."),
    ("BERTHING", "Berthing / next-day working change", True,
     "AM / PM berth, or a next-day working (berth road or next departure time) changed. "
     "Re-ordered lines and day-of-week-only differences are not changes."),
    ("DAYS", "Days run change", True,
     "Days-run code changed. If nothing else about the train changed only the days are highlighted."),
    ("NOTES", "Notes / routing change", True, "Free-text note rows (e.g. '(via Redhill)') changed."),
]
CATEGORY_LABELS = {k: lbl for k, lbl, _, _ in CATEGORIES}
CATEGORY_ORDER = {k: i for i, (k, _, _, _) in enumerate(CATEGORIES)}

LOC_CODES = {"s": "Start/terminate", "c": "Call", "p": "Pass"}


@dataclass
class Change:
    category: str
    sheet: str                 # sheet key
    sheet_title: str
    block_key: str
    train: str                 # display headcode
    field: str                 # logical field (column) or "" for whole block
    target: str                # main | unit | note | inrow | block | block_end
    target_key: str = ""       # unit diagram / note text / inbound headcode used to locate row
    old: str = ""
    new: str = ""
    description: str = ""
    note: str = ""             # note row added when "show previous" is on
    kind: str = "modify"       # modify | add_block | remove_block | add_row | remove_row
    rows: List[dict] = dataclasses.field(default_factory=list)   # old row specs for removed rows/blocks
    anchor: Optional[str] = None                      # new-sheet block key to insert after
    sort_time: Optional[int] = None
    round: int = 1
    colour: str = ""
    hide_old: bool = False     # never show the previous value (days-only change)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Change":
        names = {f.name for f in fields(Change)}
        return Change(**{k: v for k, v in d.items() if k in names})


def _fl(f: str) -> str:
    return FIELD_LABELS.get(f, f)


def _show(v: Optional[str]) -> str:
    return v if v else "(blank)"


def _origin(frm: Optional[str]) -> str:
    if not frm:
        return "nothing"
    if frm.strip().casefold() == "berth":
        return "berth"
    return f"berth ({frm})"


# --------------------------------------------------------------------------- #
# Block matching
# --------------------------------------------------------------------------- #
def _similarity(o: Block, n: Block) -> int:
    s = 6 if o.variant.casefold() == n.variant.casefold() else 0
    for f in ("time", "in_id", "dest", "from", "plat", "inwards"):
        if o.main.get(f) and o.main.get(f) == n.main.get(f):
            s += 2
    s += len({u.diag for u in o.units} & {u.diag for u in n.units})
    s += len({k for _r, k, _d in o.nw} & {k for _r, k, _d in n.nw})
    return s


def _best(o_or_n: Block, cands: List[Block]) -> Block:
    return max(cands, key=lambda c: (_similarity(o_or_n, c), -abs(c.order - o_or_n.order)))


def match_blocks(old: List[Block], new: List[Block]):
    """Returns (pairs [(old, new, mode)], removed old blocks, added new blocks).

    mode is "same", "split" (a new days-variant compared with its closest original) or
    "merged" (an original days-variant that no longer has its own entry, compared with the
    entry it was merged into).  Day splits/merges are never reported as new or removed trains,
    and the days code itself is ignored for them - only real differences are reported.
    """
    pairs: List[Tuple[Block, Block, str]] = []
    used_o, used_n = set(), set()

    def pair(o, n, mode="same"):
        pairs.append((o, n, mode))
        used_o.add(o.key)
        used_n.add(n.key)

    # exact key = same headcode and days variant.  Keys made unique with a running counter
    # ('#2') depend on row order, so those are matched on content below instead.
    new_by_key = {b.key: b for b in new if "#" not in b.key}
    for o in old:
        if "#" not in o.key and o.key in new_by_key:
            pair(o, new_by_key[o.key])

    old_by_base, new_by_base = defaultdict(list), defaultdict(list)
    for o in old:
        if o.base_id:
            old_by_base[(o.is_berth, o.base_id)].append(o)
    for n in new:
        if n.base_id:
            new_by_base[(n.is_berth, n.base_id)].append(n)

    def same_variant(a, b):
        return a.variant.casefold() == b.variant.casefold()

    # same headcode and the same days variant (e.g. duplicated ECS moves, or a variant whose
    # inbound changed) - a MO variant is only ever compared with the MO variant
    for base, ns in new_by_base.items():
        for n in ns:
            cands = [o for o in old_by_base.get(base, []) if o.key not in used_o and same_variant(o, n)]
            if n.key not in used_n and cands:
                pair(_best(n, cands), n)

    # days changed / split / merged
    absorbed = set()
    for base in set(old_by_base) & set(new_by_base):
        oa, na = old_by_base[base], new_by_base[base]
        ol = [o for o in oa if o.key not in used_o]
        nl = [n for n in na if n.key not in used_n]
        if not ol and not nl:
            continue
        if len(oa) == len(na):                # straight days change: compare 1:1
            for n in nl:
                cands = [o for o in ol if o.key not in used_o]
                if cands:
                    pair(_best(n, cands), n)
            continue
        old_days = {o.variant.casefold() for o in oa}
        new_days = {n.variant.casefold() for n in na}
        if not (any(n.variant.casefold() not in old_days for n in nl)
                or any(o.variant.casefold() not in new_days for o in ol)):
            continue
        split_from = set()
        for n in nl:                          # day split: each new part vs its closest original
            o = _best(n, oa)
            pairs.append((o, n, "split"))
            split_from.add(o.key)
            used_n.add(n.key)
        for o in ol:                          # day merge: original part vs the entry it went into
            absorbed.add(o.key)
            if o.key not in split_from:
                pairs.append((o, _best(o, na), "merged"))

    removed = [o for o in old if o.key not in used_o and o.key not in absorbed]
    added = [n for n in new if n.key not in used_n]
    return pairs, removed, added


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
_PUNCT = re.compile(r"[^\w\s]")
# free-text fields compared loosely when 'ignore spacing / punctuation' is on (times, platforms,
# headcodes, units and days are always compared exactly)
LOOSE_FIELDS = {"dest", "from", "portion", "frm"}


def loose_text(text: str) -> str:
    """'(via  Redhill.)' -> 'via redhill': punctuation and repeated spaces ignored."""
    return " ".join(_PUNCT.sub(" ", text).split()).casefold()


class _Ctx:
    def __init__(self, sheet_key, title, loose=False, single_day=(False, False)):
        self.sheet = sheet_key
        self.title = title
        self.loose = loose
        self.single_day = single_day            # (original, updated) is a one-day CWN with no day codes
        self.out: List[Change] = []

    def differs(self, field_name: str, a: str, b: str) -> bool:
        if a == b:
            return False
        return not (self.loose and field_name in LOOSE_FIELDS and loose_text(a) == loose_text(b))

    def add(self, cat, blk: Block, fld, target, old, new, desc, target_key="", note="",
            kind="modify", rows=None, anchor=None):
        self.out.append(Change(
            category=cat, sheet=self.sheet, sheet_title=self.title, block_key=blk.key,
            train=blk.label(), field=fld, target=target, target_key=target_key, old=old, new=new,
            description=desc, note=note, kind=kind, rows=rows or [], anchor=anchor,
            sort_time=blk.sort_time))


def _row_spec(blk: Block, r: int) -> List[dict]:
    return [s for s in blk.rows if s.get("r") == r]


def compare_models(old: CWNModel, new: CWNModel, progress=None, loose: bool = False,
                   full_old: Optional[CWNModel] = None, full_new: Optional[CWNModel] = None) -> List[Change]:
    """All changes between two CWNs. loose: ignore differences only in spacing or punctuation in
    free-text fields (destinations, routing, notes); capitals are always ignored.
    full_old / full_new: the whole CWNs when old / new hold only the trains of chosen days, so a train
    that still runs on other days is reported as a days change, not as cancelled or new."""
    old_ids = (full_old or old).all_train_ids()
    new_ids = (full_new or new).all_train_ids()
    # a one-day CWN (e.g. an STP week's WO CWN) gives no day codes: its trains all run that day, so a blank
    # there against 'SX' in a CWN of several days is not a change
    single = tuple(not any(b.main.get("days") for s in (full or m).sheets.values() for b in s.blocks)
                   for m, full in ((old, full_old), (new, full_new)))

    def at(model, sk) -> set:
        sh = model.sheets.get(sk) if model else None
        return {b.base_id for b in sh.blocks if b.base_id} if sh else set()
    changes: List[Change] = []
    keys = list(new.sheets) + [k for k in old.sheets if k not in new.sheets]
    for i, sk in enumerate(keys):
        so = old.sheets.get(sk)
        sn = new.sheets.get(sk)
        sheet = sn or so
        assert sheet is not None                # every key comes from one side or the other
        title = sheet.title
        if progress:
            progress(i, len(keys), title)
        ctx = _Ctx(sk, title, loose, single)
        pairs, removed, added = match_blocks(so.blocks if so else [], sn.blocks if sn else [])
        pair_map: Dict[str, List[str]] = defaultdict(list)
        for o, n, _mode in pairs:
            pair_map[o.key].append(n.key)

        for o, n, mode in pairs:
            start = len(ctx.out)
            _compare_pair(ctx, o, n, mode)
            mine = ctx.out[start:]
            if mine and all(c.category == "DAYS" for c in mine):
                for c in mine:
                    c.hide_old = True

        for o in removed:
            anchor = "__TOP__"
            for prev in reversed(so.blocks[:o.order] if so else []):
                if prev.key in pair_map:
                    anchor = pair_map[prev.key][0]
                    break
            when = o.raw.get("time") or o.raw.get("inwards") or ""
            where = o.raw.get("dest") or ""
            info = " ".join(x for x in (when, where) if x)
            if full_new is not None and o.base_id and o.base_id in at(full_new, sk):
                cat, desc = "DAYS", f"No longer runs on the chosen day(s) ({info})"
            elif o.base_id and o.base_id not in new_ids:
                cat, desc = "CANCELLED", f"Train cancelled ({info})"
            else:
                cat, desc = "LOCATION", f"No longer shown at {title} ({info})"
            if not sn:
                desc += " - location tab removed from updated CWN"
            ctx.add(cat, o, "", "block", "present", "removed", desc, kind="remove_block",
                    rows=list(o.rows), anchor=anchor)

        for n in added:
            when = n.raw.get("time") or n.raw.get("inwards") or ""
            where = n.raw.get("dest") or ""
            info = " ".join(x for x in (when, where) if x)
            if full_old is not None and n.base_id and n.base_id in at(full_old, sk):
                cat, desc = "DAYS", f"Now runs on the chosen day(s) ({info})"
            elif n.base_id and n.base_id not in old_ids:
                cat, desc = "NEW", f"New train ({info})"
            else:
                cat, desc = "LOCATION", f"Now shown at {title} ({info})"
            ctx.add(cat, n, "", "block", "", "added", desc, kind="add_block")

        if so and sn:
            _compare_forms(ctx, so, sn, pair_map)
            _compare_footer(ctx, so, sn)
        changes.extend(_dedupe(ctx.out))
    changes.sort(key=lambda c: (tab_order(c.sheet_title), c.sort_time if c.sort_time is not None else 9999))
    return changes


_DAY_TAB = {c.upper(): i for i, c in enumerate(DAY_CODES)}


def tab_order(title: str) -> tuple:
    """Sort key for tab names: the day tabs of platform workings Monday first (their names can end in a space),
    other tabs (CWN locations) alphabetically."""
    t = title.strip().upper()
    return (0, _DAY_TAB[t], "") if t in _DAY_TAB else (1, 0, t)


def _footer_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def _compare_footer(ctx: _Ctx, so: SheetModel, sn: SheetModel):
    """Platform workings: the berthing arrangements below the trains, line by line (Platform 14, ...)."""
    old = {e["label"].casefold(): e for e in so.footer}
    new = {e["label"].casefold(): e for e in sn.footer}
    title = next((e["label"].split(" Berthing")[0] for e in sn.footer if "berthing arrangements" in
                  e["label"].casefold()), ctx.title)
    for k, e in new.items():
        if "berthing arrangements" in k:
            continue
        was = old.get(k)
        if was is not None and _footer_text(was["text"]) == _footer_text(e["text"]):
            continue
        if was is None and not e["text"]:
            continue
        desc = (f"{title} berthing - {e['label']}: changed from {_show(was['text'] if was else '')} to "
                f"{_show(e['text'])}" if was is not None else f"{title} berthing - {e['label']}: added - {e['text']}")
        ctx.out.append(Change(category="BERTHING", sheet=ctx.sheet, sheet_title=ctx.title,
                              block_key="FOOTER|" + e["label"], train=f"{title} berthing: {e['label']}",
                              field="footer", target="footer", target_key=e["label"],
                              old=was["text"] if was else "", new=e["text"], description=desc, sort_time=10000))
    for k, was in old.items():
        if k not in new and "berthing arrangements" not in k and was["text"]:
            ctx.out.append(Change(category="BERTHING", sheet=ctx.sheet, sheet_title=ctx.title,
                                  block_key="FOOTER|" + was["label"], train=f"{title} berthing: {was['label']}",
                                  field="footer", target="footer", target_key=was["label"], old=was["text"],
                                  new="", description=f"{title} berthing - {was['label']}: no longer shown "
                                  f"(was {was['text']})", sort_time=10000))


def _dedupe(out: List[Change]) -> List[Change]:
    """Several original day variants merged into one entry report the same difference
    (e.g. platform 7 -> 6) once each: keep a single copy of identical changes."""
    seen, result = set(), []
    for c in out:
        key = (c.block_key, c.kind, c.category, c.field, c.target, c.target_key, c.old, c.new)
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def _compare_pair(ctx: _Ctx, o: Block, n: Block, mode: str = "same"):
    om, nm, orw, nrw = o.main, n.main, o.raw, n.raw
    ignore_days = mode != "same"
    lbl = n.label()
    if mode == "merged":
        lbl = f"{lbl} (former {o.variant or 'days'} variant)"

    def diff(f):
        return f in nm and ctx.differs(f, om.get(f, ""), nm.get(f, ""))

    simple = [("time", "TIME"), ("plat", "PLATFORM"), ("line", "PLATFORM"), ("days", "DAYS"),
              ("dest", "BERTHING" if n.is_berth else "LOCATION"), ("loc", "LOCATION")]
    for f, cat in simple:
        if not diff(f) or (f == "days" and ignore_days):
            continue
        if f == "days" and ((ctx.single_day[0] and not om.get(f)) or (ctx.single_day[1] and not nm.get(f))):
            continue                            # one-day CWN: no day codes, every train runs that day
        if f == "dest" and is_next_working(orw.get("dest", "")) and is_next_working(nrw.get("dest", "")):
            continue    # berth / next-day working lines are compared as a set below
        if f == "loc":
            desc = (f"{lbl}: changed from {LOC_CODES.get(om[f], _show(orw.get(f)))} to "
                    f"{LOC_CODES.get(nm[f], _show(nrw.get(f)))} at {ctx.title}")
        else:
            desc = f"{lbl}: {_fl(f)} changed from {_show(orw.get(f))} to {_show(nrw.get(f))}"
        ctx.add(cat, n, f, "main", orw.get(f, ""), nrw.get(f, ""), desc)

    inbound_changed = diff("in_id")
    if inbound_changed:
        was = orw.get("in_id") or _origin(orw.get("from"))
        now = nrw.get("in_id") or _origin(nrw.get("from"))
        ctx.add("FORMATION", n, "in_id", "main", orw.get("in_id", ""), nrw.get("in_id", ""),
                f"{lbl}: now formed from {now} (previously formed from {was})",
                note=f"Amended: previously formed from {was}")
    for f, cat in (("dep", "TIME"), ("inwards", "TIME"), ("from", "LOCATION"), ("fp", "FORMATION"),
                   ("in_line", "PLATFORM")):
        if diff(f):
            ctx.add("FORMATION" if inbound_changed else cat, n, f, "main", orw.get(f, ""), nrw.get(f, ""),
                    f"{lbl}: {_fl(f)} changed from {_show(orw.get(f))} to {_show(nrw.get(f))}")

    _compare_units(ctx, o, n, lbl)
    _compare_notes(ctx, o, n, lbl)
    _compare_next_workings(ctx, o, n, lbl)


def _align_units(ou: List[UnitRow], nu: List[UnitRow]):
    """Line units up by diagram number first, then by position."""
    pairs, used_o, used_n = [], set(), set()
    for j, u in enumerate(nu):
        if not u.diag:
            continue
        for i, v in enumerate(ou):
            if i not in used_o and v.diag == u.diag:
                pairs.append((v, u))
                used_o.add(i)
                used_n.add(j)
                break
    lo = [v for i, v in enumerate(ou) if i not in used_o]
    ln = [u for j, u in enumerate(nu) if j not in used_n]
    k = min(len(lo), len(ln))
    pairs.extend(zip(lo[:k], ln[:k]))
    return pairs, lo[k:], ln[k:]


def _unit_key(blk: Block, u: UnitRow) -> str:
    """How a unit row is found again: its diagram number, or (platform workings have none) its position."""
    if u.diag:
        return u.diag
    return "#%d" % next((i for i, x in enumerate(blk.units) if x.row == u.row), 0)


def _compare_units(ctx: _Ctx, o: Block, n: Block, lbl: str):
    pairs, removed, added = _align_units(o.units, n.units)
    for v, u in pairs:
        tk = _unit_key(n, u)
        checks = [("unit", "unit", "STOCK"), ("cars", "cars", "STOCK"), ("op", "op", "STOCK"),
                  ("am", "am", "BERTHING"), ("pm", "pm", "BERTHING")]
        if v.row != o.start_row and u.row != n.start_row:
            checks.append(("dest", "portion", "BERTHING" if n.is_berth else "LOCATION"))
        for f, attr, cat in checks:
            if f in u.raw and ctx.differs(attr, getattr(v, attr), getattr(u, attr)):
                ov, nv = v.raw.get(f, ""), u.raw.get(f, "")
                what = _fl("portion" if attr == "portion" else f)
                ctx.add(cat, n, f, "unit", ov, nv, f"{lbl}: {what} changed from {_show(ov)} to {_show(nv)}",
                        target_key=tk)
        # secondary inbound working on a continuation row
        if v.row != o.start_row and u.row != n.start_row:
            in_changed = v.in_id != u.in_id
            if in_changed:
                was = v.raw.get("in_id") or "nothing"
                now = u.raw.get("in_id") or "nothing"
                ctx.add("FORMATION", n, "in_id", "unit", v.raw.get("in_id", ""), u.raw.get("in_id", ""),
                        f"{lbl}: unit now comes from {now} (previously {was})",
                        target_key=tk, note=f"Amended: unit previously from {was}")
            for f, attr, cat in (("dep", "dep", "TIME"), ("inwards", "inwards", "TIME"),
                                 ("from", "frm", "LOCATION"), ("fp", "fp", "FORMATION"),
                                 ("in_line", "in_line", "PLATFORM")):
                if f in u.raw and ctx.differs(attr, getattr(v, attr), getattr(u, attr)):
                    ov, nv = v.raw.get(f, ""), u.raw.get(f, "")
                    ctx.add("FORMATION" if in_changed else cat, n, f, "unit", ov, nv,
                            f"{lbl}: {_fl(f)} changed from {_show(ov)} to {_show(nv)}", target_key=tk)
    for u in added:
        ctx.add("STOCK", n, "unit", "unit", "", u.raw.get("unit", ""),
                f"{lbl}: unit added - {u.raw.get('unit', '').strip('()')}", target_key=_unit_key(n, u),
                kind="add_row")
    for v in removed:
        ctx.add("STOCK", n, "unit", "block_end", v.raw.get("unit", ""), "",
                f"{lbl}: unit removed - {v.raw.get('unit', '').strip('()')}",
                kind="remove_row", rows=_row_spec(o, v.row))


def _compare_notes(ctx: _Ctx, o: Block, n: Block, lbl: str):
    key = loose_text if ctx.loose else (lambda t: t)
    pool: Dict[str, int] = defaultdict(int)
    for _r, t, _d in o.notes:
        pool[key(t)] += 1
    for _r, t, d in n.notes:
        t = key(t)
        if pool[t] > 0:
            pool[t] -= 1
        else:
            ctx.add("NOTES", n, "note", "note", "", d, f"{lbl}: note added - {d}", target_key=t, kind="add_row")
    for r, t, d in o.notes:     # whatever is left in the pool was removed
        t = key(t)
        if pool[t] > 0:
            pool[t] -= 1
            ctx.add("NOTES", n, "note", "block_end", d, "", f"{lbl}: note removed - {d}",
                    kind="remove_row", rows=_row_spec(o, r))


def _road(key: str) -> str:
    """Berth road / siding of a next-working key, e.g. 'bi149' from 'berth bi149 06+16mo'."""
    words = key.replace("berth", "", 1).split()
    return words[0] if words else ""


_UNIT_POSITION = re.compile(r"\((\d+)\)\s*$")


def _position(text: str) -> str:
    """The unit position at the end of a next-working line, e.g. '2' from 'Berth BI150 06+10MO (2)'."""
    m = _UNIT_POSITION.search(text)
    return m.group(1) if m else ""


def _compare_next_workings(ctx: _Ctx, o: Block, n: Block, lbl: str):
    """Berth / next-day working lines compared as a set on berth road + next time: a different
    order, a unit swap between lines or a different day-of-week code are not changes - only a
    real difference (another road or time, or a working added/removed) is."""
    pool = defaultdict(list)
    for item in o.nw:
        pool[item[1]].append(item)
    new_only = []
    for item in n.nw:
        if pool[item[1]]:
            pool[item[1]].pop()
        else:
            new_only.append(item)
    old_only = [item for items in pool.values() for item in items]
    old_only.sort(key=lambda it: it[0])
    # pair a new line with a removed one only when they are the same working: the same berth road (a new
    # time) first, then the same unit position '(n)'. Anything left is paired only when it cannot be a guess:
    # one line left on each side and neither gives a unit position (a single unit's working that changed).
    # Otherwise it is a removal and an addition - never a 'changed from' between unrelated workings.
    paired: Dict[int, tuple] = {}
    for same in (lambda a, b: _road(a[1]) == _road(b[1]),
                 lambda a, b: _position(a[2]) != "" and _position(a[2]) == _position(b[2])):
        for i, item in enumerate(new_only):
            if i not in paired:
                match = next((it for it in old_only if same(it, item)), None)
                if match is not None:
                    old_only.remove(match)
                    paired[i] = match
    left = [i for i in range(len(new_only)) if i not in paired]
    if len(left) == 1 and len(old_only) == 1 and not _position(new_only[left[0]][2]) \
            and not _position(old_only[0][2]):
        paired[left[0]] = old_only.pop()
    for i, (_r, key, disp) in enumerate(new_only):
        match = paired.get(i)
        if match is not None:
            ctx.add("BERTHING", n, "dest", "nw", match[2], disp,
                    f"{lbl}: next-day working changed from {match[2]} to {disp}", target_key=key)
        else:
            ctx.add("BERTHING", n, "dest", "nw", "", disp, f"{lbl}: next-day working added - {disp}",
                    target_key=key, kind="add_row")
    for r, _key, disp in old_only:
        ctx.add("BERTHING", n, "dest", "block_end", disp, "", f"{lbl}: next-day working removed - {disp}",
                kind="remove_row", rows=_row_spec(o, r))


def _compare_forms(ctx: _Ctx, so: SheetModel, sn: SheetModel, pair_map: Dict[str, List[str]]):
    """Inbound service now forms a different outbound service (the 'vice versa' check)."""
    old_forms, new_forms = defaultdict(set), defaultdict(set)
    old_lbl = {}
    for b in so.blocks:
        old_lbl[b.key] = b.label()
        for i in b.in_ids:
            old_forms[i].add(b.key)
    for b in sn.blocks:
        for i in b.in_ids:
            new_forms[i].add(b.key)
    new_blocks = sn.block_by_key()
    for inb, nkeys in new_forms.items():
        okeys = old_forms.get(inb)
        if not okeys:
            continue
        mapped = set()
        for k in okeys:
            mapped.update(pair_map.get(k, []))
        if nkeys <= mapped:
            continue
        was = ", ".join(sorted(old_lbl[k] for k in okeys))
        also = bool(mapped & nkeys)
        disp_in = inb.upper()
        for nk in sorted(nkeys - mapped):
            nb = new_blocks[nk]
            verb = "berths" if nb.is_berth else f"forms {nb.label()}"
            if also:
                desc = f"Inbound {disp_in} now also {verb} (previously only formed {was})"
                note = f"Amended: inbound {disp_in} previously only formed {was}"
            else:
                desc = f"Inbound {disp_in} now {verb} (previously formed {was})"
                note = f"Amended: inbound {disp_in} previously formed {was}"
            ctx.add("FORMATION", nb, "in_id", "inrow", was, disp_in, desc, target_key=inb, note=note)
