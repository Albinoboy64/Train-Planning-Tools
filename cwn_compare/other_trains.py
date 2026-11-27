"""Add other operators' trains to a CWN or platform workings (and, without changing the file, give the platform
workings' berthing arrangements their units).

The other operators' trains come from their own files (Attune XML, VPT or Network Rail CIF: rstools.others).
Each tab's station is found from its name (the tab name or the title above the headings, e.g. 'Victoria'),
matched to the files' location names. On a platform workings day tab ('MO', 'MO 14-12-26') the trains of that day
are added; on a CWN tab every train, with its days in the DAYS column.

A train leaving the station gets a row like the CWN's own: headcode, time, platform, destination, the operator
code as the stock (and in the Op column), and where it came from: the same train if it runs through, the train
that arrived and formed it (the last train ending there before it, from the same platform where both say), or
'Berth' when that train arrived the day before. A train ending there that stays overnight gets a berth row
('Berth 1T05 05.40TO': the train it forms next). The new rows go in time order among the existing ones, in grey
italics; every existing row keeps its text and formatting (rows below move down). A train already on the tab
(same headcode and time) is not added again."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from rstools import naming, others as O
from rstools.days import DAY_CODES

from .model import SheetModel, parse_workbook, sheet_key
from rstools.naming import plural

Log = Callable[[str], None]
GREY = "FF7F7F7F"


class OtherTrainsError(Exception):
    pass


@dataclass
class Result:
    chart: str                  # the saved copy (named like the other tasks' outputs, for the window)
    summary: str
    warnings: List[str] = field(default_factory=list)
    report: str = ""


@dataclass
class NewRow:
    minutes: int                # sort key: minutes after the start of the day (after midnight: past 1440)
    berth: bool                 # an arrival staying overnight (goes among the berth rows)
    values: Dict[str, str]      # field -> text
    key: Tuple[str, str]        # (headcode, time) for not adding a train twice


def _base(name: str) -> str:
    """'London Victoria (C)' -> 'victoria': names compared without 'London', brackets and punctuation."""
    t = re.sub(r"\(.*?\)", " ", name or "").casefold()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    words = [w for w in t.split() if w not in ("london",)]
    return " ".join(words)


def station_tiplocs(texts: Sequence[str], names: Dict[str, str]) -> Set[str]:
    """The TIPLOCs whose name matches a tab's station (tab name or title), or a TIPLOC written there."""
    out: Set[str] = set()
    for text in texts:
        t = (text or "").strip()
        if not t:
            continue
        if t.upper() in names:
            out.add(t.upper())
        want = _base(t)
        if want:
            out |= {k for k, v in names.items() if _base(v) == want}
        if out:
            return out
    return out


def _clock(sec: Optional[int], ecs: bool) -> str:
    if sec is None:
        return ""
    from rstools.clock import clock
    return clock(sec % 86400 if sec >= 86400 else sec, "+" if ecs else ".")


def _minutes(sec: int) -> int:
    m = sec // 60
    return m + 1440 if m < 180 else m           # after midnight: at the end of the day


def _name(names: Dict[str, str], tiploc: str) -> str:
    return names.get(tiploc, tiploc)


def _tab_texts(ws, sm: SheetModel) -> List[str]:
    """The tab's name and the text above its headings (a CWN or workings tab's title, e.g. 'Victoria')."""
    texts = [ws.title.strip()]
    for r in range(1, sm.header_row):
        for c in range(1, min(ws.max_column, 6) + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, str) and v.strip():
                texts.append(re.sub(r"\s*\(.*\)\s*$", "", v.strip()))
    return texts


def rows_for(plans, tiplocs: Set[str], days: Set[int], names: Dict[str, str], day_text: Callable[[Set[int]], str],
             tab_day: Optional[int], sunday: str = "SuO") -> List[NewRow]:
    """The rows other operators' trains add to one tab: `tab_day` for a platform workings day tab, else every
    day in `days` (a CWN), with `day_text(days)` in the DAYS column."""
    links = O.link(O.ends(plans, tiplocs))
    formed: Dict[int, O.Link] = {lk.depart.n: lk for lk in links if lk.depart is not None}
    # the ends are numbered as O.ends numbers them: find a train's own end at the station by (train, day, kind)
    by_train: Dict[Tuple[int, int, str], int] = {}
    for e in O.ends(plans, tiplocs):
        by_train[(id(e.train), e.day, e.kind)] = e.n
    arrivals: Dict[int, O.Link] = {lk.arrive.n: lk for lk in links}
    rows: Dict[Tuple, NewRow] = {}
    day_list = [tab_day] if tab_day is not None else sorted(days)
    for plan in plans:
        for day in day_list:
            for t in O.runs_on(plan, day):
                op = O.operator(plan, t)
                ecs = O.is_empty(t)
                for i, c in enumerate(t.calls):
                    if c.loc not in tiplocs or not c.stops:
                        continue
                    last = i == len(t.calls) - 1
                    first = i == 0
                    if not last and c.dep is not None:
                        v = {"id": t.id[:4], "time": _clock(c.dep_pub if (c.dep_pub is not None and not ecs)
                                                            else c.dep, ecs),
                             "plat": c.plat, "dest": _name(names, t.calls[-1].loc), "unit": op, "op": op,
                             "loc": "S" if first else "C"}
                        if not first:
                            o = t.calls[0]
                            v.update({"in_id": t.id[:4], "inwards": _clock(c.arr, ecs), "from": _name(names, o.loc),
                                      "dep": _clock(o.dep, ecs)})
                        else:
                            lk = formed.get(by_train.get((id(t), day, "dep"), -1))
                            if lk is not None and lk.nights == 0:
                                a = lk.arrive
                                o = a.train.calls[0]
                                v.update({"in_id": a.headcode, "inwards": _clock(a.time, O.is_empty(a.train)),
                                          "from": _name(names, o.loc), "dep": _clock(o.dep, O.is_empty(a.train))})
                            elif lk is not None:
                                v["from"] = "Berth"
                        key = (v["id"], v["time"])
                        rows.setdefault((key, day if tab_day is None else 0), NewRow(_minutes(c.dep), False, v, key))
                    elif last:
                        lk = arrivals.get(by_train.get((id(t), day, "arr"), -1))
                        if lk is not None and lk.nights == 0:
                            continue                    # it forms a train the same day: shown on that train's row
                        o = t.calls[0]
                        when = c.arr if c.arr is not None else c.dep
                        nxt = ""
                        if lk is not None and lk.depart is not None:
                            d = lk.depart
                            code = sunday if d.day == 6 else DAY_CODES[d.day]
                            nxt = f" {d.headcode} {_clock(d.time, O.is_empty(d.train))}{code}"
                        v = {"plat": c.plat, "dest": "Berth" + nxt, "unit": op, "op": op, "in_id": t.id[:4],
                             "inwards": _clock(when, ecs), "from": _name(names, o.loc), "dep": _clock(o.dep, ecs)}
                        key = (v["in_id"], v["inwards"])
                        rows.setdefault((key, day if tab_day is None else 0),
                                        NewRow(_minutes(when or 0), True, v, key))
    if tab_day is not None:
        return sorted(rows.values(), key=lambda r: (r.berth, r.minutes))
    # a CWN: one row for each train and time, with the days it runs
    merged: Dict[Tuple, Tuple[NewRow, Set[int]]] = {}
    for (key, day), row in rows.items():
        sig = (key, tuple(sorted(row.values.items())))
        if sig in merged:
            merged[sig][1].add(day)
        else:
            merged[sig] = (row, {day})
    out = []
    for row, on in merged.values():
        row.values["days"] = day_text(on)
        out.append(row)
    return sorted(out, key=lambda r: (r.berth, r.minutes))


# ------------------------------------------------------------------ writing
def _existing(sm: SheetModel) -> Set[Tuple[str, str]]:
    have = set()
    for b in sm.blocks:
        have.add(((b.raw.get("id") or "")[:4].upper(), (b.raw.get("time") or "").strip()))
        have.add(((b.raw.get("in_id") or "")[:4].upper(), (b.raw.get("inwards") or "").strip()))
    return have


def _sort(m: Optional[int]) -> int:
    if m is None:
        return 10 ** 6
    return m + 1440 if m < 180 else m


def _target_row(sm: SheetModel, row: NewRow) -> int:
    """The sheet row the new row goes on: before the first train of its kind (departure / berth) that is later."""
    same = [b for b in sm.blocks if b.is_berth == row.berth]
    for b in same:
        if _sort(b.sort_time) > row.minutes:
            return b.start_row
    if same:
        return same[-1].end_row + 1
    if not row.berth:
        later = [b for b in sm.blocks if b.is_berth]
        if later:
            return later[0].start_row
    return max([b.end_row for b in sm.blocks] or [sm.header_row]) + 1


def _insert(ws, at: int, n: int):
    """Rows inserted above `at`; merged cells and row heights below move down with their rows."""
    moved = [m for m in ws.merged_cells.ranges if m.min_row >= at]
    for m in moved:
        ws.merged_cells.remove(m)
    heights = {r: d.height for r, d in ws.row_dimensions.items() if r >= at and d.height}
    ws.insert_rows(at, n)
    for r in heights:
        ws.row_dimensions[r].height = None
    for r, h in heights.items():
        ws.row_dimensions[r + n].height = h
    for m in moved:
        m.shift(0, n)
        ws.merged_cells.add(m)


def _write_row(ws, r: int, sm: SheetModel, row: NewRow, like: int):
    from copy import copy

    from openpyxl.styles import Font, PatternFill
    from rstools.fsutil import clean_cell
    for c in range(1, sm.max_col + 1):
        src = ws.cell(row=like, column=c) if like else None
        cell = ws.cell(row=r, column=c)
        if src is not None and src.has_style:
            cell.border, cell.alignment = copy(src.border), copy(src.alignment)
            cell.number_format = src.number_format
            f = src.font
            cell.font = Font(name=f.name, size=f.sz, italic=True, color=GREY)
        else:
            cell.font = Font(italic=True, color=GREY)
        cell.fill = PatternFill(fill_type=None)
    for fld, text in row.values.items():
        col = sm.cols.get(fld)
        if col and text:
            ws.cell(row=r, column=col).value = clean_cell(text)


def add_other_trains(path: str, other_paths: Sequence[str], out_dir: str = "", name: str = "",
                     log: Log = lambda _m: None) -> Result:
    """Save a copy of a CWN or platform workings with other operators' trains added (see the module notes)."""
    from rstools.fsutil import output_folder, save_output, unique_stem

    from .days import coverage
    from .loader import LoadError, load_any
    from .xlsxfix import save_workbook
    if not path or not os.path.isfile(path):
        raise OtherTrainsError(f"This file could not be found:\n{path}")
    if not other_paths:
        raise OtherTrainsError("Choose the other operators' files (Attune XML, VPT or CIF).")
    try:
        plans = O.load(other_paths, log)
    except O.OthersError as exc:
        raise OtherTrainsError(str(exc))
    log(f"Reading {os.path.basename(path)}")
    try:
        wb = load_any(path, rich_text=True)
    except (LoadError, OSError) as exc:
        raise OtherTrainsError(str(exc))
    try:
        model = parse_workbook(wb)
    except Exception as exc:
        raise OtherTrainsError(f"{os.path.basename(path)} could not be read as a CWN or platform workings ({exc}).")
    if not model.sheets:
        raise OtherTrainsError(f"No CWN or platform workings tabs were found in {os.path.basename(path)}.")
    cover, _assumed = coverage(model, path)
    added, warnings = add_to_workbook(wb, model, plans, cover, log)
    folder = output_folder(out_dir)
    stem = unique_stem(folder, naming.clip(name or f"{os.path.splitext(os.path.basename(path))[0]} "
                                                   "(other operators added)"))
    out = os.path.join(folder, stem + ".xlsx")
    save_output(lambda: save_workbook(wb, out), out, OtherTrainsError)
    ops = ", ".join(sorted({O.operator(p) for p in plans}))
    return Result(out, f"{plural(added, 'row')} of other operators' trains ({ops}) added, in grey italics.", warnings)


def add_to_workbook(wb, model, plans, cover: Set[int], log: Log = lambda _m: None) -> Tuple[int, List[str]]:
    """Add the other operators' trains to every tab of an open CWN or platform workings. Returns (rows added,
    warnings)."""
    from .days import tab_day
    from rstools.timetable.base import load_tiplocs
    names = load_tiplocs()
    for p in plans:
        names.update(p.locations)
    warnings: List[str] = []
    added = 0
    for sm in model.sheets.values():
        ws = wb[sm.title]
        tiplocs = station_tiplocs(_tab_texts(ws, sm), names)
        if not tiplocs:
            warnings.append(f"{sm.title.strip()}: its station could not be found in the other operators' files "
                            f"(from '{ws.title.strip()}'), so nothing was added to it.")
            continue
        day = tab_day(sm.key) if "cars" in sm.cols else None
        rows = rows_for(plans, tiplocs, cover, names, lambda on: O.day_code(on, cover), day,
                        "SUN" if "victoria" in sheet_key(sm.title).casefold() else "SuO")
        have = _existing(sm)
        rows = [r for r in rows if (r.key[0].upper(), r.key[1]) not in have]
        if not rows:
            continue
        # bottom up, so the rows found for the earlier ones stay where they were
        placed = sorted(((_target_row(sm, r), i, r) for i, r in enumerate(rows)), key=lambda x: (-x[0], -x[1]))
        like = sm.blocks[0].start_row if sm.blocks else 0
        for at, _i, r in placed:
            _insert(ws, at, 1)
            _write_row(ws, at, sm, r, like + (1 if like >= at else 0))
            like += 1 if like >= at else 0
        added += len(rows)
        log(f"{sm.title.strip()}: {plural(len(rows), 'train')} of other operators added")
    return added, warnings
