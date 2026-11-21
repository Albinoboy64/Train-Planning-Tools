"""Unexpected errors: the details are kept in error.log (in the app's data folder) for support, and the user
sees a short message. Files that are open in another program, read-only folders and full disks get a plain
explanation instead, as they are not faults in the app."""
from __future__ import annotations

import datetime
import errno
import os
import traceback

LOG_NAME = "error.log"
LOG_LIMIT = 1024 * 1024              # keep the log small: past this only the newest half is kept


def log_path() -> str:
    from .branding import settings_dir
    return os.path.join(settings_dir(), LOG_NAME)


def write(text: str) -> str:
    """Add an entry to the log; returns its path ('' if it could not be written)."""
    try:
        from cwn_compare import __version__
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > LOG_LIMIT:
            with open(path, "rb") as fh:
                fh.seek(-LOG_LIMIT // 2, os.SEEK_END)
                tail = fh.read()
            with open(path, "wb") as fh:
                fh.write(b"(older entries removed)\n" + tail[tail.find(b"\n=====") + 1:])
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.datetime.now():%d/%m/%Y %H:%M:%S}  v{__version__} =====\n{text}\n")
        return path
    except OSError:
        return ""


def file_problem(exc: BaseException) -> str:
    """A plain message for a file that could not be opened or saved, or '' for any other error."""
    if isinstance(exc, PermissionError):
        name = exc.filename or ""
        return ("A file could not be opened or saved. Close it in Excel or Word if it is open, check the folder "
                "can be written to, then try again." + (f"\n\n{name}" if name else ""))
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "The disk is full, so the output could not be saved. Free some space, then try again."
    return ""


def describe(exc: BaseException, tb: str = "") -> str:
    """The message to show for an error no reader explained: a file problem in plain words, otherwise
    'Unexpected error' with the log's location (or the details themselves if the log cannot be written)."""
    plain = file_problem(exc)
    if plain:
        return plain
    tb = tb or "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    where = write(tb)
    return f"Unexpected error: {exc}" + (f"\n\nDetails were saved to:\n{where}" if where else f"\n\n{tb}")
