"""Build the stats pack tables (same tabs, columns and rules as the TRACS-RS stats pack).

Every table is kept with raw values (seconds, miles, counts) so that weekly totals and
comparisons can be calculated before formatting.  `None` in a numeric cell means
'unknown' and is written as '???' (as TRACS-RS does).
"""
from __future__ import annotations

import datetime as _dt
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .model import DayModel, Part, TrainRun, service_type

MORNING = (7 * 3600, 9 * 3600 + 59 * 60)       # 07:00 - 09:59 (end exclusive, as TRACS-RS)
EVENING = (16 * 3600, 19 * 3600)               # 16:00 - 19:00 (to 18:59:59)
PEAK_BANDS = [(0, MORNING[0]), MORNING, (MORNING[1], EVENING[0]), EVENING, (EVENING[1], 86400)]


class Clock(int):
    """A time of day in seconds (hh:mm:ss, may exceed 24:00)."""


class Dur(int):
    """A duration in seconds (h:mm:ss)."""


@dataclass
class Row:
    cells: list
    kind: str = "body"          # body | total


@dataclass
class Table:
    name: str
    rows: List[Row]
    key_cols: int = 1           # columns that identify a row (for weekly totals / comparisons)
    side: Optional[list] = None  # Service Miles: in-service / empty train counts
    has_day: bool = False


TAB_ORDER = ["Glossary", "Fleet", "Service Miles", "Service Count by Formation", "Mileage by Formation",
             "Mileage by Unit", "Mileage by Vehicle", "Formation Mileage by Service Co",
             "Unit Mileage by Service Code", "Vehicle Mileage by Service Code", "Diagrammed Time by Formation",
             "Diagrammed Time by Unit", "Diagrammed Time by Vehicle", "Wheel Turning Time by Formation",
             "Wheel Turning Time by Unit", "Wheel Turning Time by Vehicle", "Vehicle Stops by Service Code",
             "Vehicle Counts at Stops", "Vehicle Counts at Stops by Peak", "Calling Pattern (stops+passes)",
             "Calling Pattern (stops only)", "Diagram Summary", "Formation Data", "Diagram Data"]
LIST_TABS = {"Service Miles", "Diagram Summary", "Formation Data", "Diagram Data"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def add(a, b):
    return None if a is None or b is None else a + b


def _sum(values):
    total = 0
    for v in values:
        if v is None:
            return None
        total += v
    return total


def formation_key(part: Part, model: DayModel) -> str:
    return "+".join(sorted(_cls(k, model) for k in part.formation))


def formation_ordered(part: Part, model: DayModel) -> str:
    return "/".join(_cls(k, model) for k in part.formation)


def _cls(diag_key: str, model: DayModel) -> str:
    d = model.all_diagrams.get(diag_key)
    return d.fleet if d else "?"


def _cars(part: Part, model: DayModel) -> Optional[int]:
    total = 0
    for k in part.formation:
        d = model.all_diagrams.get(k)
        if d is None or d.cars is None:
            return None
        total += d.cars
    return total


def _length(part: Part, model: DayModel) -> Optional[float]:
    total = 0.0
    for k in part.formation:
        d = model.all_diagrams.get(k)
        if d is None or d.length is None:
            return None
        total += d.length
    return total


def _split_sum(items):
    """items: (stype, value) -> [empty, in service, total] with None propagation."""
    emp, ins = 0, 0
    for st, v in items:
        if st == "Empty":
            emp = add(emp, v)
        else:
            ins = add(ins, v)
    return [emp, ins, add(emp, ins)]


def _keyed(rows_by_key: Dict[str, list], total=True, wrap=lambda v: v) -> List[Row]:
    rows = [Row([k] + [wrap(v) for v in vals]) for k, vals in sorted(rows_by_key.items())]
    if total and rows:
        n = len(rows[0].cells) - 1
        sums = [_sum(r.cells[i + 1] for r in rows) for i in range(n)]
        rows.append(Row(["Total"] + [wrap(v) for v in sums], "total"))
    return rows


# --------------------------------------------------------------------------- #
def build_tables(model: DayModel, info: dict) -> List[Table]:
    parts = [(t, p) for t in model.trains for p in t.parts]
    tabs = [glossary(info), fleet_tab(model), service_miles(model)]
    tabs += formation_tabs(model, parts)
    tabs += unit_tabs(model)
    tabs += stops_tabs(model)
    tabs += calling_patterns(model)
    tabs += [diagram_summary(model), formation_data(model, parts), diagram_data(model)]
    order = {n: i for i, n in enumerate(TAB_ORDER)}
    return sorted(tabs, key=lambda t: order[t.name])


def glossary(info: dict) -> Table:
    stamp = info.get("created") or _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return Table("Glossary", [Row([f"{stamp} (Train Planning Tools {info.get('version', '')})",
                                   info.get("inputs", "")])])


def fleet_tab(model: DayModel) -> Table:
    in_use: Dict[str, int] = defaultdict(int)
    for d in model.diagrams:
        in_use[d.fleet] += 1
    rows = []
    seen = set()
    for f in sorted(model.fleet.rows, key=lambda r: r.cls):
        seen.add(f.cls)
        rows.append(_fleet_row(f.cls, f.power, f.cars, f.first, f.standard, f.standing, f.total,
                               f.available, in_use.get(f.cls, 0), f.spare))
    for cls in sorted(set(in_use) - seen):
        rows.append(_fleet_row(cls, "Unknown", None, None, None, None, None, None, in_use[cls], None))
    return Table("Fleet", rows)


def _fleet_row(cls, power, cars, first, std, standing, total, avail, used, spare):
    def veh(n):
        return None if n is None or cars is None else n * cars
    return Row([cls, power, cars, first, std, standing, total, avail, used, spare,
                veh(avail), veh(used), veh(spare)])


def service_miles(model: DayModel) -> Table:
    rows = []
    loaded, empty = 0.0, 0.0
    n_ins = n_emp = 0
    for t in model.trains:
        miles = t.miles
        if t.stype == "Empty":
            empty, n_emp = add(empty, miles), n_emp + 1
        else:
            loaded, n_ins = add(loaded, miles), n_ins + 1
        rows.append(Row([t.headcode, t.origin, model.name(t.origin), Clock(t.dep), Clock(t.arr),
                         Dur(t.arr - t.dep), t.dest, model.name(t.dest), miles]))
    blank = [None] * 7
    rows.append(Row(["Total (Loaded)"] + blank + [loaded], "total"))
    rows.append(Row(["Total (Empty)"] + blank + [empty], "total"))
    rows.append(Row(["Total"] + blank + [add(loaded, empty)], "total"))
    return Table("Service Miles", rows, side=[n_ins, n_emp])


def formation_tabs(model: DayModel, parts) -> List[Table]:
    count: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0])
    miles = defaultdict(list)
    diag_t = defaultdict(list)
    wheel_t = defaultdict(list)
    for _t, p in parts:
        k = formation_key(p, model)
        st = service_type(p.headcode)
        c = count[k]
        c[1 if st == "Empty" else 0] += 1
        c[2] += 1
        miles[k].append((st, p.miles))
        diag_t[k].append((st, p.arr - p.dep))
        run = sum(leg.arr - leg.dep for leg in p.legs) if p.legs else p.arr - p.dep
        wheel_t[k].append((st, run))
    m = {k: _split_sum(v) for k, v in miles.items()}
    dt = {k: _split_sum(v) for k, v in diag_t.items()}
    wt = {k: _split_sum(v) for k, v in wheel_t.items()}
    return [
        Table("Service Count by Formation", _keyed({k: v for k, v in count.items()})),
        Table("Mileage by Formation", _keyed(m)),
        Table("Formation Mileage by Service Co", _keyed(m)),
        Table("Diagrammed Time by Formation", _keyed(dt, wrap=_dur)),
        Table("Wheel Turning Time by Formation", _keyed(wt, wrap=_dur)),
    ]


def _dur(v):
    return None if v is None else Dur(v)


def unit_tabs(model: DayModel) -> List[Table]:
    miles, dtime, wtime, cars = defaultdict(list), defaultdict(list), defaultdict(list), {}
    for d in model.diagrams:
        cars[d.fleet] = d.cars
        for mv in d.moves:
            miles[d.fleet].append((mv.stype, mv.miles))
            dtime[d.fleet].append((mv.stype, mv.arr - mv.dep))
            wtime[d.fleet].append((mv.stype, mv.wheel))
    um = {k: _split_sum(v) for k, v in miles.items()}
    ud = {k: _split_sum(v) for k, v in dtime.items()}
    uw = {k: _split_sum(v) for k, v in wtime.items()}

    def per_vehicle(table):
        out = {}
        for k, vals in table.items():
            c = cars.get(k)
            out[k] = [None if (v is None or c is None) else v * c for v in vals]
        return out
    vm, vd, vw = per_vehicle(um), per_vehicle(ud), per_vehicle(uw)
    return [
        Table("Mileage by Unit", _keyed(um)),
        Table("Mileage by Vehicle", _keyed(vm, total=False)),
        Table("Unit Mileage by Service Code", _keyed(um)),
        Table("Vehicle Mileage by Service Code", _keyed(vm)),
        Table("Diagrammed Time by Unit", _keyed(ud, wrap=_dur)),
        Table("Diagrammed Time by Vehicle", _keyed(vd, wrap=_dur)),
        Table("Wheel Turning Time by Unit", _keyed(uw, wrap=_dur)),
        Table("Wheel Turning Time by Vehicle", _keyed(vw, wrap=_dur)),
    ]


# --------------------------------------------------------------------------- #
# stops / counts
# --------------------------------------------------------------------------- #
def _train_events(t: TrainRun, model: DayModel):
    """(location, time, 'arr'|'dep', cars, stype) for every stop of a train."""
    st = t.stype
    for k, p in enumerate(t.parts):
        cars = _cars(p, model)
        if not p.legs:
            if k == 0:
                yield p.origin, p.dep, "dep", cars, st
            yield p.dest, p.arr, "arr", cars, st
            continue
        for i, leg in enumerate(p.legs):
            if i == 0 and k == 0:
                yield leg.origin, leg.dep, "dep", cars, st
            elif i == 0 and k > 0:
                yield leg.origin, leg.dep, "dep", cars, st        # departure with the new formation
            last = i == len(p.legs) - 1
            if leg.dest_stop or last:
                yield leg.dest, leg.arr, "arr", cars, st
                if not last:
                    yield leg.dest, p.legs[i + 1].dep, "dep", cars, st


def _stabled(model: DayModel):
    """(location, start, end, cars): units stabled before their first / after their last move."""
    for d in model.diagrams:
        if not d.moves:
            continue
        first, last = d.moves[0], d.moves[-1]
        yield first.origin, 0, first.dep, d.cars
        if last.arr < 86400:
            yield last.dest, last.arr, 86400, d.cars


def stops_tabs(model: DayModel) -> List[Table]:
    stops: Dict[str, List[int]] = defaultdict(lambda: [0, 0])     # loc -> [empty, in service] vehicles stopping
    hourly: Dict[str, List[List[int]]] = defaultdict(lambda: [[0] * 5 for _ in range(24)])
    peak: Dict[str, List[List[int]]] = defaultdict(lambda: [[0] * 5 for _ in range(len(PEAK_BANDS))])
    for t in model.trains:
        first = True
        for loc, time, kind, cars, st in _train_events(t, model):
            n = cars or 0
            # a stop is counted once per service: at its arrival, or at the origin departure
            if kind == "arr" or first:
                stops[loc][0 if st == "Empty" else 1] += n
            first = False
            col = (1 if st == "Empty" else 0) if kind == "arr" else (3 if st == "Empty" else 2)
            if time < 86400:                      # TRACS-RS leaves out events after 24:00
                hourly[loc][time // 3600][col] += n
                for b, (a, e) in enumerate(PEAK_BANDS):
                    if a <= time < e:
                        peak[loc][b][col] += n
    for loc, start, end, cars in _stabled(model):
        n = cars or 0
        for h in range(24):
            if start <= h * 3600 and (h + 1) * 3600 <= end:
                hourly[loc][h][4] += n
        for b, (a, e) in enumerate(PEAK_BANDS):
            if start <= a and e <= end:
                peak[loc][b][4] += n
    locs = sorted(set(model.locations) | set(hourly) | set(stops))
    stop_rows = [Row([loc, model.name(loc), v[0], v[1], v[0], v[1]]) for loc, v in sorted(stops.items())]
    hour_rows = [Row([loc, model.name(loc)] + [x for h in hourly[loc] for x in h]) for loc in locs]
    peak_rows = [Row([loc, model.name(loc)] + [x for b in peak[loc] for x in b]) for loc in locs]
    return [Table("Vehicle Stops by Service Code", stop_rows),
            Table("Vehicle Counts at Stops", hour_rows),
            Table("Vehicle Counts at Stops by Peak", peak_rows)]


def calling_patterns(model: DayModel) -> List[Table]:
    """Trains grouped by origin, destination and calling points, in diagram order."""
    by_code = {t.headcode: t for t in model.trains}
    ordered = [by_code[h] for h in dict.fromkeys(mv.headcode for d in model.diagrams for mv in d.moves)
               if h in by_code]
    out = []
    for name, stops_only in (("Calling Pattern (stops+passes)", False), ("Calling Pattern (stops only)", True)):
        groups: "OrderedDict[tuple, list]" = OrderedDict()
        for t in ordered:
            pts = [leg.dest for leg in t.legs[:-1]
                   if not stops_only or (leg.dest_stop and leg.dest_pass_kind != "N")]
            g = groups.setdefault((t.origin, t.dest, ", ".join(pts)), [0] * 9)
            ecs = t.stype == "Empty"
            g[1 if ecs else 0] += 1
            g[2] += 1
            for lo, (a, e) in ((3, MORNING), (6, EVENING)):
                if a <= t.dep < e:
                    g[lo + (1 if ecs else 0)] += 1
                    g[lo + 2] += 1
        out.append(Table(name, [Row(list(k) + v) for k, v in groups.items()], key_cols=3))
    return out


# --------------------------------------------------------------------------- #
# list tabs
# --------------------------------------------------------------------------- #
def diagram_summary(model: DayModel) -> Table:
    rows = []
    groups = defaultdict(list)
    for d in model.diagrams:
        groups[d.fleet].append(d)
    for fleet in sorted(groups):
        sums = [0.0, 0, 0.0, 0, 0]
        for d in groups[fleet]:
            if not d.moves:
                continue
            first, last = d.moves[0], d.moves[-1]
            e_m = _sum(m.miles for m in d.moves if m.stype == "Empty")
            l_m = _sum(m.miles for m in d.moves if m.stype != "Empty")
            e_w = sum(m.wheel for m in d.moves if m.stype == "Empty")
            l_w = sum(m.wheel for m in d.moves if m.stype != "Empty")
            dur = last.arr - first.dep
            rows.append(Row([fleet, d.depot, d.number, first.origin, model.name(first.origin), Clock(first.dep),
                             last.dest, model.name(last.dest), Clock(last.arr), e_m, Dur(e_w), l_m, Dur(l_w),
                             Dur(dur)]))
            sums = [add(sums[0], e_m), sums[1] + e_w, add(sums[2], l_m), sums[3] + l_w, sums[4] + dur]
        rows.append(Row(["Total"] + [None] * 8 + [sums[0], Dur(sums[1]), sums[2], Dur(sums[3]), Dur(sums[4])],
                        "total"))
    return Table("Diagram Summary", rows, key_cols=3)


def _pub(work: int, pub: Optional[int]):
    return Clock(pub) if pub is not None and pub != work else None


def formation_data(model: DayModel, parts) -> Table:
    rows = []
    for _t, p in sorted(parts, key=lambda tp: (tp[1].headcode, tp[1].dep)):
        rows.append(Row(["Y", p.headcode, None, None, None, p.origin, model.name(p.origin), Clock(p.dep),
                         _pub(p.dep, p.dep_pub), p.dest, model.name(p.dest), Clock(p.arr), _pub(p.arr, p.arr_pub),
                         p.miles, "/".join(p.formation), formation_ordered(p, model),
                         _q(_cars(p, model)), _q(_round(_length(p, model))), service_type(p.headcode), p.ends]))
    return Table("Formation Data", rows, key_cols=2)


def _round(v):
    return None if v is None else round(v, 2)


def _q(v):
    """Car count / length: '?' when the stock type is unknown (as TRACS-RS)."""
    return "?" if v is None else v


def diagram_data(model: DayModel) -> Table:
    rows = []
    for d in model.diagrams:
        for mv in d.moves:
            pos = mv.formation.index(d.key) if d.key in mv.formation else 99
            rows.append(((mv.headcode, mv.dep, pos),
                         Row(["Y", mv.headcode, None, None, None, mv.origin, model.name(mv.origin), Clock(mv.dep),
                              _pub(mv.dep, mv.dep_pub), mv.dest, model.name(mv.dest), Clock(mv.arr),
                              _pub(mv.arr, mv.arr_pub), mv.miles, d.depot, d.number, d.fleet, _q(d.cars),
                              mv.stype])))
    rows.sort(key=lambda kr: kr[0])
    return Table("Diagram Data", [r for _k, r in rows], key_cols=2)


# --------------------------------------------------------------------------- #
# weekly totals
# --------------------------------------------------------------------------- #
def weekly_tables(per_day: Sequence[tuple], info: dict) -> List[Table]:
    """per_day: [(day code, [Table...])].  Summary tabs are totalled across the days; list tabs
    are combined with a Day column; Fleet shows the most units in use on any day."""
    out = []
    names = [t.name for t in per_day[0][1]]
    for name in names:
        tables = [(code, next(t for t in tabs if t.name == name)) for code, tabs in per_day]
        if name == "Glossary":
            out.append(glossary(info))
        elif name == "Fleet":
            out.append(_weekly_fleet(tables))
        elif name in LIST_TABS:
            out.append(_weekly_list(name, tables))
        else:
            out.append(_weekly_keyed(name, tables))
    return out


def _weekly_fleet(tables):
    base = {r.cells[0]: list(r.cells) for r in tables[0][1].rows}
    for _code, t in tables[1:]:
        for r in t.rows:
            cur = base.setdefault(r.cells[0], list(r.cells))
            if (r.cells[8] or 0) > (cur[8] or 0):
                cur[8], cur[11] = r.cells[8], r.cells[11]
    return Table("Fleet", [Row(v) for k, v in sorted(base.items())])


def _weekly_list(name, tables):
    rows = []
    side = [0, 0]
    totals = defaultdict(lambda: 0.0)
    for code, t in tables:
        for r in t.rows:
            if r.kind == "total":
                if name == "Service Miles":
                    totals[r.cells[0]] = add(totals[r.cells[0]], r.cells[-1])
                else:
                    rows.append(Row([code] + r.cells, "total"))
                continue
            rows.append(Row([code] + r.cells))
        if t.side:
            side = [side[0] + t.side[0], side[1] + t.side[1]]
    if name == "Service Miles":
        for label in ("Total (Loaded)", "Total (Empty)", "Total"):
            rows.append(Row([None, label] + [None] * 7 + [totals[label]], "total"))
    return Table(name, rows, key_cols=tables[0][1].key_cols + 1, side=side if name == "Service Miles" else None,
                 has_day=True)


# tabs kept in first-seen (diagram) order rather than sorted by key
_UNSORTED = {"Calling Pattern (stops+passes)", "Calling Pattern (stops only)"}


def _plus(a, b):
    """Weekly sum of one cell: text is kept, unknown (None) stays unknown, times stay times."""
    if isinstance(a, str) or isinstance(b, str):
        return a
    s = add(a, b)
    return type(b)(s) if isinstance(b, (Dur, Clock)) and s is not None else s


def _weekly_keyed(name, tables):
    """Rows with the same key are added up across the days; a Total row is rebuilt when the
    daily tabs have one."""
    k = tables[0][1].key_cols
    acc: "OrderedDict[tuple, list]" = OrderedDict()
    has_total = False
    for _code, t in tables:
        for r in t.rows:
            if r.kind == "total":
                has_total = True
                continue
            key = tuple(r.cells[:k])
            cur = acc.get(key)
            if cur is None:
                acc[key] = list(r.cells)
            else:
                width = max(len(cur), len(r.cells))
                cur.extend([0] * (width - len(cur)))
                for i in range(k, len(r.cells)):
                    cur[i] = _plus(cur[i], r.cells[i])
    rows = [Row(v) for v in acc.values()]
    if name not in _UNSORTED:
        rows.sort(key=lambda r: r.cells[0])
    if has_total and rows:
        sums = [None] * (k - 1)
        for i in range(k, len(rows[0].cells)):
            vals = [r.cells[i] for r in rows]
            if any(isinstance(v, str) for v in vals):
                sums.append(None)
                continue
            s_ = _sum(vals)
            sums.append(type(vals[0])(s_) if isinstance(vals[0], (Dur, Clock)) and s_ is not None else s_)
        rows.append(Row(["Total"] + sums, "total"))
    return Table(name, rows, key_cols=k)
