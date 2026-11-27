"""Process pools that can be stopped at once.

A `with ProcessPoolExecutor()` block waits for every queued job when it ends, even when the run was stopped (Stop /
Esc) or the window is closing, so the helpers would carry on comparing and saving. `stop_now` cancels the queued
jobs and ends the helper processes; a helper ended part-way leaves only its own temporary file (outputs are saved
to a temporary file and renamed when complete), never a half-written output. Pools in use are kept in a list so
the window can stop them all when it closes (`stop_all`)."""
from __future__ import annotations

import threading
import weakref
from contextlib import contextmanager

_LIVE: "weakref.WeakSet" = weakref.WeakSet()
_LOCK = threading.Lock()


def stop_now(pool) -> None:
    """Cancel the pool's queued jobs and end its helper processes, without waiting for them."""
    procs = list((getattr(pool, "_processes", None) or {}).values())
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass


@contextmanager
def stoppable(pool):
    """Use a pool like `with pool:`, but a stop (Cancelled), an error or the window closing ends it at once;
    finishing normally waits for the jobs as usual."""
    with _LOCK:
        _LIVE.add(pool)
    try:
        yield pool
    except BaseException:
        stop_now(pool)
        raise
    else:
        pool.shutdown(wait=True)
    finally:
        with _LOCK:
            _LIVE.discard(pool)


def stop_all() -> None:
    """End every pool still running (the window is closing)."""
    with _LOCK:
        pools = list(_LIVE)
    for pool in pools:
        stop_now(pool)
