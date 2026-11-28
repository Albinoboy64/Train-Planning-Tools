"""Unexpected errors: the details are kept in error.log (in the app's data folder) for support, and the user
sees a short message. Files that are open in another program, read-only folders and full disks get a plain
explanation instead, as they are not faults in the app.

Privacy: the log holds tracebacks only, never the contents of a timetable XML, workbook or PDF - a line longer than
LINE_LIMIT (which would be text from a file in an error message) is cut short when it is written. Before the log is
shared (Help > Error log...), redact() hides file paths, the Windows user and computer names, email addresses and
text quoted from input files; export() saves that redacted copy, never overwriting a file."""
from __future__ import annotations

import datetime
import errno
import os
import re
import socket
import traceback
from typing import List

LOG_NAME = "error.log"
LOG_LIMIT = 1024 * 1024              # keep the log small: past this only the newest half is kept
LINE_LIMIT = 500                    # characters kept of one line: longer lines are file contents, not a traceback


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
            fh.write(f"\n===== {datetime.datetime.now():%d/%m/%Y %H:%M:%S}  v{__version__} =====\n"
                     f"{shorten_lines(text)}\n")
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
    if isinstance(exc, FileExistsError):
        where = f"\n\n{exc.filename}" if exc.filename else ""
        return ("A file with the output's name appeared in the folder while it was being saved, so nothing was "
                "written over. Run it again to save under a new name." + where)
    if isinstance(exc, FileNotFoundError) and exc.filename:
        return ("The output could not be saved: its folder is missing or the path is too long for Windows. Choose a "
                f"shorter output name or a folder nearer the top of the drive.\n\n{exc.filename}")
    if isinstance(exc, ValueError) and "too large" in str(exc).lower():
        return f"The output is too large to save as one Excel file ({exc}). Choose fewer days or tabs and try again."
    return ""


def workbook_problem(path: str, exc: BaseException) -> str:
    """A plain message for an Excel input that could not be opened (the details go to the log)."""
    import os
    name = os.path.basename(path)
    if isinstance(exc, PermissionError):
        return f"'{name}' could not be opened - it may be open in Excel. Close it there and try again."
    if path.lower().endswith(".xls"):
        return (f"'{name}' is an older Excel 97-2003 (.xls) file, which this task cannot read. Open it in Excel, "
                "save it as an Excel Workbook (.xlsx) and choose that file.")
    from rstools.fsutil import UnsafeFileError
    from rstools.limits import TooLargeError
    if isinstance(exc, (UnsafeFileError, TooLargeError)):
        return str(exc)
    write(f"Reading {path} failed:\n{''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}")
    return (f"'{name}' could not be read as an Excel workbook. It may be damaged, password-protected or not an "
            f"Excel file: open it in Excel, save it again and retry. (Details: {exc})")


def describe(exc: BaseException, tb: str = "") -> str:
    """The message to show for an error no reader explained: a file problem in plain words, otherwise
    'Unexpected error' with the log's location (or the details themselves if the log cannot be written)."""
    plain = file_problem(exc)
    if plain:
        return plain
    tb = tb or "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    where = write(tb)
    return f"Unexpected error: {exc}" + (f"\n\nDetails were saved to:\n{where}" if where else f"\n\n{tb}")


def shorten_lines(text: str, limit: int = LINE_LIMIT) -> str:
    """Each line cut to `limit` characters: a traceback's lines are short; a long one is text quoted from a file
    (a whole XML element, a cell, a page) and is not kept."""
    out = []
    for line in text.splitlines():
        if len(line) > limit:
            line = line[:limit] + f" ...({len(line) - limit:,} characters left out)"
        out.append(line)
    return "\n".join(out)


def read() -> str:
    """The whole log, or '' when there is none."""
    try:
        with open(log_path(), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def clear() -> bool:
    """Empty the log (True when done or there was none)."""
    try:
        os.remove(log_path())
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


_WIN_FILE = re.compile(r"(?:\\\\[^\\\s'\"<>|]+|\b[A-Za-z]:)(?:[\\/][^\\/:*?\"<>|\r\n']+?)*?[\\/]"
                       r"[^\\/:*?\"<>|\r\n']+?\.[A-Za-z0-9]{1,5}(?=$|[\s'\",;:.)\]])")   # a file: may have spaces
_WIN_PATH = re.compile(r"(?:\\\\[^\\\s'\"<>|]+\\[^\s'\"<>|]*|\b[A-Za-z]:[\\/][^\s'\"<>|]*)")
_POSIX_PATH = re.compile(r"(?<![\w.:/])/(?:[\w.\-~]+/)+[\w.\-~]*")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_QUOTED = re.compile(r"'([^'\n]{4,})'|\"([^\"\n]{4,})\"")
_FILE_LINE = re.compile(r'^\s*File "')


def _short_path(m: "re.Match") -> str:
    """'<path>' plus the file name (kept: it says which part of the app failed), '<folder>' for a folder."""
    text = m.group(0).rstrip(".,;:)")
    tail = m.group(0)[len(text):]
    name = re.split(r"[\\/]", text.rstrip("\\/"))[-1]
    sep = "\\" if "\\" in text else "/"
    return (f"<path>{sep}{name}" if "." in name and not text.endswith(("\\", "/")) else "<folder>") + tail


def _hide_quoted(m: "re.Match") -> str:
    inner = m.group(1) if m.group(1) is not None else m.group(2)
    if inner.startswith(("<path>", "<folder>", "<user>", "<email>")):
        return m.group(0)                                  # already hidden: the redacted path is kept
    return "'<text>'" if m.group(1) is not None else '"<text>"'


def _who() -> List[str]:
    """The user and computer names to hide (from the environment), longest first; very short names are left, as
    hiding them would garble the log."""
    names = {os.environ.get(k, "") for k in ("USERNAME", "USER", "LOGNAME", "COMPUTERNAME", "USERDOMAIN")}
    try:
        names.add(socket.gethostname())
    except OSError:
        pass
    home = os.path.basename(os.path.expanduser("~").rstrip("\\/"))
    names.add(home)
    return sorted((n for n in names if n and len(n) >= 3), key=len, reverse=True)


def redact(text: str, paths: bool = True, user: bool = True, content: bool = True) -> str:
    """The log with personal and file details hidden, for sharing.
    paths: absolute file paths become '<path>\\name.ext' (the file name is kept) or '<folder>';
    user: the Windows user and computer names and email addresses become '<user>' / '<email>';
    content: text quoted in error messages (a value from a file) becomes '<text>'. The app's own source lines in a
    traceback (the line after 'File "..."') are kept as they are."""
    out = []
    after_file = False
    names = _who() if user else []
    for line in text.splitlines():
        is_file = bool(_FILE_LINE.match(line))
        is_source = after_file and line.startswith("    ") and not is_file
        if paths:
            if re.search(r"[A-Za-z]:\\\\", line):         # a path as Python shows it, with doubled backslashes
                line = line.replace("\\\\", "\\")
            line = _WIN_FILE.sub(_short_path, line)
            line = _WIN_PATH.sub(_short_path, line)
            line = _POSIX_PATH.sub(_short_path, line)
        if user:
            line = _EMAIL.sub("<email>", line)
            for n in names:
                line = re.sub(rf"(?i)(?<![\w]){re.escape(n)}(?![\w])", "<user>", line)
        if content and not is_file and not is_source:
            line = _QUOTED.sub(_hide_quoted, line)
        out.append(line)
        after_file = is_file
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def export(text: str, folder: str = "") -> str:
    """Save `text` (the redacted log) as 'error log YYYY-MM-DD.txt' in `folder` (this PC only; default
    Downloads), next to and never over an existing file. Returns the path."""
    from .fsutil import atomic_path, is_network_path, output_folder, unique_stem
    if folder and is_network_path(folder):
        raise OSError("The error log is saved on this PC only: choose a local folder.")
    folder = output_folder(folder)
    stem = unique_stem(folder, f"error log {datetime.date.today():%Y-%m-%d}", (".txt",))
    path = os.path.join(folder, stem + ".txt")
    with atomic_path(path) as tmp:
        with open(tmp, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(text)
    return path
