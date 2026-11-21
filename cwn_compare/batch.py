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

_NOISE = re.compile(r"\b(proof|draft|issue|iss|version|ver|rev|v|p)\s*\.?\s*\d+[a-z]?\b|\b(final|copy|new|old|"
                    r"updated|original|amended|cwn)\b|\(\d+\)|\b\d{1,2}[-./]\d{1,2}[-./]\d{2,4}\b", re.I)


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _key(path: str) -> str:
    """'BTN CWN Proof 2 (1).xlsx' -> 'btn' : the part of the name that says which CWN it is."""
    text = _NOISE.sub(" ", _NOISE.sub(" ", _stem(path)).replace("_", " ").replace("-", " "))
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
    need = max((60 * os.path.getsize(u) + 20 * os.path.getsize(o) for o, u in pairs), default=0) / 1e6
    free = available_memory_mb()
    by_memory = int(0.7 * free // max(need, 300)) if free else cores
    return max(1, min(cores, len(pairs), by_memory))


def _one(opts: Options) -> dict:
    from .engine import run
    return run(opts)


def run_batch(pairs: List[Tuple[str, str]], base: Options,
              done: Callable[[int, int, str, str, Optional[dict], str], None] = lambda *a: None) -> List[dict]:
    """Compare every pair; done(index, total, original, updated, result or None, error) after each one."""
    jobs = [dataclasses.replace(base, original=o, updated=u, output_name="", days=[]) for o, u in pairs]
    results: List[dict] = []
    workers = workers_for(pairs)
    if workers > 1:
        try:
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
        except Exception:
            pool = None
        if pool is not None:
            with pool:
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
