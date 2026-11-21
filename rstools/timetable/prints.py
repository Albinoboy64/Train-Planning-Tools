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
from dataclasses import dataclass, field
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
    raise PrintError(f"'{os.path.basename(path)}': train prints must be PDF (.pdf) or Word (.docx) files.")


def from_attune(t) -> "PrintTrain":
    """An Attune Single Train Report train, with every column kept under its own name."""
    from .attune_print import TIME_COLS
    calls = []
    for r in t.rows:
        times = {k: v for k, v in r.values.items() if k in TIME_COLS or k == "pass"}
        rest = {k: v for k, v in r.values.items() if k not in times}
        calls.append(Call(r.name, _loc_key(r.name), times, " ".join(rest.values()), rest))
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


def _pair(orig: List[PrintTrain], upd: List[PrintTrain]):
    """One-to-one pairs: headcode + UID, then headcode + days + first time, then headcode + first time,
    then a headcode that appears once on each side."""
    pairs, left, right = [], list(orig), list(upd)
    rules = (("Headcode, UID and days", lambda t: (t.headcode, t.uid, t.days) if t.uid else None),
             ("Train ID and days", lambda t: (t.ident, t.days) if t.ident else None),
             ("Headcode, days and first time", lambda t: (t.headcode, t.days, t.first_time)),
             ("Headcode and first time", lambda t: (t.headcode, t.first_time)),
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


def _compare_pair(a: PrintTrain, b: PrintTrain) -> List[PrintChange]:
    out: List[PrintChange] = []
    label = a.label() if a.label() == b.label() else f"{a.label()} / {b.label()}"
    days = a.days if a.days == b.days else f"{a.days} / {b.days}".strip(" /")
    for key in dict.fromkeys(list(a.info) + list(b.info)):
        va, vb = a.info.get(key, ""), b.info.get(key, "")
        if va != vb:
            out.append(PrintChange(label, days, "(train details)", f"{key} changed", va or "-", vb or "-"))
    ha, hb = [h for h in a.heading if h not in b.heading], [h for h in b.heading if h not in a.heading]
    if ha or hb:
        out.append(PrintChange(label, days, "(train details)", "Train details changed", "\n".join(ha) or "-",
                               "\n".join(hb) or "-"))
    sm = difflib.SequenceMatcher(None, [c.key for c in a.calls], [c.key for c in b.calls], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for ca, cb in zip(a.calls[i1:i2], b.calls[j1:j2]):
                for role in dict.fromkeys(list(ca.times) + list(cb.times)):
                    ta, tb = ca.times.get(role, ""), cb.times.get(role, "")
                    if ta != tb:
                        name = _TIME_NAMES.get(role.rstrip("0123456789"), "Time")
                        what = (f"{name} time changed" if ta and tb else f"{name} time added" if tb
                                else f"{name} time removed")
                        out.append(PrintChange(label, days, ca.loc, what, ta or "-", tb or "-"))
                if ca.fields or cb.fields:
                    for key in dict.fromkeys(list(ca.fields) + list(cb.fields)):
                        fa, fb = ca.fields.get(key, ""), cb.fields.get(key, "")
                        if fa != fb:
                            out.append(PrintChange(label, days, ca.loc, f"{_FIELD_NAMES.get(key, key)} changed",
                                                   fa or "-", fb or "-"))
                elif ca.details != cb.details:
                    out.append(PrintChange(label, days, ca.loc, "Call details changed (platform, line, activity...)",
                                           ca.details or "-", cb.details or "-"))
            continue
        for ca in a.calls[i1:i2]:
            out.append(PrintChange(label, days, ca.loc, "Location removed", _fmt_times(ca), "-"))
        for cb in b.calls[j1:j2]:
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
    rows = [("Days run", a.days if a else "", b.days if b else ""),
            ("Train", (a.ident or a.headcode) if a else "", (b.ident or b.headcode) if b else ""),
            ("UID", a.uid if a else "", b.uid if b else "")]
    keys = [k for k in INFO_ORDER if k in x.info or k in y.info]
    keys += [k for k in dict.fromkeys(list(x.info) + list(y.info)) if k not in keys]
    seen = set()
    for k in keys:
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
    return [r for r in rows if r[1] or r[2]]


def _role_keys(ca: Optional[Call], cb: Optional[Call]) -> List[str]:
    have = set(ca.times if ca else ()) | set(cb.times if cb else ())
    keys = [k for k in _ROLE_ORDER if k in have]
    keys += sorted(k for k in have if k not in keys and not k.startswith("pub_"))
    return keys or [""]


def _location_rows(ca: Optional[Call], cb: Optional[Call]) -> List[Tuple[List[str], str]]:
    """The rows of one location: one per time (Arr / Dep / Pass), details on the first."""
    out = []
    da, db = _call_details(ca), _call_details(cb)
    names = ("Platform", "Line", "Activity", "Dwell", "Allowances")
    for n, role in enumerate(_role_keys(ca, cb)):
        ta = ca.times.get(role, "") if ca and role else ""
        tb = cb.times.get(role, "") if cb and role else ""
        pub = _PUBLIC_OF.get(role, "")
        pa = ca.times.get(pub, "") if ca and pub else ""
        pb = cb.times.get(pub, "") if cb and pub else ""
        details = [_both(x, y) for x, y in zip(da, db)] if n == 0 else [""] * 5
        if ca is None or cb is None:
            state, result = ("added", "Location added") if ca is None else ("removed", "Location removed")
        else:
            diffs = []
            if ta != tb:
                diffs.append("Time added" if not ta else "Time removed" if not tb else "Time changed")
            if pa != pb:
                diffs.append("Public time changed")
            if n == 0:
                diffs += [f"{name} changed" for name, x, y in zip(names, da, db) if x != y]
            state, result = ("changed", ", ".join(diffs)) if diffs else ("same", "Match")
        loc = cast(Call, ca or cb).loc if n == 0 else ""
        out.append(([loc, _ROLE_SHOWN.get(role, role), ta, tb, _both(pa, pb)] + details + [result], state))
    return out


def side_by_side(a: Optional[PrintTrain], b: Optional[PrintTrain]) -> List[Tuple[List[str], str]]:
    """A train from each set of prints laid out like the timetable comparison - one row per location
    and time, both prints' times side by side - with the print's own details (public times, platform,
    line, activity codes, dwell, allowances) and the train's details (days run, IDs, dates...) on top.
    Returns [(cells, state)], state 'same' / 'changed' / 'added' / 'removed' / 'muted' (train details)."""
    rows: List[Tuple[List[str], str]] = []
    for name, va, vb in train_details(a, b):
        state = "muted" if va == vb or a is None or b is None else "changed"
        rows.append(([name, "", va, vb, "", "", "", "", "", "",
                      "" if state == "muted" else "Changed"], state))
    calls_a, calls_b = (a.calls if a else []), (b.calls if b else [])
    sm = difflib.SequenceMatcher(None, [c.key for c in calls_a], [c.key for c in calls_b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for ca, cb in zip(calls_a[i1:i2], calls_b[j1:j2]):
                rows += _location_rows(ca, cb)
            continue
        for ca in calls_a[i1:i2]:
            rows += _location_rows(ca, None)
        for cb in calls_b[j1:j2]:
            rows += _location_rows(None, cb)
    return rows


def compare_prints(original: List[PrintTrain], updated: List[PrintTrain], warnings: Iterable[str] = ()):
    pairs, added, removed = _pair(original, updated)
    pairs.sort(key=lambda p: (p[0].source, p[0].page, p[0].first_time, p[0].headcode))
    changes, counted = [], []
    for a, b, how in pairs:
        found = _compare_pair(a, b)
        changes.extend(found)
        counted.append((a, b, how, len(found)))
    return PrintComparison(original, updated, counted, added, removed, changes, list(warnings))


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
        for cells, state in side_by_side(a, b):
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
    if cmp.warnings:
        add_sheet(wb, "Notes", ["Note"], [[w] for w in cmp.warnings], [110])
    return wb
