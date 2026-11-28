"""Mileage over a period: the whole timetable, one month, or any dates.

Each date in the period is counted with the diagrams that run on it: those for its day of the week whose dates
(in the TRENT print) cover it, with an STP or draft version used in place of the LTP one only on the dates it is
valid for. The mileage tabs of each date are added up, so a week of STP diagrams counts only in that week."""
from __future__ import annotations

import calendar
import datetime as _dt
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from rstools.days import DAY_NAMES, DAYS

from .fleet import FleetTable
from .model import build_day
from .stats import Row, Table, build_tables, weekly_tables
from .trent import TrentData, TrentDiagram
from rstools.naming import agree, plural
from .output import save_sink

MILEAGE_TABS = ["Mileage by Formation", "Mileage by Unit", "Mileage by Vehicle", "Formation Mileage by Service Co",
                "Unit Mileage by Service Code", "Vehicle Mileage by Service Code"]
KINDS = {"timetable": "The whole timetable", "month": "One month", "custom": "From one date to another"}
MAX_DAYS = 400                          # a period longer than this is not a timetable period


class PeriodError(ValueError):
    pass


@dataclass
class Period:
    start: _dt.date
    end: _dt.date
    label: str                          # 'December 2026 timetable', 'January 2027', '01/02/2027 - 28/02/2027'

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def dates(self):
        d = self.start
        while d <= self.end:
            yield d
            d += _dt.timedelta(days=1)


def _date(text: str) -> Optional[_dt.date]:
    try:
        return _dt.datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except (AttributeError, ValueError):
        return None


def parse_date(text: str, what: str = "date") -> _dt.date:
    """A date typed as YYYY-MM-DD or DD/MM/YYYY."""
    t = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return _dt.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise PeriodError(f"The {what} '{t}' is not a date: use DD/MM/YYYY (or YYYY-MM-DD).")


def parse_month(text: str) -> Tuple[int, int]:
    """(year, month) from '2027-01', '01/2027' or 'January 2027' / 'Jan 2027'."""
    t = (text or "").strip()
    for fmt in ("%Y-%m", "%m/%Y", "%B %Y", "%b %Y"):
        try:
            d = _dt.datetime.strptime(t, fmt)
            return d.year, d.month
        except ValueError:
            continue
    raise PeriodError(f"The month '{t}' is not a month: use e.g. January 2027 or 2027-01.")


def timetable_span(trent: TrentData) -> Tuple[Optional[_dt.date], Optional[_dt.date]]:
    """The first and last dates of the timetable: of the LTP diagrams (else of every diagram) in the print."""
    for pool in ([d for d in trent.diagrams if d.plan.upper() == "LTP"], trent.diagrams):
        starts = [x for x in (_date(d.start) for d in pool) if x]
        ends = [x for x in (_date(d.end) for d in pool) if x]
        if starts and ends:
            return min(starts), max(ends)
    return None, None


def months(trent: TrentData) -> List[str]:
    """The months the timetable runs in, e.g. ['December 2026', 'January 2027', ...]."""
    a, b = timetable_span(trent)
    if a is None or b is None:
        return []
    out: List[str] = []
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month) and len(out) < 24:
        out.append(f"{calendar.month_name[m]} {y}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def resolve(trent: TrentData, kind: str, month: str = "", start: str = "", end: str = "") -> Period:
    """The period chosen: the whole timetable, a month (cut to the timetable's dates) or the dates typed."""
    a, b = timetable_span(trent)
    if kind == "timetable":
        if a is None or b is None:
            raise PeriodError("The TRENT print gives no diagram dates, so the timetable's period is not known. "
                              "Choose the dates instead.")
        return Period(a, b, f"{a:%d/%m/%Y} - {b:%d/%m/%Y} (whole timetable)")
    if kind == "month":
        y, m = parse_month(month)
        first, last = _dt.date(y, m, 1), _dt.date(y, m, calendar.monthrange(y, m)[1])
        if a is not None and b is not None:
            if last < a or first > b:
                raise PeriodError(f"{calendar.month_name[m]} {y} is outside the timetable "
                                  f"({a:%d/%m/%Y} - {b:%d/%m/%Y}).")
            first, last = max(first, a), min(last, b)
        return Period(first, last, f"{calendar.month_name[m]} {y}"
                      + (f" ({first:%d/%m/%Y} - {last:%d/%m/%Y})" if (first.day != 1 or last.month != m
                                                                    or last.day != calendar.monthrange(y, m)[1])
                         else ""))
    if kind == "custom":
        s, e = parse_date(start, "first date"), parse_date(end, "last date")
        if e < s:
            raise PeriodError("The last date is before the first date.")
        if (e - s).days + 1 > MAX_DAYS:
            raise PeriodError(f"Choose a period of at most {MAX_DAYS} days.")
        return Period(s, e, f"{s:%d/%m/%Y} - {e:%d/%m/%Y}")
    raise PeriodError(f"'{kind}' is not a period: use " + ", ".join(KINDS) + ".")


def _runs_on(d: TrentDiagram, date: _dt.date) -> bool:
    if date.weekday() not in d.days:
        return False
    a, b = _date(d.start), _date(d.end)
    return (a is None or a <= date) and (b is None or date <= b)


def _total(table: Table) -> Optional[list]:
    rows = [r for r in table.rows if r.kind == "total"]
    if rows:
        return list(rows[-1].cells)
    body = [r.cells for r in table.rows if r.kind == "body"]
    if not body:
        return None
    width = len(body[0])
    out: list = ["Total"]
    for ci in range(1, width):
        vals = [c[ci] for c in body]
        out.append(None if any(v is None for v in vals) else sum(v for v in vals if isinstance(v, (int, float))))
    return out


def build(trent: TrentData, attune, operators, fleets, period: Period, info: dict,
          progress: Callable[[float, str], None] = lambda f, m: None) -> Tuple[List[Table], Table, List[str]]:
    """(the mileage tabs added up over the period, the Mileage by Date tab, warnings)."""
    fleet = FleetTable.load()
    warnings: List[str] = [fleet.warning] if fleet.warning else []
    cache: Dict[tuple, Optional[List[Table]]] = {}
    per_date: List[Tuple[str, List[Table]]] = []
    date_rows: List[Row] = []
    xml_days = attune.days() if attune is not None else set()
    empty: List[_dt.date] = []
    for i, date in enumerate(period.dates()):
        if i % 7 == 0:
            progress(0.1 + 0.75 * i / max(period.days, 1), f"Adding up {date:%d/%m/%Y}...")
        running = [d for d in trent.diagrams if _runs_on(d, date)]
        key = (date.weekday(), tuple(sorted(id(d) for d in running)))
        if key not in cache:
            tabs: Optional[List[Table]] = None
            if running:
                day_trent = TrentData(trent.path, running, [], trent.layout)
                model = build_day(day_trent, attune, fleet, date.weekday(), operators, fleets,
                                  report_missing=date.weekday() in xml_days)
                warnings += [f"{DAY_NAMES[date.weekday()]} ({date:%d/%m/%Y}): {w}" for w in model.warnings
                             if "not found in the XML" in w]
                if model.diagrams:
                    tabs = [t for t in build_tables(model, info) if t.name in MILEAGE_TABS or t.name == "Glossary"]
            cache[key] = tabs
        tabs = cache[key]
        day = DAYS[date.weekday()]
        if tabs is None:
            empty.append(date)
            date_rows.append(Row([date, day, 0, 0, 0.0, 0.0, 0.0, 0.0]))
            continue
        per_date.append((day, tabs))
        by = {t.name: t for t in tabs}
        unit = _total(by["Mileage by Unit"]) or [None] * 4
        veh = _total(by["Vehicle Mileage by Service Code"]) or [None] * 4
        stp = sum(1 for d in running if d.plan.upper() != "LTP")
        diagrams = len({d.key for d in running})
        date_rows.append(Row([date, day, diagrams, stp, unit[1], unit[2], unit[3], veh[3]]))
    if not per_date:
        raise PeriodError("No diagrams run in the period for the selected operators and fleets.")
    progress(0.9, "Adding up the period...")
    totals = [t for t in weekly_tables(per_date, info) if t.name in MILEAGE_TABS]
    order = {n: i for i, n in enumerate(MILEAGE_TABS)}
    totals.sort(key=lambda t: order[t.name])
    sums: list = ["Total", None, None, None]
    for ci in range(4, 8):
        vals = [r.cells[ci] for r in date_rows]
        sums.append(None if any(v is None for v in vals) else round(sum(vals), 2))
    date_rows.append(Row(sums, "total"))
    if empty:
        warnings.append(f"{plural(len(empty), 'date')} in the period {agree(len(empty), 'has', 'have')} no diagrams "
                        "for the selected operators and fleets "
                        f"(e.g. {', '.join(f'{d:%d/%m/%Y}' for d in empty[:6])}); they count as no miles.")
    return totals, Table("Mileage by Date", date_rows), warnings


DATE_HEADERS = ["Date", "Day", "Diagrams", "STP / draft diagrams", "Empty (unit miles)", "In Service (unit miles)",
                "Total (unit miles)", "Total (vehicle miles)"]


def write(totals: Sequence[Table], by_date: Table, period: Period, fmt: str, path_for, stem: str,
          info: dict) -> str:
    """Save the period's tabs: Glossary, Mileage by Date, then each mileage tab added up over the period."""
    from .output import sink_for
    from .stats import glossary
    from .units import Report
    sink = sink_for(fmt)
    sink.table("Glossary", "Glossary", glossary(info))
    note = (f"{period.label}: {plural(period.days, 'day')}. Each date counts the diagrams that run on it, with STP "
            "and draft "
            "diagrams only on the dates they are valid for.")
    sink.report(Report("Mileage by Date", f"Mileage by Date - {period.label}", DATE_HEADERS,
                       [r.cells for r in by_date.rows], [r.kind for r in by_date.rows], note))
    for t in totals:
        title = {"Formation Mileage by Service Co": "Formation Mileage by Service Code"}.get(t.name, t.name)
        sink.table(t.name, f"{title} - total ({period.label})", t)
    path = path_for(stem, sink.ext)
    save_sink(sink, path, stem)
    return path
