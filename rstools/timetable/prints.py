"""Compare two sets of train prints (PDF or Word): each train's whole journey and details.

A train print shows, for each train, a heading (headcode, often the UID, days and dates) and then
one line per location with its arrival / departure (or passing) times and the other details of that
call (platform, line, path, activities, allowances...). Layouts differ between systems, so the
reader works on the text of the print rather than fixed positions:

* every page is turned into fixed-width lines (PDF text keeps its layout; Word tables are laid out
  as columns), so columns line up as they do on paper;
* a train starts at a heading line holding a headcode with a UID or a word such as 'Train' or
  'Headcode' (a heading repeated on the next page continues the same train);
* a location line is text followed by one or more times; times are read under the 'Arr' / 'Dep' /
  'Pass' column headings when the print has them;
* page numbers, print dates and repeated column headings are ignored.

Trains are paired one-to-one by headcode and UID (or headcode, days and first time), and each pair
is compared location by location, so a removed call shows once rather than shifting every line.
"""
from __future__ import annotations

import difflib
import logging
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, cast

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TIME = re.compile(r"(?<![\d/:.])([01]\d|2[0-3])[:.]?([0-5]\d)(½|H)?(?![\d/])")
_HEADCODE = re.compile(r"\b(\d[A-Z]\d{2})(?:[A-Z0-9]{2})?\b")
_UID = re.compile(r"\b([A-Z]\d{5})\b")
_HEAD_WORD = re.compile(r"\b(train|head\s*code|headcode|schedule|uid|service|reporting\s+number|signalling\s+id)\b",
                        re.I)
_DAYS = re.compile(r"\b(M?T?W?(?:TH)?F?S?(?:SU)?O|SX|SO|SUO|MSX|FSX|MX|FX|MO|FO|[MTWFS]{2,7}|"
                   r"(?:[M-][T-][W-][T-][F-][S-][S-]))\b")
_NOISE = re.compile(r"(\bpage\s+\d+(\s+of\s+\d+)?\b|\bprinted\b|\bprint\s+date\b|\brun\s+date\b|"
                    r"\bgenerated\b|\bcreated\b|"
                    r"^\s*[-=_.\s]{4,}\s*$)", re.I)
_COLUMN_WORDS = {"arr": "arr", "arrive": "arr", "arrival": "arr", "dep": "dep", "depart": "dep",
                 "departure": "dep", "pass": "pass", "pas": "pass", "passing": "pass"}


# pypdf logs its own notes about damaged files ('EOF marker not found'); a file that cannot be read is
# reported to the user as a PrintError instead
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PrintError(Exception):
    pass


@dataclass
class Call:
    loc: str                    # location as shown
    key: str                    # normalised location (for pairing)
    times: Dict[str, str]       # 'arr' / 'dep' / 'pass' / 'time' -> HHMM (½ kept)
    details: str                # the rest of the line (platform, line, activities...)
    fields: Dict[str, str] = field(default_factory=dict)    # named columns, when the layout is known
    tiploc: str = ""            # the location code, where the source gives it (Attune prints, VPT)


@dataclass
class PrintTrain:
    headcode: str
    uid: str
    days: str
    heading: List[str]          # heading / detail lines (normalised)
    calls: List[Call] = field(default_factory=list)
    source: str = ""            # file the train came from
    page: int = 0
    ident: str = ""             # full train ID when the print gives one (e.g. 1H05BS)
    info: Dict[str, str] = field(default_factory=dict)      # named heading fields, when the layout is known
    skipped: List[str] = field(default_factory=list)         # Attune location lines that could not be read
    kind: str = ""              # 'vpt' for a Voyager plan train export (not a train print)
    lacks: frozenset = frozenset()      # time columns this kind of file never has (so they are not compared)
    dayset: Optional[frozenset] = None  # the weekdays (0 = Monday) when the file gives them exactly

    @property
    def day_key(self):
        """The days as a set of weekdays, so 'SX' and 'MTWThF' are the same days; the text if it cannot be read."""
        if self.dayset is not None:
            return self.dayset
        from rstools.statspack.days import days_of_code
        found = days_of_code(self.days)
        return frozenset(found) if found else self.days

    @property
    def first_key(self) -> str:
        """The first time without its marker ('05a52½' and '05.52½' are the same time)."""
        return plain_time(self.first_time)

    @property
    def first_time(self) -> str:
        for c in self.calls:
            for role in ("dep", "wtt_dep", "pub_dep", "time", "pass", "arr", "wtt_arr", "pub_arr"):
                if c.times.get(role):
                    return c.times[role]
        return ""

    @property
    def origin(self) -> str:
        return self.calls[0].loc if self.calls else ""

    @property
    def destination(self) -> str:
        return self.calls[-1].loc if self.calls else ""

    def label(self) -> str:
        return " ".join(x for x in (self.ident or self.headcode, self.uid) if x) or "(no headcode)"


_PLAIN = re.compile(r"^(\d\d)[./apAP ]?(\d\d)(½)?$")


def plain_time(text: str) -> str:
    """A time as HHMM (with its half): '05a52½' -> '0552½'; anything else as it is."""
    m = _PLAIN.match((text or "").strip())
    return f"{m.group(1)}{m.group(2)}{m.group(3) or ''}" if m else (text or "")


# ----------------------------------------------------------------------- reading
def _norm(text: str) -> str:
    return " ".join(text.split())


def _docx_lines(path: str) -> List[List[str]]:
    """Word: paragraphs as they are, tables laid out as fixed-width columns. One page per page break."""
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    try:
        with zipfile.ZipFile(path) as z:
            from rstools.fsutil import zip_read
            root = ET.fromstring(zip_read(z, "word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError) as exc:
        raise PrintError(f"'{os.path.basename(path)}' could not be read as a Word document ({exc}).")
    body = root.find(f"{W}body")
    pages: List[List[str]] = [[]]

    def para_text(p) -> str:
        out = []
        for node in p.iter():
            if node.tag == f"{W}t" and node.text:
                out.append(node.text)
            elif node.tag == f"{W}tab":
                out.append("    ")
            elif node.tag == f"{W}br" and node.get(f"{W}type") == "page":
                out.append("\f")
        return "".join(out)

    for el in list(body) if body is not None else []:
        if el.tag == f"{W}p":
            for i, part in enumerate(para_text(el).split("\f")):
                if i:
                    pages.append([])
                pages[-1].append(part)
        elif el.tag == f"{W}tbl":
            grid = [[_norm(" ".join(para_text(p) for p in tc.iter(f"{W}p"))) for tc in tr.iter(f"{W}tc")]
                    for tr in el.iter(f"{W}tr")]
            width = max((len(r) for r in grid), default=0)
            sizes = [max((len(r[c]) for r in grid if c < len(r)), default=0) for c in range(width)]
            for r in grid:
                pages[-1].append("  ".join(cell.ljust(sizes[c]) for c, cell in enumerate(r)).rstrip())
    return [p for p in pages if any(line.strip() for line in p)]


PAGES_PER_WORKER = 25            # below this many pages a PDF is read on one core


def _page_text(page) -> List[str]:
    try:
        text = page.extract_text(extraction_mode="layout")
    except Exception:                           # unusual page content: fall back to plain extraction
        text = page.extract_text() or ""
    return text.splitlines()


def _pdf_range(path: str, start: int, stop: int) -> List[List[str]]:
    """Text of pages start..stop-1 (run in a helper process for big PDFs)."""
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    from pypdf import PdfReader
    reader = PdfReader(path)
    return [_page_text(reader.pages[i]) for i in range(start, stop)]


# --- fast path: PDFium (about ten times quicker than pypdf) for Attune Single Train Reports
def _pdfium_page(page) -> List[str]:
    """One page as PlacedLines: characters grouped into lines by baseline, into words by the gaps
    between them (a gap wider than ~0.42 em starts a new table cell), each word keeping its x."""
    import ctypes
    import pypdfium2.raw as raw
    from .attune_print import PlacedLine
    tp = page.get_textpage()
    try:
        n = tp.count_chars()
        text = tp.get_text_range(0, n) if n else ""
        ox, oy = ctypes.c_double(), ctypes.c_double()
        chars = []
        spaces = 0                      # real space characters (not ones PDFium adds) before this one
        for i in range(min(n, len(text))):
            ch = text[i]
            if not ch.strip():
                if ch in " \xa0" and raw.FPDFText_IsGenerated(tp.raw, i) == 0:
                    spaces += 1
                elif ch in "\r\n":
                    spaces = 0
                continue
            x0, y0, x1, y1 = tp.get_charbox(i, loose=True)
            raw.FPDFText_GetCharOrigin(tp.raw, i, ox, oy)
            chars.append((x0, x1, oy.value, (y1 - y0) / 1.15, ch, spaces))   # left, right, baseline, em, text
            spaces = 0
    finally:
        tp.close()
    rows: List[list] = []
    for c in sorted(chars, key=lambda c: -c[2]):                       # top of the page first
        if rows and rows[-1][0] - c[2] <= 0.3 * c[3]:
            rows[-1][1].append(c)
        else:
            rows.append([c[2], [c]])
    # a table cell wrapped onto two lines starts half a line above its row ('Southampton Airport' /
    # 'Parkway'): its first line belongs to the row, as on paper
    left = min((c[0] for c in chars), default=0.0)
    merged: List[list] = []
    for y, cs in rows:
        if merged and merged[-1][2] and min(c[0] for c in cs) <= left + 2 and merged[-1][0] - y <= 0.75 * cs[0][3]:
            cs = merged.pop()[1] + cs
        fragment = min(c[0] for c in cs) > left + 20
        merged.append([y, cs, fragment])
    out: List[str] = []
    for _y, cs, _frag in merged:
        cs.sort(key=lambda c: c[0])
        text, spans, last = "", [], None
        for x0, x1, _b, em, ch, spaces in cs:
            gap = x0 - last if last is not None else 0.0
            if last is None or gap > 0.08 * em or spaces:               # a new word...
                if text:                                                 # ...in a new cell, or the same one:
                    if spaces:                                           # the PDF's own spaces say which
                        new_cell = spaces >= 2 or gap > 1.6 * (x1 - x0) * 2
                    else:                                                # else the width of the gap
                        new_cell = gap > 0.42 * em
                    text += "  " if new_cell else " "
                spans.append([len(text), len(text), x0, x1])
            text += ch
            spans[-1][1], spans[-1][3] = len(text), max(spans[-1][3], x1)
            last = x1 if last is None else max(last, x1)
        out.append(PlacedLine(text, [tuple(s) for s in spans]))
    return out


def _pdfium_range(path: str, start: int, stop: int) -> List[List[str]]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        return [_pdfium_page(doc[i]) for i in range(start, stop)]
    finally:
        doc.close()


def _pdfium_probe(path: str) -> Tuple[int, bool]:
    """(pages, is an Attune Single Train Report) - run in a helper process."""
    import pypdfium2 as pdfium
    from .attune_print import is_attune_report
    doc = pdfium.PdfDocument(path)
    try:
        count = len(doc)
        return count, bool(count) and is_attune_report([_pdfium_page(doc[0])])
    finally:
        doc.close()


def _pdfium_lines(path: str) -> Optional[List[List[str]]]:
    """An Attune Single Train Report read with PDFium, or None (not installed, another layout, or the
    file could not be read this way) so the pure-Python pypdf reader is used instead.

    PDFium is native code, so it only ever runs in helper processes: a damaged or hostile PDF that made
    it crash would end that helper, never the app, and the file is then read with pypdf."""
    import importlib.util
    import multiprocessing
    if importlib.util.find_spec("pypdfium2") is None:
        return None
    if multiprocessing.parent_process() is not None:      # already a helper process (e.g. one of several
        try:                                               # files read at once): read it here
            count, attune = _pdfium_probe(path)
            return _pdfium_range(path, 0, count) if attune else None
        except Exception:
            return None
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    workers = max(1, (os.cpu_count() or 1) - 1)
    try:
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
    except Exception:
        return None
    ok = False
    try:
        count, attune = pool.submit(_pdfium_probe, path).result(timeout=120)
        if not attune:
            ok = True
            return None
        parts = max(1, min(workers, count // (PAGES_PER_WORKER * 4)))
        step = -(-count // parts) if count else 1
        jobs = [pool.submit(_pdfium_range, path, a, min(a + step, count)) for a in range(0, count, step)]
        pages = [page for job in jobs for page in job.result(timeout=60 + count)]
        ok = True
        return pages
    except Exception:                       # a helper failed, crashed or hung: the caller reads it with pypdf
        return None
    finally:
        if not ok:                          # never wait for a stuck helper: stop it
            for proc in list(getattr(pool, "_processes", {}).values()):
                try:
                    proc.kill()
                except Exception:
                    pass
        pool.shutdown(wait=ok, cancel_futures=True)


def _pdf_lines(path: str) -> List[List[str]]:
    """Every page's text, laid out as on paper. An Attune Single Train Report is read with PDFium when
    available (much quicker); otherwise pypdf, with a big PDF split into page ranges read on several
    CPU cores at once (one core is left free for the window); it falls back to one core if that fails."""
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    fast = _pdfium_lines(path)
    if fast is not None:
        return fast
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        count = len(reader.pages)
        pages = None
        workers = min((os.cpu_count() or 1) - 1, count // PAGES_PER_WORKER)
        import multiprocessing
        if workers >= 2 and multiprocessing.parent_process() is None:     # not already in a helper process
            pages = _parallel(_pdf_range, path, count, workers)
        if pages is None:
            pages = [_page_text(page) for page in reader.pages]
    except PrintError:
        raise
    except Exception as exc:
        raise PrintError(f"'{os.path.basename(path)}' could not be read as a PDF ({exc}).")
    if pages and not any(line.strip() for p in pages for line in p):
        raise PrintError(f"'{os.path.basename(path)}' has no text to read (it may be a scanned image). "
                         "Save the print from the planning system as a PDF or Word file instead.")
    return pages


def _parallel(reader, path: str, count: int, workers: int) -> Optional[List[List[str]]]:
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    step = -(-count // workers)
    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
            parts = [pool.submit(reader, path, a, min(a + step, count)) for a in range(0, count, step)]
            return [page for part in parts for page in part.result()]
    except Exception:                           # helper processes unavailable: read it here instead
        return None


def read_print(path: str) -> List[PrintTrain]:
    if os.path.splitext(path)[1].lower() == ".vpt":
        from .vpt import read_vpt
        return read_vpt(path)
    pages = read_pages(path)
    from .attune_print import is_attune_report, parse_attune
    if is_attune_report(pages):
        return [from_attune(t) for t in parse_attune(pages, os.path.basename(path))]
    return parse_pages(pages, os.path.basename(path))


def read_pages(path: str) -> List[List[str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _pdf_lines(path)
    if ext in (".docx", ".docm"):
        return _docx_lines(path)
    raise PrintError(f"'{os.path.basename(path)}': train prints must be PDF (.pdf), Word (.docx) or Attune "
                     "Voyager plan train export (.vpt) files.")


def from_attune(t) -> "PrintTrain":
    """An Attune Single Train Report train, with every column kept under its own name."""
    from .attune_print import TIME_COLS
    calls = []
    for r in t.rows:
        times = {k: v for k, v in r.values.items() if k in TIME_COLS or k == "pass"}
        rest = {k: v for k, v in r.values.items() if k not in times}
        calls.append(Call(r.name, _loc_key(r.name), times, " ".join(rest.values()), rest, r.tiploc))
    info = dict(t.fields)
    info.update({"Train category": t.category, "Operator": t.toc_name})
    return PrintTrain(t.headcode, t.uid, t.days, [], calls, t.source, t.page, ident=t.train_id, info=info,
                      skipped=list(getattr(t, "skipped", [])))


def _is_heading(line: str) -> Optional[Tuple[str, str]]:
    """(headcode, uid) when the line starts a train."""
    hc = _HEADCODE.search(line)
    if not hc:
        return None
    uid = _UID.search(line.replace(hc.group(0), " "))
    times = _TIME.findall(line)
    start = line.strip()
    led = _HEAD_WORD.match(start) or start.startswith(hc.group(0))     # 'Train 1A23 ...' / '1A23 ...'
    if (uid or led) and len(times) <= 1 or uid and _HEAD_WORD.search(line):
        return hc.group(1), uid.group(1) if uid else ""
    return None


def _columns(line: str) -> Optional[Dict[int, str]]:
    """Positions of the Arr / Dep / Pass column headings, when the line is a column-heading line."""
    found = {}
    for m in re.finditer(r"[A-Za-z]+", line):
        role = _COLUMN_WORDS.get(m.group(0).lower())
        if role:
            found[(m.start() + m.end()) // 2] = role
    return found if len(found) >= 2 else None


def _call(line: str, columns: Optional[Dict[int, str]]) -> Optional[Call]:
    times = list(_TIME.finditer(line))
    if not times:
        return None
    loc = line[:times[0].start()].strip(" .:-|\t")
    if len(re.sub(r"[^A-Za-z]", "", loc)) < 2 or _HEADCODE.fullmatch(loc.split()[-1] if loc.split() else ""):
        return None
    shown: Dict[str, str] = {}
    for i, m in enumerate(times):
        value = m.group(1) + m.group(2) + ("½" if m.group(3) else "")
        if columns:
            centre = (m.start() + m.end()) // 2
            role = columns[min(columns, key=lambda pos: abs(pos - centre))]
        elif len(times) >= 2:
            role = ("arr", "dep")[min(i, 1)] if i < 2 else f"time{i + 1}"
        else:
            role = "time"
        if role in shown:                       # two times under one heading: keep both
            role = f"{role}{i + 1}"
        shown[role] = value
    pieces, prev = [], times[0].end()
    for m in times[1:]:
        pieces.append(line[prev:m.start()])
        prev = m.end()
    pieces.append(line[prev:])
    rest = _norm(" ".join(pieces).replace("|", " "))
    return Call(_norm(loc), _loc_key(loc), shown, rest)


def _loc_key(loc: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", loc).replace("&", " and ")
    return " ".join(re.sub(r"[^A-Za-z0-9 ]", " ", text).split()).casefold()


def parse_pages(pages: Sequence[Sequence[str]], source: str = "") -> List[PrintTrain]:
    trains: List[PrintTrain] = []
    current: Optional[PrintTrain] = None
    columns: Optional[Dict[int, str]] = None
    for page_no, lines in enumerate(pages, start=1):
        for line in lines:
            line = line.replace("\t", "    ").rstrip()
            if not line.strip() or _NOISE.search(line):
                continue
            head = _is_heading(line)
            if head:
                hc, uid = head
                if current and current.heading and current.heading[0] == _norm(line):
                    continue                    # the heading repeated on the next page
                days = _DAYS.search(_HEADCODE.sub(" ", _UID.sub(" ", line)))
                current = PrintTrain(hc, uid, days.group(1) if days else "", [_norm(line)], source=source,
                                     page=page_no)
                trains.append(current)
                columns = None
                continue
            if current is None:
                continue
            cols = _columns(line)
            if cols:
                columns = cols
                continue
            call = _call(line, columns)
            if call:
                current.calls.append(call)
            elif _norm(line) not in current.heading:
                current.heading.append(_norm(line))
    return trains


# ----------------------------------------------------------------------- comparing
@dataclass
class PrintChange:
    train: str
    days: str
    location: str
    change: str
    original: str
    updated: str


@dataclass
class PrintComparison:
    original: List[PrintTrain]
    updated: List[PrintTrain]
    pairs: List[Tuple[PrintTrain, PrintTrain, str, int]]    # (original, updated, how paired, changes)
    added: List[PrintTrain]
    removed: List[PrintTrain]
    changes: List[PrintChange]
    warnings: List[str]
    passenger_only: bool = False        # passing and working-only times left out (see passenger_calls)


def has_public(*trains: Optional["PrintTrain"]) -> bool:
    """The prints show public times (Attune Single Train Report), so a call without one is not for passengers."""
    return any(k.startswith("pub_") and v for t in trains if t is not None for c in t.calls for k, v in c.times.items())


def is_passenger_call(c: "Call", public: bool) -> bool:
    """A call passengers see: with a public time where the prints show them; otherwise any call that is not only a
    passing time."""
    if public:
        return any(c.times.get(k) for k in ("pub_arr", "pub_dep"))
    return any(v for k, v in c.times.items() if k != "pass")


def passenger_calls(t: Optional["PrintTrain"], public: bool) -> List["Call"]:
    return [c for c in t.calls if is_passenger_call(c, public)] if t is not None else []


# a VPT and a train print name and lay out these differently, so only these are compared between the two kinds
CROSS_INFO = ("TrainID", "From", "Until")
CROSS_LACKS = frozenset({"activity", "line", "dwell", "eng", "pth", "prf", "adj"})
_DETAIL_KEYS = ("plat", "line", "activity", "dwell", ("eng", "pth", "prf", "adj"))


def _same_time(ta: str, tb: str, cross: bool) -> bool:
    """Equal times; between a VPT and a print also when only the marker differs ('05a52½' / '05.52½')."""
    return ta == tb or (cross and plain_time(ta) == plain_time(tb))


def _ignored(a: Optional["PrintTrain"], b: Optional["PrintTrain"]) -> frozenset:
    """The time columns and fields not compared for this pair: what a VPT never has, and, between a VPT and a print,
    the fields the two lay out differently."""
    if a is None or b is None:
        return frozenset()
    out = set(a.lacks) | set(b.lacks)
    if a.kind != b.kind:
        out |= CROSS_LACKS
    return frozenset(out)


def _calls_for(a: Optional["PrintTrain"], b: Optional["PrintTrain"], passenger_only: bool):
    """The calls compared on each side. Passenger times only: a call with a public time (or, for a VPT, which has
    none, any stop); against a print, a VPT's stops that the print does not show to passengers are left out."""
    calls_a, calls_b = (a.calls if a else []), (b.calls if b else [])
    if not passenger_only:
        return calls_a, calls_b
    public = has_public(a, b)
    calls_a = passenger_calls(a, public and not (a and a.kind))
    calls_b = passenger_calls(b, public and not (b and b.kind))
    if a is not None and b is not None and a.kind != b.kind:
        keys_a, keys_b = {c.key for c in calls_a}, {c.key for c in calls_b}
        if a.kind:
            calls_a = [c for c in calls_a if c.key in keys_b]
        else:
            calls_b = [c for c in calls_b if c.key in keys_a]
    return calls_a, calls_b


def _pair(orig: List[PrintTrain], upd: List[PrintTrain]):
    """One-to-one pairs: headcode + UID, then headcode + days + first time, then headcode + first time,
    then a headcode that appears once on each side."""
    pairs, left, right = [], list(orig), list(upd)
    rules = (("Headcode, UID and days", lambda t: (t.headcode, t.uid, t.day_key) if t.uid else None),
             ("Train ID and days", lambda t: (t.ident, t.day_key) if t.ident else None),
             ("Headcode, days and first time", lambda t: (t.headcode, t.day_key, t.first_key)),
             ("Headcode and first time", lambda t: (t.headcode, t.first_key)),
             ("Headcode (only one on each side)", lambda t: t.headcode))
    for how, key in rules:
        index: Dict[object, List[PrintTrain]] = {}
        for t in right:
            k = key(t)
            if k is not None:
                index.setdefault(k, []).append(t)
        if how.startswith("Headcode (only"):
            counts: Dict[object, int] = {}
            for t in left:
                counts[t.headcode] = counts.get(t.headcode, 0) + 1
        still, taken = [], set()
        for t in left:
            k = key(t)
            cands = index.get(k) if k is not None else None
            if cands and (not how.startswith("Headcode (only") or (len(cands) == 1 and counts[k] == 1)):
                u = cands.pop(0)
                taken.add(id(u))                    # (a set: thousands of trains pair in moments)
                pairs.append((t, u, how))
            else:
                still.append(t)
        left = still
        right = [u for u in right if id(u) not in taken]
    return pairs, right, left


_TIME_NAMES = {"arr": "Arrival", "dep": "Departure", "pass": "Passing", "time": "Time", "wtt_arr": "Working arrival",
               "wtt_dep": "Working departure", "pub_arr": "Public arrival", "pub_dep": "Public departure"}
_FIELD_NAMES = {"dwell": "Dwell", "activity": "Activity", "plat": "Platform", "line": "Line",
                "eng": "Engineering allowance", "pth": "Pathing allowance", "prf": "Performance allowance",
                "adj": "Adjustment allowance", "off_arr": "Public offset (arr)", "off_dep": "Public offset (dep)"}


def _fmt_times(c: Call) -> str:
    return ", ".join(f"{_TIME_NAMES.get(role, role).lower()} {t}" for role, t in c.times.items())


KIND_ORDER = ("Days run", "TID", "UID", "Header", "Calling points", "Timing", "Platform/line", "Activity",
              "Dwell/allowances", "Details")
_TID_KEYS = ("TrainID", "SignalID", "RSID Headcode", "Train", "Headcode")


def change_kind(c: "PrintChange") -> str:
    """The broad nature of a change: 'Timing', 'TID', 'Days run', 'UID', 'Header', 'Calling points'..."""
    what = c.change
    if c.location == "(train details)":
        key = what[:-len(" changed")] if what.endswith(" changed") else what
        if key in ("Days Pattern", "Days run"):
            return "Days run"
        if key in _TID_KEYS:
            return "TID"
        if key in ("Train UID", "UID"):
            return "UID"
        return "Header"
    if what.startswith("Location"):
        return "Calling points"
    if " time " in what:
        return "Timing"
    if what.startswith(("Platform", "Line")):
        return "Platform/line"
    if what.startswith("Activity"):
        return "Activity"
    if what.startswith(("Dwell", "Engineering", "Pathing", "Performance", "Adjustment")):
        return "Dwell/allowances"
    return "Details"


def kinds_text(changes: Iterable["PrintChange"]) -> str:
    """'Timing, TID change' for a set of changes ('No change' for none)."""
    found = {change_kind(c) for c in changes}
    return ", ".join(k for k in KIND_ORDER if k in found) + " change" if found else "No change"


def _compare_pair(a: PrintTrain, b: PrintTrain, passenger_only: bool = False, header: bool = True,
                  timing: bool = True) -> List[PrintChange]:
    """The differences between two paired trains. `passenger_only`: passing times and calls with no public time
    are left out (one print may not show the intermediate timing points). `header` / `timing`: whether the train's
    header details (days, IDs, class...) and the times are compared."""
    out: List[PrintChange] = []
    calls_a, calls_b = _calls_for(a, b, passenger_only)
    skip, cross = _ignored(a, b), a.kind != b.kind
    label = a.label() if a.label() == b.label() else f"{a.label()} / {b.label()}"
    days = a.days if a.days == b.days else f"{a.days} / {b.days}".strip(" /")
    for key in dict.fromkeys(list(a.info) + list(b.info)) if header else ():
        va, vb = a.info.get(key, ""), b.info.get(key, "")
        if cross and key not in CROSS_INFO:
            continue                                    # a VPT and a print name and format these differently
        if key == "Days Pattern":
            same = a.day_key == b.day_key
        else:
            same = va == vb
        if not same:
            out.append(PrintChange(label, days, "(train details)", f"{key} changed", va or "-", vb or "-"))
    if header and a.day_key != b.day_key and (cross or ("Days Pattern" not in a.info
                                                          and "Days Pattern" not in b.info)):
        out.append(PrintChange(label, days, "(train details)", "Days run changed", a.days or "-", b.days or "-"))
    ha, hb = [h for h in a.heading if h not in b.heading], [h for h in b.heading if h not in a.heading]
    if header and (ha or hb):
        out.append(PrintChange(label, days, "(train details)", "Train details changed", "\n".join(ha) or "-",
                               "\n".join(hb) or "-"))
    sm = difflib.SequenceMatcher(None, [c.key for c in calls_a], [c.key for c in calls_b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for ca, cb in zip(calls_a[i1:i2], calls_b[j1:j2]):
                for role in dict.fromkeys(list(ca.times) + list(cb.times)):
                    if (passenger_only and role == "pass") or role in skip:
                        continue
                    ta, tb = ca.times.get(role, ""), cb.times.get(role, "")
                    if not _same_time(ta, tb, cross) and timing:
                        name = _TIME_NAMES.get(role.rstrip("0123456789"), "Time")
                        what = (f"{name} time changed" if ta and tb else f"{name} time added" if tb
                                else f"{name} time removed")
                        out.append(PrintChange(label, days, ca.loc, what, ta or "-", tb or "-"))
                if ca.fields or cb.fields:
                    for key in dict.fromkeys(list(ca.fields) + list(cb.fields)):
                        fa, fb = ca.fields.get(key, ""), cb.fields.get(key, "")
                        if fa != fb and key not in skip:
                            out.append(PrintChange(label, days, ca.loc, f"{_FIELD_NAMES.get(key, key)} changed",
                                                   fa or "-", fb or "-"))
                elif ca.details != cb.details and not cross:
                    out.append(PrintChange(label, days, ca.loc, "Call details changed (platform, line, activity...)",
                                           ca.details or "-", cb.details or "-"))
            continue
        for ca in calls_a[i1:i2]:
            out.append(PrintChange(label, days, ca.loc, "Location removed", _fmt_times(ca), "-"))
        for cb in calls_b[j1:j2]:
            out.append(PrintChange(label, days, cb.loc, "Location added", "-", _fmt_times(cb)))
    return out


# ----------------------------------------------------------------------- side by side (Live View and report)
SIDE_COLUMNS = ["Location", "Arr/Dep", "Original", "Updated", "Public times", "Platform", "Line",
                "Activity / details", "Dwell", "Allowances", "Result"]
# train details shown above the calls, in this order (then any others the print has)
INFO_ORDER = ("Days Pattern", "Train UID", "From", "Until", "TrainID", "SignalID", "RSID Headcode", "Train Class",
              "Train Category", "Operator", "Power Type", "Timing Load", "Model Train", "Train Length (m)",
              "Limiting Speed", "Trailing Load", "Service Code", "ODT", "Origin Loc", "Origin Time",
              "Destination Loc", "Destination Time", "Distance", "Business Sector", "Brand", "Catering",
              "Reservations", "Accommodation", "Sleepers", "Bank Holidays", "Ops Char")
_ROLE_ORDER = ("wtt_arr", "arr", "wtt_dep", "dep", "pass", "time")
_ROLE_SHOWN = {"wtt_arr": "Arr", "arr": "Arr", "wtt_dep": "Dep", "dep": "Dep", "pass": "Pass", "time": "Time"}
_PUBLIC_OF = {"wtt_arr": "pub_arr", "arr": "pub_arr", "wtt_dep": "pub_dep", "dep": "pub_dep"}


def _both(a: str, b: str) -> str:
    """One value, or 'old → new' where the two prints differ."""
    a, b = a or "", b or ""
    return a if a == b else f"{a or '-'} → {b or '-'}"


def _call_details(c: Optional[Call]) -> List[str]:
    """Platform, line, activity (or the print's other details), dwell and allowances of a call."""
    if c is None:
        return [""] * 5
    f = c.fields
    if not f:
        return ["", "", c.details, "", ""]
    allow = " ".join(f"{k} {f[k]}" for k in ("eng", "pth", "prf", "adj") if f.get(k))
    return [f.get("plat", ""), f.get("line", ""), f.get("activity", ""), f.get("dwell", ""), allow]


def train_details(a: Optional[PrintTrain], b: Optional[PrintTrain]) -> List[Tuple[str, str, str]]:
    """(detail, original, updated) for the top of a side-by-side train: days run, IDs, dates, class..."""
    x, y = cast(PrintTrain, a or b), cast(PrintTrain, b or a)     # at least one side is a train
    partial = a is not None and b is not None and a.kind != b.kind      # a VPT against a print
    rows = [("Days run", a.days if a else "", b.days if b else ""),
            ("Train", (a.ident or a.headcode) if a else "", (b.ident or b.headcode) if b else ""),
            ("UID", a.uid if a else "", b.uid if b else "")]
    keys = [k for k in INFO_ORDER if k in x.info or k in y.info]
    keys += [k for k in dict.fromkeys(list(x.info) + list(y.info)) if k not in keys]
    seen = set()
    for k in keys:
        if partial and k not in CROSS_INFO:
            continue
        if k.casefold() in seen:                          # 'Train Category' and 'Train category'
            continue
        seen.add(k.casefold())
        if k in ("Days Pattern", "Train UID"):              # already shown as days run / UID
            continue
        rows.append((k, a.info.get(k, "") if a else "", b.info.get(k, "") if b else ""))
    if not x.info:                                       # a print without named fields: its heading lines
        ha, hb = (a.heading if a else []), (b.heading if b else [])
        for i in range(max(len(ha), len(hb))):
            rows.append((f"Heading {i + 1}" if i else "Heading", ha[i] if i < len(ha) else "",
                         hb[i] if i < len(hb) else ""))
    if partial:                                          # only what both have: the rest is not a difference
        return [r for r in rows if r[1] and r[2]]
    return [r for r in rows if r[1] or r[2]]


def _role_keys(ca: Optional[Call], cb: Optional[Call]) -> List[str]:
    have = set(ca.times if ca else ()) | set(cb.times if cb else ())
    keys = [k for k in _ROLE_ORDER if k in have]
    keys += sorted(k for k in have if k not in keys and not k.startswith("pub_"))
    return keys or [""]


def _location_rows(ca: Optional[Call], cb: Optional[Call], skip: frozenset = frozenset(),
                   cross: bool = False) -> List[Tuple[List[str], str]]:
    """The rows of one location: one per time (Arr / Dep / Pass), details on the first. `skip`: columns shown but
    not compared; `cross`: a VPT against a print."""
    out = []
    da, db = _call_details(ca), _call_details(cb)
    names = ("Platform", "Line", "Activity", "Dwell", "Allowances")
    for n, role in enumerate(_role_keys(ca, cb)):
        ta = ca.times.get(role, "") if ca and role else ""
        tb = cb.times.get(role, "") if cb and role else ""
        pub = _PUBLIC_OF.get(role, "")
        pa = ca.times.get(pub, "") if ca and pub else ""
        pb = cb.times.get(pub, "") if cb and pub else ""
        details = [_both(x, y) if not _skipped(key, skip) else (x or y)
                   for key, x, y in zip(_DETAIL_KEYS, da, db)] if n == 0 else [""] * 5
        pub_skipped = pub in skip
        if ca is None or cb is None:
            state, result = ("added", "Location added") if ca is None else ("removed", "Location removed")
        else:
            diffs = []
            if not _same_time(ta, tb, cross):
                diffs.append("Time added" if not ta else "Time removed" if not tb else "Time changed")
            if pa != pb and not pub_skipped:
                diffs.append("Public time changed")
            if n == 0:
                diffs += [f"{name} changed" for name, key, x, y in zip(names, _DETAIL_KEYS, da, db)
                          if x != y and not _skipped(key, skip)]
            state, result = ("changed", ", ".join(diffs)) if diffs else ("same", "Match")
        loc = cast(Call, ca or cb).loc if n == 0 else ""
        out.append(([loc, _ROLE_SHOWN.get(role, role), ta, tb, (pa or pb) if pub_skipped else _both(pa, pb)]
                    + details + [result], state))
    return out


def _skipped(key, skip: frozenset) -> bool:
    return any(k in skip for k in key) if isinstance(key, tuple) else key in skip


def side_by_side(a: Optional[PrintTrain], b: Optional[PrintTrain],
                 passenger_only: bool = False) -> List[Tuple[List[str], str]]:
    """A train from each set of prints laid out like the timetable comparison - one row per location
    and time, both prints' times side by side - with the print's own details (public times, platform,
    line, activity codes, dwell, allowances) and the train's details (days run, IDs, dates...) on top.
    Returns [(cells, state)], state 'same' / 'changed' / 'added' / 'removed' / 'muted' (train details)."""
    rows: List[Tuple[List[str], str]] = []
    skip, cross = _ignored(a, b), a is not None and b is not None and a.kind != b.kind
    for name, va, vb in train_details(a, b):
        same = va == vb or (name == "Days run" and a is not None and b is not None and a.day_key == b.day_key)
        state = "muted" if same or a is None or b is None else "changed"
        rows.append(([name, "", va, vb, "", "", "", "", "", "",
                      "" if state == "muted" else "Changed"], state))
    calls_a, calls_b = _calls_for(a, b, passenger_only)
    sm = difflib.SequenceMatcher(None, [c.key for c in calls_a], [c.key for c in calls_b], autojunk=False)
    calls: List[Tuple[List[str], str]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for ca, cb in zip(calls_a[i1:i2], calls_b[j1:j2]):
                calls += _location_rows(ca, cb, skip, cross)
            continue
        for ca in calls_a[i1:i2]:
            calls += _location_rows(ca, None)
        for cb in calls_b[j1:j2]:
            calls += _location_rows(None, cb)
    if passenger_only:
        calls = _without_passes(calls)
    return rows + calls


def _without_passes(rows: List[Tuple[List[str], str]]) -> List[Tuple[List[str], str]]:
    """Location rows without their 'Pass' lines (the location name moves to the next line of the location)."""
    out: List[Tuple[List[str], str]] = []
    carry = ""
    for cells, state in rows:
        if cells[1] == "Pass":
            carry = cells[0] or carry
            continue
        if carry and not cells[0]:
            cells = [carry] + cells[1:]
        carry = ""
        out.append((cells, state))
    return out


def _rekeyed(trains: List[PrintTrain], by_code: bool) -> List[PrintTrain]:
    """Copies of the trains whose calls are keyed by location code (or, where a code is missing, by name), so a VPT
    and a print find each other's calls; the originals (which may be cached) are left as they are."""
    out = []
    for t in trains:
        calls = [replace(c, key=c.tiploc.casefold() if by_code else _loc_key(c.loc)) for c in t.calls]
        out.append(replace(t, calls=calls))
    return out


def compare_prints(original: List[PrintTrain], updated: List[PrintTrain], warnings: Iterable[str] = (),
                   passenger_only: bool = False):
    if {bool(t.kind) for t in original} != {bool(t.kind) for t in updated} and original and updated:
        every = original + updated                      # a VPT on one side and prints on the other
        by_code = all(c.tiploc for t in every for c in t.calls)
        original, updated = _rekeyed(original, by_code), _rekeyed(updated, by_code)
    pairs, added, removed = _pair(original, updated)
    pairs.sort(key=lambda p: (p[0].source, p[0].page, p[0].first_time, p[0].headcode))
    changes, counted = [], []
    for a, b, how in pairs:
        found = _compare_pair(a, b, passenger_only)
        changes.extend(found)
        counted.append((a, b, how, len(found)))
    return PrintComparison(original, updated, counted, added, removed, changes, list(warnings), passenger_only)


def build_workbook(cmp: PrintComparison):
    from .xlstyle import add_sheet, new_workbook
    wb = new_workbook()
    changed = sum(1 for p in cmp.pairs if p[3])
    rows = [["Trains in the original print(s)", len(cmp.original)],
            ["Trains in the updated print(s)", len(cmp.updated)],
            ["Trains paired", len(cmp.pairs)],
            ["Paired trains with changes", changed],
            ["Paired trains unchanged", len(cmp.pairs) - changed],
            ["Trains added (updated only)", len(cmp.added)],
            ["Trains removed (original only)", len(cmp.removed)],
            ["Individual changes", len(cmp.changes)]]
    add_sheet(wb, "Summary", ["Figure", "Count"], rows, [38, 12], center=[2],
              fills={3: "bad" if changed else "ok", 5: "bad" if cmp.added else "ok", 6: "bad" if cmp.removed else "ok"})
    add_sheet(wb, "Changes by Train", ["Train", "Days", "Location", "Change", "Original", "Updated"],
              [[c.train, c.days, c.location, c.change, c.original, c.updated] for c in cmp.changes],
              [16, 10, 26, 34, 40, 40])
    # side by side: every train with a difference (and every added / removed train) laid out like the
    # timetable comparison, with the train's details on top and the prints' own details by each call
    side: List[list] = []
    fills: Dict[int, str] = {}
    shade = {"changed": "review", "removed": "bad", "added": "ok"}
    blocks: List[Tuple[Optional[PrintTrain], Optional[PrintTrain], str]] = [
        (a, b, f"{a.label()} {a.days}".strip() + ("" if a.label() == b.label() else f" / {b.label()}"))
        for a, b, _how, n in cmp.pairs if n]
    blocks += [(t, None, f"{t.label()} {t.days} - removed".strip()) for t in cmp.removed]
    blocks += [(None, t, f"{t.label()} {t.days} - added".strip()) for t in cmp.added]
    for a, b, title in blocks:
        fills[len(side)] = "info"
        side.append([title] + [""] * (len(SIDE_COLUMNS) - 1))
        for cells, state in side_by_side(a, b, cmp.passenger_only):
            if state in shade:
                fills[len(side)] = shade[state]
            side.append(cells)
    add_sheet(wb, "Side by Side", SIDE_COLUMNS, side, [26, 8, 12, 12, 14, 12, 8, 18, 8, 16, 30], fills=fills)

    def listing(trains):
        return [[t.headcode, t.uid, t.days, t.first_time, t.origin, t.destination, len(t.calls), t.source, t.page]
                for t in sorted(trains, key=lambda t: (t.first_time, t.headcode))]
    heads = ["Headcode", "UID", "Days", "First time", "From", "To", "Locations", "File", "Page"]
    widths = [11, 10, 10, 11, 26, 26, 11, 30, 7]
    add_sheet(wb, "Trains Added", heads, listing(cmp.added), widths, formats={4: "@"}, center=[4, 7, 9])
    add_sheet(wb, "Trains Removed", heads, listing(cmp.removed), widths, formats={4: "@"}, center=[4, 7, 9])
    add_sheet(wb, "How Trains Were Paired", ["Original train", "Updated train", "Paired by", "Changes", "Original file",
                                  "Updated file"],
              [[a.label(), b.label(), how, n, f"{a.source} p{a.page}", f"{b.source} p{b.page}"]
               for a, b, how, n in cmp.pairs],
              [16, 16, 30, 10, 30, 30], center=[4])
    notes = list(cmp.warnings)
    if cmp.passenger_only:
        notes.insert(0, "Passenger times only: passing times and calls without a public time (timing points, "
                        "working-only stops) were left out of the comparison.")
    if notes:
        add_sheet(wb, "Notes", ["Note"], [[w] for w in notes], [110])
    return wb
