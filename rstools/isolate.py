"""Run native-code readers (PDFium) in a helper process, so a damaged or hostile file that makes the native code
crash ends the helper, never the app. Inside a helper process already (several files read at once) the reader
runs there directly."""
from __future__ import annotations

import multiprocessing
from typing import Callable

TIMEOUT = 900                       # seconds: a whole Section 4 book takes well under a minute


class ReaderCrashed(OSError):       # an OSError, so callers report it as an unreadable file
    pass


def run(fn: Callable, *args, name: str = "the file"):
    """fn(*args) in a helper process (fn must be a module-level function and its result picklable). The reader's
    own errors are raised here as they are; a crash or hang of the helper becomes ReaderCrashed. If no helper
    can be started at all, fn runs here."""
    if multiprocessing.parent_process() is not None:
        return fn(*args)
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    try:
        pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
    except Exception:
        return fn(*args)
    ok = False
    try:
        result = pool.submit(fn, *args).result(timeout=TIMEOUT)
        ok = True
        return result
    except BrokenProcessPool:
        raise ReaderCrashed(f"{name} made the PDF reader stop unexpectedly, so it could not be read. It may be "
                            "damaged: try saving or printing it to a new PDF.")
    except TimeoutError:
        raise ReaderCrashed(f"{name} took too long to read, so it was stopped.")
    finally:
        if not ok:
            for proc in list(getattr(pool, "_processes", {}).values()):
                try:
                    proc.kill()
                except Exception:
                    pass
        pool.shutdown(wait=ok, cancel_futures=True)
