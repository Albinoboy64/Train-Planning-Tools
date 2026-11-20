"""Parse a Carriage Working Notice workbook into train "blocks".

A CWN location tab lists, for each outbound train, one main row (headcode in
the first ID column) followed by continuation rows: one per extra coupled unit
and free-text note rows such as "(via Redhill)".  Each main row also carries
the inbound working that forms the train (FROM / INWARDS / ID columns).
Rows with no outbound headcode whose DESTINATION starts with "Berth" are
inbound trains that berth at the location instead of forming another train.

The parser is driven by the column headings, so tabs whose columns are in a
different order (or other CWN layouts using the same headings) still work.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Logical field -> accepted header captions (upper-case, stripped)
HEADER_SYNONYMS = {
    "id": ["ID", "HEADCODE"],
    "days": ["DAYS", "DAY", "DAYS RUN"],
    "time": ["TIME", "DEP", "DEPART", "DEP TIME"],
    "plat": ["PL", "PLAT", "PLATFORM", "PLT"],
    "dest": ["DESTINATION", "DEST"],
    "unit": ["UNIT", "STOCK", "CLASS", "UNITS"],
    "am": ["AM"],
    "pm": ["PM"],
    "diag": ["DIAG", "DIAGRAM"],
    "from": ["FROM", "ORIGIN"],
    "inwards": ["INWARDS", "INWARD", "ARR", "ARR TIME"],
    "in_id": ["IN ID", "INWARD ID", "INWARDS ID"],
    "loc": ["LOC", "ACT", "ACTIVITY"],
}

FIELD_LABELS = {
    "id": "Headcode",
    "days": "Days",
    "time": "Time",
    "plat": "Platform",
    "dest": "Destination",
    "unit": "Unit / stock",
    "am": "AM berth",
    "pm": "PM berth",
    "diag": "Diagram",
    "dep": "Inward departure time",
    "from": "From",
    "fp": "Portion (FP/RP)",
    "inwards": "Inwards arrival time",
    "in_id": "Inward headcode",
    "loc": "Start/Call/Pass",
    "note": "Note",
    "portion": "Portion destination",
    "nw": "Next-day working",
}

TIME_RE = re.compile(r"^(\d{1,2})\s*([.+/:hH])\s*(\d{2})(.*)$")


# A "next-day working" line, e.g. "Berth BI104 05+59MO (1)" or "SU305 05+32MO (2)"
_NW_RE = re.compile(r"^(berth\b|[a-z]{1,4}\d{1,4}\s+\d{1,2}[.+:]\d{2})", re.I)
_TIME_DAYS_RE = re.compile(r"(\d{1,2}[.+:]\d{2})\s?([A-Za-z]{1,8})\b")
_POSITION_RE = re.compile(r"\s*\(\d+\)\s*$")
_DAY_TOKENS = re.compile(r"Su|Sa|Th|Tu|M|T|W|F|S", re.I)
_DAY_ORDER = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "S": 5, "Su": 6}
_DAY_CANON = {"m": "M", "t": "T", "tu": "T", "w": "W", "th": "Th", "f": "F", "s": "S", "sa": "S", "su": "Su"}


# --------------------------------------------------------------------------- #
# Normalisation helpers (comparison ignores formatting-only differences)
# --------------------------------------------------------------------------- #
def cell_text(v) -> str:
    """Display text for a raw cell value (whitespace collapsed)."""
    if v is None:
        return ""
    if type(v) is str:
        return " ".join(v.split())
    if isinstance(v, _dt.datetime):
        if v.year <= 1900:
            return v.strftime("%H.%M")
        return v.strftime("%d/%m/%Y %H:%M") if (v.hour or v.minute) else v.strftime("%d/%m/%Y")
    if isinstance(v, _dt.time):
        return v.strftime("%H.%M")
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return " ".join(str(v).split())


def is_ecs(headcode_text: str) -> bool:
    """Empty coaching stock / light moves (class 5 and 0 headcodes) use '+' times."""
    return bool(headcode_text) and headcode_text[0] in "50"


def time_text(v, ecs: bool = False) -> str:
    """Display text for a time cell: always HH.MM (or HH+MM for ECS), never an Excel serial."""
    sep = "+" if ecs else "."
    if isinstance(v, (_dt.time, _dt.datetime)):
        return "%02d%s%02d" % (v.hour, sep, v.minute)
    if isinstance(v, float) and 0 <= v < 1:
        mins = int(round(v * 1440)) % 1440
        return "%02d%s%02d" % (mins // 60, sep, mins % 60)
    t = cell_text(v)
    m = TIME_RE.match(t)
    if m:
        s = m.group(2)
        s = sep if s in ":hH" else s
        return "%02d%s%s%s" % (int(m.group(1)), s, m.group(3), m.group(4).strip())
    return t


def _day_tokens(code: str):
    """(day tokens, suffix) if `code` is a days code such as 'MO', 'FSX', 'ThFO', 'Su', else None."""
    suffix, body = "", code
    if len(code) > 1 and code[-1] in "OXox":        # Only / eXcepted
        suffix, body = code[-1].upper(), code[:-1]
    tokens = _DAY_TOKENS.findall(body)
    if not tokens or "".join(tokens).lower() != body.lower():
        return None
    return tokens, suffix


def canon_day_code(code: str) -> str:
    """'ThFO' == 'FThO', 'SU' == 'Su': day letters put in week order, case normalised."""
    parsed = _day_tokens(code)
    if parsed is None:
        return code
    tokens, suffix = parsed
    days = sorted({_DAY_CANON[t.lower()] for t in tokens}, key=_DAY_ORDER.get)
    return "".join(days) + suffix


def canon_days(text: str) -> str:
    """Normalise a days-run field such as 'SX', 'FSX', 'MO FO' (order of codes ignored)."""
    parts = [p for p in re.split(r"[\s,/&+;]+", text) if p]
    return " ".join(sorted(canon_day_code(p) for p in parts))


def is_next_working(text: str) -> bool:
    return bool(text) and bool(_NW_RE.match(text))


def canon_next_working(text: str) -> str:
    """Comparison key for a next-day working line: berth road + next time only.

    The position '(n)' and the day-of-week code are left out, so re-ordered lines and
    day-code-only differences (e.g. after day variants were re-ordered) are not changes.
    """
    t = _POSITION_RE.sub("", text)
    t = _TIME_DAYS_RE.sub(lambda m: time_text(m.group(1)) if _day_tokens(m.group(2))
                          else time_text(m.group(1)) + " " + m.group(2), t)
    return " ".join(t.split()).casefold()


def next_working_days(texts) -> str:
    """Canonical day codes mentioned in next-day working lines, e.g. 'MO' - identifies a day variant."""
    codes = {canon_day_code(m.group(2)) for t in texts for m in _TIME_DAYS_RE.finditer(t)
             if _day_tokens(m.group(2))}
    return " ".join(sorted(codes))


def norm_bracket(text: str) -> str:
    """Units/diagrams in coupled formations are wrapped in ( ... ) across rows."""
    return text.strip("()[] ").casefold()


def time_minutes(t: str) -> Optional[int]:
    m = TIME_RE.match(t or "")
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(3))


def sheet_key(title: str) -> str:
    return " ".join(title.split()).upper()


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass
class UnitRow:
    row: int
    unit: str          # normalised values ...
    am: str
    pm: str
    diag: str
    portion: str       # destination text on continuation rows e.g. [Bognor Regis]
    in_id: str
    dep: str
    frm: str
    fp: str
    inwards: str
    raw: Dict[str, str] = field(default_factory=dict)   # display values of the row


@dataclass
class Block:
    sheet: str                 # sheet key
    key: str                   # unique within the sheet
    base_id: str               # outbound headcode, or inbound headcode for berth blocks
    days: str
    is_berth: bool
    start_row: int
    end_row: int
    main: Dict[str, str]       # normalised values of the main row
    raw: Dict[str, str]        # display values of the main row
    units: List[UnitRow]
    notes: List[tuple]         # (row, normalised text, display text) - free-text notes
    nw: List[tuple]            # (row, comparison key, display text) - next-day workings / berths
    rows: List[dict]           # serialisable row specs (values + basic style)
    in_ids: List[str]          # all inbound headcodes in the block (normalised)
    order: int = 0
    variant: str = ""          # days variant: DAYS code, or the day codes of its next-day workings
    sort_time: Optional[int] = None   # minutes past midnight of the main time (for ordering)

    def label(self) -> str:
        days = self.raw.get("days") or self.variant
        if self.is_berth:
            return f"{(self.raw.get('in_id') or self.base_id).upper()} (berths{', ' + days if days else ''})"
        head = (self.raw.get("id") or self.base_id).upper()
        return f"{head} ({days})" if days else head


@dataclass
class SheetModel:
    key: str
    title: str
    header_row: int
    cols: Dict[str, int]        # logical field -> 1-based column
    max_col: int
    blocks: List[Block]
    _by_key: Optional[Dict[str, Block]] = field(default=None, repr=False, compare=False)

    def block_by_key(self) -> Dict[str, Block]:
        if self._by_key is None:            # blocks are fixed once a sheet has been built
            self._by_key = {b.key: b for b in self.blocks}
        return self._by_key


@dataclass
class CWNModel:
    sheets: Dict[str, SheetModel]     # key -> sheet
    other_sheets: List[str]           # titles of non-CWN tabs (cover etc.)
    warnings: List[str] = field(default_factory=list)
    day_hint: str = ""                # wording on the cover / above the headings (which days the CWN is for)

    def all_train_ids(self) -> set:
        ids = set()
        for sh in self.sheets.values():
            for b in sh.blocks:
                if b.base_id:
                    ids.add(b.base_id)
                ids.update(b.in_ids)
        return ids


# --------------------------------------------------------------------------- #
# Header detection
# --------------------------------------------------------------------------- #
def find_header(rows) -> Optional[tuple]:
    """rows: the first rows of a sheet as value tuples. Returns (header_row, cols, max_col)."""
    for idx, row in enumerate(rows):
        caps = [cell_text(v).upper() for v in row]
        id_cols = [ci for ci, cap in enumerate(caps, start=1) if cap in HEADER_SYNONYMS["id"]]
        if not id_cols or not any(c in caps for c in HEADER_SYNONYMS["time"]):
            continue
        cols: Dict[str, int] = {"id": id_cols[0]}
        if len(id_cols) >= 2:
            cols["in_id"] = id_cols[1]        # second ID column = inbound headcode
        for ci, cap in enumerate(caps, start=1):
            for fld, syns in HEADER_SYNONYMS.items():
                if fld not in cols and cap in syns:
                    cols[fld] = ci
                    break
        i = cols["id"]                        # TLGN CWNs: the day code column after ID has no heading
        if "days" not in cols and i < len(caps) and not caps[i] and (i + 1) not in set(cols.values()):
            cols["days"] = i + 1
        if "from" in cols:                    # unlabelled columns either side of FROM
            f = cols["from"]
            used = set(cols.values())
            if f > 1 and not caps[f - 2] and (f - 1) not in used:
                cols["dep"] = f - 1
            if f < len(caps) and not caps[f] and (f + 1) not in used:
                cols["fp"] = f + 1
        return idx + 1, cols, max(cols.values())
    return None


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_workbook(wb) -> CWNModel:
    """Works with normal and read-only openpyxl workbooks."""
    sheets: Dict[str, SheetModel] = {}
    others: List[str] = []
    warnings: List[str] = []
    hints: List[str] = []
    for ws in wb.worksheets:
        if ws.title.startswith("_CWNCompare"):
            continue
        try:
            sm = parse_sheet(ws)
        except Exception as exc:   # one odd tab must not stop the whole comparison
            warnings.append(f"Tab '{ws.title}' could not be read and was skipped ({exc}).")
            others.append(ws.title)
            continue
        if sm is None:
            others.append(ws.title)
            hints.append(ws.title)
            hints.extend(_head_text(ws, 30))
            continue
        hints.append(ws.title)
        hints.extend(_head_text(ws, sm.header_row - 1))
        k, n = sm.key, 2
        while k in sheets:
            k = f"{sm.key}#{n}"
            n += 1
        sm.key = k
        for b in sm.blocks:
            b.sheet = k
        sheets[k] = sm
    return CWNModel(sheets, others, warnings, " ".join(h for h in hints if h)[:4000])


def _head_text(ws, rows: int) -> List[str]:
    """Text in the first rows of a sheet (cover wording, titles above the headings)."""
    if rows < 1:
        return []
    try:
        return [cell_text(v) for row in ws.iter_rows(min_row=1, max_row=rows, max_col=20, values_only=True)
                for v in row if isinstance(v, str) and v.strip()]
    except Exception:
        return []


def _spec_value(v):
    """Serialisable copy of a cell value (times kept as day fractions so they re-parse identically)."""
    if v is None or type(v) is str:
        return cell_text(v)
    if isinstance(v, bool):
        return cell_text(v)
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, _dt.time) or (isinstance(v, _dt.datetime) and v.year <= 1900):
        return (v.hour * 60 + v.minute) / 1440
    return cell_text(v)


def _style_of(cell) -> dict:
    try:
        font, fill = cell.font, cell.fill
        rgb = fill.fgColor.rgb if fill is not None and fill.fill_type == "solid" else None
        return {"b": bool(font.b), "i": bool(font.i), "fill": rgb if isinstance(rgb, str) else None}
    except AttributeError:      # empty read-only cell
        return {"b": False, "i": False, "fill": None}


def parse_sheet(ws) -> Optional[SheetModel]:
    head_rows = list(ws.iter_rows(min_row=1, max_row=15, values_only=True))
    found = find_header(head_rows)
    if not found:
        return None
    header_row, cols, max_col = found
    id_i = cols["id"] - 1
    check = [c - 1 for f, c in cols.items() if f != "loc"]
    specs = []
    for r, cells in enumerate(ws.iter_rows(min_row=header_row + 1, max_col=max_col), start=header_row + 1):
        vals = [c.value for c in cells]
        if not any(i < len(vals) and vals[i] not in (None, "") and cell_text(vals[i]) for i in check):
            continue
        spec = {"r": r, "v": [_spec_value(v) for v in vals]}
        spec.update(_style_of(cells[id_i]) if id_i < len(cells) else {"b": False, "i": False, "fill": None})
        specs.append(spec)
    return build_sheet(ws.title, header_row, cols, max_col, specs)


def build_sheet(title: str, header_row: int, cols: Dict[str, int], max_col: int,
                specs: List[dict]) -> SheetModel:
    """Group data rows (row specs) into train blocks."""
    key = sheet_key(title)
    groups: List[dict] = []
    cur: Optional[dict] = None
    for spec in specs:
        row = spec["v"]
        vals = {f: (row[c - 1] if c <= len(row) else None) for f, c in cols.items()}
        text = {f: cell_text(v) for f, v in vals.items()}
        out_id = text.get("id", "")
        is_berth_row = not out_id and text.get("dest", "").casefold().startswith("berth")
        if out_id or cur is None or (is_berth_row and (text.get("in_id") or not cur["berth"])):
            cur = {"rows": [], "berth": not out_id}
            groups.append(cur)
        cur["rows"].append((spec["r"], vals, text, spec))

    blocks = [_build_block(key, g) for g in groups]
    # Unique keys: headcode|days, disambiguated by inbound headcode then a counter
    counts: Dict[str, int] = {}
    for b in blocks:
        counts[b.key] = counts.get(b.key, 0) + 1
    seen: Dict[str, int] = {}
    for i, b in enumerate(blocks):
        b.order = i
        k = b.key
        if counts[k] > 1:
            k = f"{k}|{b.main.get('in_id', '')}"
        seen[k] = seen.get(k, 0) + 1
        b.key = k if seen[k] == 1 else f"{k}#{seen[k]}"
        b.sort_time = time_minutes(b.main.get("time") or b.main.get("inwards") or "")
    return SheetModel(key, title, header_row, cols, max_col, blocks)


def _display_row(vals: dict, text: dict, out_ecs: bool) -> dict:
    """Display text of one row; times formatted HH.MM / HH+MM."""
    d = dict(text)
    if "time" in d:
        d["time"] = time_text(vals["time"], out_ecs)
    in_ecs = is_ecs(text["in_id"]) if text.get("in_id") else out_ecs
    for f in ("dep", "inwards"):
        if f in d:
            d[f] = time_text(vals[f], in_ecs)
    return d


def _normalise(d: dict) -> dict:
    n = {f: v.casefold() for f, v in d.items()}
    for f in ("unit", "diag"):
        if f in n:
            n[f] = norm_bracket(n[f])
    if "days" in n:
        n["days"] = canon_days(d["days"]).casefold()
    return n


def _build_block(sheet: str, group: dict) -> Block:
    rows = group["rows"]
    r0, v0, t0, _ = rows[0]
    out_ecs = is_ecs(t0.get("id", ""))
    raw = _display_row(v0, t0, out_ecs)
    main = _normalise(raw)
    units: List[UnitRow] = []
    notes, nw, in_ids = [], [], []
    if is_next_working(raw.get("dest", "")):
        nw.append((r0, canon_next_working(raw["dest"]), raw["dest"]))
    for i, (r, v, t, _) in enumerate(rows):
        d = raw if i == 0 else _display_row(v, t, out_ecs)
        n = main if i == 0 else _normalise(d)
        if n.get("in_id"):
            in_ids.append(n["in_id"])
        dest = d.get("dest", "")
        if i > 0 and is_next_working(dest):
            nw.append((r, canon_next_working(dest), dest))
            dest_is_nw = True
        else:
            dest_is_nw = False
        if d.get("unit") or (i == 0 and (d.get("diag") or d.get("pm"))):
            units.append(UnitRow(
                row=r, unit=n.get("unit", ""), am=n.get("am", ""), pm=n.get("pm", ""),
                diag=n.get("diag", ""), portion="" if (i == 0 or dest_is_nw) else n.get("dest", ""),
                in_id=n.get("in_id", ""), dep=n.get("dep", ""), frm=n.get("from", ""),
                fp=n.get("fp", ""), inwards=n.get("inwards", ""), raw=d))
        elif i > 0 and not dest_is_nw:
            note = dest or " ".join(x for f, x in d.items() if f != "loc" and x)
            if is_next_working(note):
                nw.append((r, canon_next_working(note), note))
            elif note:
                notes.append((r, note.casefold(), note))
    if group["berth"]:
        base = main.get("in_id", "")
        key = "BERTH|" + (base or main.get("dest", ""))
    else:
        base = main.get("id", "")
        key = base
    variant = canon_days(raw["days"]) if raw.get("days") else next_working_days(t for _r, _k, t in nw)
    if variant:
        key += "|" + variant.casefold()
    return Block(sheet=sheet, key=key, base_id=base, days=main.get("days", ""),
                 is_berth=group["berth"], start_row=r0, end_row=rows[-1][0], main=main, raw=raw,
                 units=units, notes=notes, nw=nw, rows=[s for (*_, s) in rows], in_ids=in_ids,
                 variant=variant)


# --------------------------------------------------------------------------- #
# (De)serialisation - the baseline stored inside a comparison CWN keeps only the
# raw rows of each tab; blocks are rebuilt with the same parser when read back.
# --------------------------------------------------------------------------- #
def model_to_dict(m: CWNModel) -> dict:
    return {"v": 2, "other": m.other_sheets, "hint": m.day_hint, "sheets": [{
        "key": sh.key, "title": sh.title, "header_row": sh.header_row, "cols": sh.cols,
        "max_col": sh.max_col, "rows": [spec for b in sh.blocks for spec in b.rows],
    } for sh in m.sheets.values()]}


def model_from_dict(d: dict) -> CWNModel:
    sheets = {}
    for s in d["sheets"]:
        if "rows" not in s:
            raise ValueError("This comparison CWN was made by an older version of the app. "
                             "Please re-run the original comparison with this version first.")
        sm = build_sheet(s["title"], s["header_row"], {k: int(v) for k, v in s["cols"].items()},
                         s["max_col"], s["rows"])
        sm.key = s["key"]
        for b in sm.blocks:
            b.sheet = sm.key
        sheets[sm.key] = sm
    return CWNModel(sheets, d.get("other", []), day_hint=d.get("hint", ""))
