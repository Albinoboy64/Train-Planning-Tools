"""Files already read, remembered while they are unchanged (same time stamp and size), so the same TRENT print,
Attune XML or CWN is not read again when the app lists its contents, re-compares in the Live View, or makes
several outputs from it. One store for the whole app, safe to use from the window's worker threads, keeping the
most recently used results only (a parsed Attune XML can be large)."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Callable, Optional, Tuple

SIZE = 8                                   # results kept

_LOCK = threading.RLock()
_STORE: "OrderedDict[tuple, tuple]" = OrderedDict()      # key -> (stamp, result)


def key_of(reader, path: str) -> Tuple[Optional[tuple], Optional[tuple]]:
    """(key, stamp) for reader(path); (None, None) if the file cannot be looked at (it is then read every time)."""
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    return ((getattr(reader, "__module__", ""), getattr(reader, "__qualname__", repr(reader)), os.path.abspath(path)),
            (st.st_mtime_ns, st.st_size))


def get(key: Optional[tuple], stamp: Optional[tuple]):
    """The result remembered for `key` if the file is unchanged, else None."""
    if key is None:
        return None
    with _LOCK:
        hit = _STORE.get(key)
        if hit is None or hit[0] != stamp:
            return None
        _STORE.move_to_end(key)
        return hit[1]


def put(key: Optional[tuple], stamp: Optional[tuple], result) -> None:
    if key is None:
        return
    with _LOCK:
        _STORE.pop(key, None)
        _STORE[key] = (stamp, result)
        while len(_STORE) > SIZE:
            _STORE.popitem(last=False)


def remember(reader: Callable, path: str):
    """reader(path), or the result remembered from the last time the unchanged file was read. The file is read
    outside the lock, so other threads are not held up by a long read."""
    key, stamp = key_of(reader, path)
    hit = get(key, stamp)
    if hit is None:
        hit = reader(path)
        put(key, stamp, hit)
    return hit


def clear() -> None:
    with _LOCK:
        _STORE.clear()
