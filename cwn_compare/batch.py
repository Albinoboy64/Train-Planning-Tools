"""Compare two folders of CWNs in one go: each updated CWN is paired with its original by file name and
every pair is compared on its own CPU core (as many at once as the PC's cores and memory allow)."""
from __future__ import annotations

import dataclasses
import difflib
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from typing import Callable, Dict, List, Optional, Tuple

from .loader import SUPPORTED_EXT
from .options import Options

# Underscores and hyphens are read as spaces first: they are word characters to a regular expression, so
# 'BTN_CWN_v1.2' or '..._14-12-2026' would otherwise keep their version or date and never pair. Digits joined by
# an underscore ('V1_2', '14_12_2026') are read as one number ('1.2', '14.12.2026').
_DIGIT_JOIN = re.compile(r"(?<=\d)_(?=\d)")
_SEPARATORS = re.compile(r"[_\-]+")
_NOISE = re.compile(
    r"\b(?:version|ver|v)\s*\.?\s*\d+(?:\.\d+)*[a-z]?\b"                  # v2, v1.2, V1_2, Version 3
    r"|\b(?:proof|draft|issue|iss|rev|p|d)\s*\.?\s*\d+(?:\.\d+)*[a-z]?\b"  # Proof 2, Issue 2a, rev2, P2, D12
    r"|\b(?:supplement|supp)\s*(?:no\.?)?\s*\d+\b"                         # Supp 1, Supplement No 2
    r"|\b(?:final|copy|new|old|updated|original|amended|cwn)\b"
    r"|\(\d+\)",                                                         # Windows' ' (1)' copies
    re.I)
_DATE = re.compile(r"\b(\d{1,4})[./ ](\d{1,2})[./ ](\d{2,4})\b|\b(\d{6}|\d{8})\b")


def _real_date(day: int, month: int, year: str) -> bool:
    return 1 <= day <= 31 and 1 <= month <= 12 and (len(year) == 2 or year[:2] in ("19", "20"))


def _is_date(m: "re.Match") -> bool:
    """Only a real date is left out (14.12.2026, 26 09 18, 260918, 20260918) - not a unit number such as
    377001 or a run of numbers that is part of the name."""
    if m.group(4):
        t = m.group(4)
        if len(t) == 6:     # yymmdd or ddmmyy
            return _real_date(int(t[4:]), int(t[2:4]), t[:2]) or _real_date(int(t[:2]), int(t[2:4]), t[4:])
        return _real_date(int(t[6:]), int(t[4:6]), t[:4]) or _real_date(int(t[:2]), int(t[2:4]), t[4:])
    a, b, c = m.group(1), m.group(2), m.group(3)
    if len(a) == 4:         # yyyy mm dd
        return _real_date(int(c), int(b), a)
    return _real_date(int(a), int(b), c) or (len(a) == 2 and _real_date(int(c), int(b), a))


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _key(path: str) -> str:
    """'BTN CWN Proof 2 (1).xlsx' -> 'btn' : the part of the name that says which CWN it is."""
    text = _SEPARATORS.sub(" ", _DIGIT_JOIN.sub(".", _stem(path)))
    text = _DATE.sub(lambda m: " " if _is_date(m) else m.group(0), text)
    text = _NOISE.sub(" ", text)
    return " ".join(text.split()).casefold()


def cwn_files(folder: str) -> List[str]:
    """CWN workbooks in a folder (not this app's change reports, not Excel's temporary '~$' files)."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if os.path.splitext(n)[1].lower() in SUPPORTED_EXT and not n.startswith("~$")
            and "change report" not in n.lower() and os.path.isfile(os.path.join(folder, n))]


def pair_files(orig_dir: str, upd_dir: str) -> Tuple[List[Tuple[str, str]], List[str], List[str]]:
    """(pairs [(original, updated)], originals left over, updated left over). Same file name first, then
    the same name once proof numbers, dates and words such as 'final' are ignored, then the clearly most
    similar name (each file is used once)."""
    origs, upds = cwn_files(orig_dir), cwn_files(upd_dir)
    pairs: List[Tuple[str, str]] = []
    left, right = list(origs), list(upds)
    for match in (lambda p: _stem(p).casefold(), _key):
        index: Dict[str, List[str]] = {}
        for o in left:
            index.setdefault(match(o), []).append(o)
        for u in list(right):
            cands = index.get(match(u))
            if cands and len(cands) == 1 and match(u):
                o = cands.pop()
                pairs.append((o, u))
                left.remove(o)
                right.remove(u)
    for u in list(right):                      # most similar name, only when clearly the best for both
        scores = sorted(((difflib.SequenceMatcher(None, _key(o), _key(u)).ratio(), o) for o in left), reverse=True)
        if not scores or scores[0][0] < 0.75 or (len(scores) > 1 and scores[0][0] - scores[1][0] < 0.1):
            continue
        o = scores[0][1]
        back = max((difflib.SequenceMatcher(None, _key(o), _key(x)).ratio(), x) for x in right)[1]
        if back == u:
            pairs.append((o, u))
            left.remove(o)
            right.remove(u)
    pairs.sort(key=lambda p: _stem(p[1]).casefold())
    return pairs, left, right


def available_memory_mb() -> Optional[int]:
    """Free memory in MB (None if it cannot be told)."""
    try:
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = Status()
            st.dwLength = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullAvailPhys // (1024 * 1024))
            return None
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return None
    return None


def workers_for(pairs: List[Tuple[str, str]]) -> int:
    """How many pairs to compare at once: one per CPU core (one core left for the window), and only as
    many as fit in free memory (a CWN being written needs roughly 60x its file size)."""
    cores = max(1, (os.cpu_count() or 1) - 1)
    def size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:                       # gone since it was listed: its own run reports it
            return 0
    need = max((60 * size(u) + 20 * size(o) for o, u in pairs), default=0) / 1e6
    free = available_memory_mb()
    by_memory = int(0.7 * free // max(need, 300)) if free else cores
    return max(1, min(cores, len(pairs), by_memory))


def _distinct_names(pairs: List[Tuple[str, str]], folder: str, report_format: str = "xlsx") -> List[str]:
    """Each pair's output name, chosen here before any is compared: pairs compared at the same time must never
    choose the same file name, nor one already in the folder (' (2)', ' (3)'... as for a single comparison)."""
    from rstools.fsutil import unique_stem
    from .engine import _safe
    from .options import default_name
    from rstools.docexport import ext_for
    tails = (".xlsx", " - Change Report" + ext_for(report_format))
    out: List[str] = []
    for o, u in pairs:
        out.append(unique_stem(folder, _safe(default_name(o, u)), tails, taken=out))
    return out


def _one(opts: Options) -> dict:
    from .engine import run
    return run(opts)


def run_batch(pairs: List[Tuple[str, str]], base: Options,
              done: Callable[[int, int, str, str, Optional[dict], str], None] = lambda *a: None) -> List[dict]:
    """Compare every pair; done(index, total, original, updated, result or None, error) after each one."""
    from rstools.fsutil import output_folder
    folder = output_folder(base.output_dir)
    if pairs and folder != base.output_dir:   # no folder chosen: a folder in Downloads named after the updated CWNs'
        folder = os.path.join(folder, os.path.basename(os.path.dirname(os.path.abspath(pairs[0][1]))) or "CWNs")
        os.makedirs(folder, exist_ok=True)
    jobs = [dataclasses.replace(base, original=o, updated=u, output_name=name, days=[], output_dir=folder)
            for (o, u), name in zip(pairs, _distinct_names(pairs, folder, base.report_format))]
    results: List[dict] = []
    workers = workers_for(pairs)
    if workers > 1:
        try:
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
        except Exception:
            pool = None
        if pool is not None:
            from rstools.pools import stoppable
            with stoppable(pool):                 # Stop (raised by done()) ends the helpers at once
                futures = {pool.submit(_one, job): i for i, job in enumerate(jobs)}
                for n, fut in enumerate(as_completed(futures), start=1):
                    i = futures[fut]
                    try:
                        res, err = fut.result(), ""
                    except Exception as exc:          # one bad file does not stop the others
                        res, err = None, str(exc) or type(exc).__name__
                    results.append(res or {})
                    done(n, len(jobs), pairs[i][0], pairs[i][1], res, err)
            return results
    for n, job in enumerate(jobs, start=1):
        try:
            res, err = _one(job), ""
        except Exception as exc:
            res, err = None, str(exc) or type(exc).__name__
        results.append(res or {})
        done(n, len(jobs), job.original, job.updated, res, err)
    return results
