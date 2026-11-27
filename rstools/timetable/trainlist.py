"""Compare two Attune train list exports (Excel): every train in the database, one row each.

The heading row is found by its labels (Headcode / Train ID, UID, Days, Origin, Departure...), so
extra title rows, column order and extra columns do not matter. Trains are paired by UID and days
when the export has a UID column, otherwise by headcode, days and origin departure time; the same key
appearing more than once is paired in order (same Stage first). Without a UID, a retimed train left
over is paired by headcode, days and origin when it is the only one on each side with them (never
guessed). Every column present in both files is compared, with times compared as HHMM (so '05:10',
'0510' and an Excel time are equal) and numbers as numbers.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from rstools.naming import plural

from .parse import norm_headcode

_KEYWORDS = re.compile(r"head\s*code|train\s*(id|no|number|uid)|\buid\b|days?|origin|destination|dep|arr|operator|"
                       r"\btoc\b|start|end|stp|from|to\b|power|class|unit|timing\s*load|schedule", re.I)
_ROLE_PATTERNS = (
    ("uid", re.compile(r"^(train\s*)?uid$|^schedule\s*(id|uid)$|^cif\s*uid$", re.I)),
    ("headcode", re.compile(r"^(head\s*code|headcode|signal\s*id|signalling\s*id|train\s*id|trainid|train\s*no\.?|"
                            r"reporting\s*(number|no\.?)|train)$", re.I)),
    ("days", re.compile(r"^(days?(\s*(of\s*operation|run|running|pattern))?|days\s*run|dow|operating\s*days)$",
                        re.I)),
    ("origin_time", re.compile(r"^(origin\s*(dep(arture)?\s*)?time|dep(arture)?\s*time|start\s*time|"
                               r"wtt\s*dep(arture)?|origin\s*dep(arture)?|work(ing)?\s*dep(arture)?|dep)$", re.I)),
    ("origin", re.compile(r"^(origin(\s*(loc|location|station|tiploc))?|start\s*location)$", re.I)),
    ("dest_time", re.compile(r"^(dest(ination)?\s*(arr(ival)?\s*)?time|arr(ival)?\s*time|end\s*time|"
                             r"wtt\s*arr(ival)?|dest(ination)?\s*arr(ival)?|work(ing)?\s*arr(ival)?|arr)$", re.I)),
    ("destination", re.compile(r"^(dest(ination)?(\s*(loc|location|station|tiploc))?|end\s*location)$", re.I)),
    ("operator", re.compile(r"^(operator|toc|toc\s*code|business)$", re.I)),
    ("category", re.compile(r"^(train\s*)?category$", re.I)),
    ("stp", re.compile(r"^(stp(\s*indicator)?|ltp\s*/\s*stp|stage)$", re.I)),
    ("start_date", re.compile(r"^(start\s*date|valid\s*from|date\s*from|from\s*date|runs\s*from|from)$", re.I)),
)
# record-keeping columns (Attune's 'Last Update', 'Lock Id'...) change on every save: listed, never compared
_AUDIT = re.compile(r"^(last\s*(update|updated|modified|edited)(\s*(by|on|date))?|(updated|modified|edited)\s*(by|on)|"
                    r"update\s*id|lock(\s*client)?\s*id|edited\??)$", re.I)
_ID = re.compile(r"^[A-Z0-9]{4,8}$")          # a bus or other non-standard train ID ('BHQ200')
_TIMEISH = re.compile(r"time|dep|arr|pass|wtt|start\s*t|end\s*t", re.I)


class TrainListError(Exception):
    pass


@dataclass
class TrainList:
    path: str
    sheet: str
    header_row: int
    headers: List[str]
    rows: List[List[str]]               # normalised values, one per heading
    roles: Dict[str, int]               # 'uid' / 'headcode' / 'days' / ... -> column
    excel_rows: List[int]

    def key_columns(self) -> List[int]:
        r = self.roles
        if "uid" in r:
            cols = [r["uid"]] + [r[k] for k in ("days", "stp", "start_date") if k in r]
        else:
            cols = [r[k] for k in ("headcode", "days", "origin_time", "origin") if k in r]
        return cols


def _text(value, timeish: bool) -> str:
    if value is None:
        return ""
    if isinstance(value, _dt.datetime):
        if timeish or value.date() == _dt.date(1899, 12, 30):          # a time typed into a date cell
            return f"{value.hour:02d}{value.minute:02d}"
        return value.strftime("%d/%m/%Y") + (f" {value:%H:%M}" if value.hour or value.minute else "")
    if isinstance(value, _dt.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, _dt.time):
        return f"{value.hour:02d}{value.minute:02d}" + ("½" if value.second >= 30 else "")
    if isinstance(value, float):
        if timeish and 0 <= value < 1:
            minutes = round(value * 1440 * 2) / 2
            return f"{int(minutes) // 60 % 24:02d}{int(minutes) % 60:02d}" + ("½" if minutes % 1 else "")
        return f"{value:g}" if value != int(value) else str(int(value))
    text = " ".join(str(value).split())
    if timeish:
        m = re.fullmatch(r"(\d{1,2})[:.]?(\d{2})(?::\d{2})?\s*(½|H)?", text)
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            return f"{int(m.group(1)):02d}{m.group(2)}" + ("½" if m.group(3) else "")
    return text


def _header_score(row: Sequence) -> int:
    cells = [str(c).strip() for c in row if isinstance(c, str) and c.strip()]
    return sum(1 for c in cells if len(c) <= 40 and _KEYWORDS.search(c))


def read_train_list(path: str) -> TrainList:
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        import csv
        from rstools import limits
        try:
            limits.check_size(path, "CSV_MAX_BYTES", "train list")
        except limits.TooLargeError as exc:
            raise TrainListError(str(exc))
        sheets = []
        for enc in ("utf-8-sig", "cp1252"):      # Excel saves 'CSV' in the Windows encoding, 'CSV UTF-8' in UTF-8
            try:
                with open(path, newline="", encoding=enc) as fh:
                    sheets = [("CSV", [list(r) for r in csv.reader(fh)])]
                break
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                from rstools.errorlog import workbook_problem
                raise TrainListError(workbook_problem(path, exc))
        if not sheets:
            with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
                sheets = [("CSV", [list(r) for r in csv.reader(fh)])]
    else:
        try:
            import openpyxl
            from rstools.fsutil import check_office_file
            check_office_file(path)     # refuse a 'zip bomb' before unpacking
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            from rstools.errorlog import workbook_problem
            raise TrainListError(workbook_problem(path, exc))
        try:
            sheets = [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
        except Exception as exc:        # a damaged sheet inside the workbook
            raise TrainListError(f"'{os.path.basename(path)}' looks damaged and could not be read ({exc}). Open it "
                                 "in Excel, save it and try again.")
        finally:
            wb.close()
    best = None
    for title, rows in sheets:
        for i, row in enumerate(rows[:40]):
            score = _header_score(row)
            if score >= 3 and (best is None or score > best[0]):
                best = (score, title, i, rows)
    if best is None:
        raise TrainListError(f"No train list was found in '{os.path.basename(path)}'. Expected a heading row with "
                             "columns such as Headcode / Train ID, UID, Days, Origin and Departure time.")
    _score, title, hr, rows = best
    raw_heads = rows[hr]
    width = max(i + 1 for i, h in enumerate(raw_heads) if h not in (None, ""))
    headers: List[str] = []
    seen: Dict[str, int] = {}
    for i in range(width):
        h = " ".join(str(raw_heads[i]).split()) if raw_heads[i] not in (None, "") else f"Column {i + 1}"
        seen[h] = seen.get(h, 0) + 1
        headers.append(h if seen[h] == 1 else f"{h} ({seen[h]})")
    roles: Dict[str, int] = {}
    for role, pattern in _ROLE_PATTERNS:
        for i, h in enumerate(headers):
            if pattern.match(h) and i not in roles.values():
                roles[role] = i
                break
    if "uid" not in roles and "headcode" not in roles:
        raise TrainListError(f"'{os.path.basename(path)}': no Headcode / Train ID or UID column was found in the "
                             f"heading row ({', '.join(headers[:12])}).")
    timeish = [bool(_TIMEISH.search(h)) and not re.search(r"date", h, re.I) for h in headers]
    data, excel_rows = [], []
    for n, row in enumerate(rows[hr + 1:], start=hr + 2):
        values = [_text(row[i] if i < len(row) else None, timeish[i]) for i in range(width)]
        if not any(values):
            continue
        if "uid" in roles:
            if not values[roles["uid"]]:
                continue                        # a total / notes row under the list
        elif not (norm_headcode(values[roles["headcode"]]) or _ID.match(values[roles["headcode"]].upper())):
            continue
        data.append(values)
        excel_rows.append(n)
    return TrainList(path, title, hr + 1, headers, data, roles, excel_rows)


@dataclass
class ListComparison:
    original: TrainList
    updated: TrainList
    key_headers: List[str]
    common: List[str]
    only_original: List[str]
    only_updated: List[str]
    pairs: List[Tuple[int, int]]
    added: List[int]
    removed: List[int]
    changes: List[Tuple[int, int, str, str, str]]     # (original row, updated row, column, old, new)
    warnings: List[str] = field(default_factory=list)
    ignored: List[str] = field(default_factory=list)    # record-keeping columns in both, not compared
    loose_headers: List[str] = field(default_factory=list)  # retimed trains paired by these (one each side)
    retimed: int = 0                                     # trains paired that way


def compare_train_lists(a: TrainList, b: TrainList) -> ListComparison:
    key_a = [a.headers[i] for i in a.key_columns()]
    key_b = [b.headers[i] for i in b.key_columns()]
    keys = [h for h in key_a if h in key_b]
    if not keys:
        raise TrainListError("The two train lists do not share their key columns (UID or headcode, days...), so "
                             f"their trains cannot be paired.\nOriginal: {', '.join(key_a)}\n"
                             f"Updated: {', '.join(key_b)}")
    pairs: List[Tuple[int, int]] = []
    left_a, left_b = list(range(len(a.rows))), list(range(len(b.rows)))

    def pair(heads: List[str], unique: bool = False):
        """Pair the trains still unpaired that share these columns (in order when a key repeats; only a
        key held by exactly one train on each side when unique)."""
        nonlocal left_a, left_b
        ia, ib = [a.headers.index(h) for h in heads], [b.headers.index(h) for h in heads]
        right: Dict[tuple, List[int]] = {}
        for j in left_b:
            right.setdefault(tuple(b.rows[j][c].casefold() for c in ib), []).append(j)
        left: Dict[tuple, List[int]] = {}
        for i in left_a:
            left.setdefault(tuple(a.rows[i][c].casefold() for c in ia), []).append(i)
        took_a, took_b = set(), set()
        for k, rows in left.items():
            others = right.get(k, [])
            if unique and (len(rows) != 1 or len(others) != 1):
                continue
            for i, j in zip(rows, others):
                pairs.append((i, j))
                took_a.add(i)
                took_b.add(j)
        left_a = [i for i in left_a if i not in took_a]
        left_b = [j for j in left_b if j not in took_b]

    stage = a.headers[a.roles["stp"]] if "stp" in a.roles else ""
    if stage and stage in b.headers and stage not in keys:
        pair(keys + [stage])            # an LTP row and its STP twin (same key) keep to their own stage
    pair(keys)
    dep = a.headers[a.roles["origin_time"]] if "origin_time" in a.roles else ""
    loose = [h for h in keys if h != dep]
    if "uid" not in a.roles and dep in keys and loose:
        n = len(pairs)
        pair(loose, unique=True)        # a retimed train: the only one left with its headcode, days and origin
        retimed = len(pairs) - n
    else:
        loose, retimed = [], 0
    removed, added = left_a, left_b
    pairs.sort()
    common = [h for h in a.headers if h in b.headers and not _AUDIT.match(h)]
    cols = [(h, a.headers.index(h), b.headers.index(h)) for h in common]
    changes = []
    for i, j in pairs:
        ra, rb = a.rows[i], b.rows[j]
        for h, ca, cb in cols:
            old, new = ra[ca], rb[cb]
            if old != new and not _same(old, new):
                changes.append((i, j, h, old, new))
    return ListComparison(a, b, keys, common, [h for h in a.headers if h not in b.headers],
                          [h for h in b.headers if h not in a.headers], pairs, added, sorted(removed), changes,
                          ignored=[h for h in a.headers if h in b.headers and _AUDIT.match(h)],
                          loose_headers=loose, retimed=retimed)


def _same(old: str, new: str) -> bool:
    """Equal apart from case, spacing or number formatting ('5' vs '5.0')."""
    if old.casefold() == new.casefold():
        return True
    try:
        return float(old) == float(new)
    except ValueError:
        return False


def _ident(lst: TrainList, r: int) -> List[str]:
    row = lst.rows[r]
    roles = lst.roles
    return [row[roles[k]] if k in roles else "" for k in ("headcode", "uid", "days", "origin", "origin_time")]


def build_workbook(cmp: ListComparison):
    from .xlstyle import add_sheet, new_workbook
    a, b = cmp.original, cmp.updated
    wb = new_workbook()
    changed = len({i for i, _j, *_ in cmp.changes})
    rows = [["Trains in the original list", len(a.rows)], ["Trains in the updated list", len(b.rows)],
            ["Trains paired", len(cmp.pairs)], ["Paired trains with changes", changed],
            ["Paired trains unchanged", len(cmp.pairs) - changed], ["Trains added (updated only)", len(cmp.added)],
            ["Trains removed (original only)", len(cmp.removed)], ["Individual changes", len(cmp.changes)]]
    add_sheet(wb, "Summary", ["Figure", "Count"], rows, [36, 12], center=[2],
              fills={3: "bad" if changed else "ok", 5: "bad" if cmp.added else "ok",
                     6: "bad" if cmp.removed else "ok"})
    ident = ["Headcode", "UID", "Days", "Origin", "Origin dep"]
    widths = [11, 10, 10, 22, 11, 22, 26, 26, 11, 11]
    keep = [k for k in range(len(ident) + 5) if k != 1 or "uid" in a.roles or "uid" in b.roles]   # no empty UID
    fmt = {keep.index(k) + 1: "@" for k in (4, 6, 7)}
    centre = [keep.index(k) + 1 for k in (4, 8, 9)]
    add_sheet(wb, "Changes by Train",
              [(ident + ["Column", "Original", "Updated", "Original row", "Updated row"])[k] for k in keep],
              [[row[k] for k in keep] for row in
               ([*_ident(a, i), h, old or "-", new or "-", a.excel_rows[i], b.excel_rows[j]]
                for i, j, h, old, new in cmp.changes)],
              [widths[k] for k in keep], formats=fmt, center=centre)
    widths = [max(10, min(30, len(h) + 4)) for h in b.headers]
    add_sheet(wb, "Trains Added", ["Updated row"] + b.headers, [[b.excel_rows[j]] + b.rows[j] for j in cmp.added],
              [11] + widths, center=[1])
    widths = [max(10, min(30, len(h) + 4)) for h in a.headers]
    add_sheet(wb, "Trains Removed", ["Original row"] + a.headers,
              [[a.excel_rows[i]] + a.rows[i] for i in cmp.removed], [11] + widths, center=[1])
    audit: List[list] = [["Original file", os.path.basename(a.path)],
             ["Original sheet / heading row", f"{a.sheet}, row {a.header_row}"],
             ["Updated file", os.path.basename(b.path)],
             ["Updated sheet / heading row", f"{b.sheet}, row {b.header_row}"],
             ["Trains paired by", ", ".join(cmp.key_headers)],
             *([["Retimed trains paired by", f"{', '.join(cmp.loose_headers)} (only when one train on each side "
                 f"is left with them): {cmp.retimed}"]] if cmp.loose_headers else []),
             ["Columns compared", f"{len(cmp.common)}: {', '.join(cmp.common)}"],
             ["Record-keeping columns (not compared)", ", ".join(cmp.ignored) or "None"],
             ["Columns only in the original (not compared)", ", ".join(cmp.only_original) or "None"],
             ["Columns only in the updated (not compared)", ", ".join(cmp.only_updated) or "None"],
             ["Cells compared", len(cmp.pairs) * len(cmp.common)]]
    add_sheet(wb, "What Was Compared", ["Item", "Detail"], audit, [40, 100])
    return wb


def describe(lst: TrainList) -> str:
    return (f"{os.path.basename(lst.path)}: {plural(len(lst.rows), 'train')} (sheet '{lst.sheet}', heading row "
            f"{lst.header_row}; paired by {', '.join(lst.headers[i] for i in lst.key_columns())})")
