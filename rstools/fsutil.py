"""Safe file writing: a file is replaced only once its new version is complete, so a crash, power cut or
full disk part-way through never leaves a damaged output or settings file behind."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager


EXCEL_MAX_PATH = 218         # Excel cannot open a file whose full path is longer than this
MIN_STEM = 30                # names are never cut shorter than this (a deeper folder gets a warning instead)


def long_path(path: str) -> str:
    """The path in Windows' extended form ('\\\\?\\C:\\...') when it is long, so it can be written even
    beyond Windows' usual 260-character limit (deep OneDrive / SharePoint folders). Unchanged elsewhere."""
    if os.name != "nt":
        return path
    full = os.path.abspath(path)
    if len(full) < 240 or full.startswith("\\\\?\\"):
        return path
    if full.startswith("\\\\"):                                # \\server\share\... -> \\?\UNC\server\share\...
        return "\\\\?\\UNC\\" + full[2:]
    return "\\\\?\\" + full


def downloads_dir() -> str:
    """The user's Downloads folder - where Windows really keeps it, even when IT has moved it - or ~/Downloads,
    or the home folder."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                            ("Data4", ctypes.c_ubyte * 8)]
            u = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B")       # FOLDERID_Downloads
            g = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path and os.path.isdir(path) and not is_network_path(path):
                    return path
        except Exception:
            pass
    home = os.path.expanduser("~")
    dl = os.path.join(home, "Downloads")
    return dl if os.path.isdir(dl) else home


def is_network_path(path: str) -> bool:
    """A folder on a network or shared drive: a \\\\server\\share path, or a drive letter mapped to one."""
    if not path:
        return False
    full = path.strip().strip('"')
    if os.name == "nt":
        full = os.path.abspath(full)
    if full.startswith("\\\\") or full.startswith("//"):
        return not full.startswith("\\\\?\\") or full[4:].upper().startswith("UNC\\")
    if os.name == "nt" and len(full) >= 2 and full[1] == ":":
        try:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(full[:2] + "\\") == 4      # DRIVE_REMOTE
        except Exception:
            return False
    return False


NETWORK_REFUSED = ("Outputs are saved on this PC only, not on a network or shared drive. Choose a local folder, "
                   "or leave the box empty to save to your Downloads folder.")


def output_folder(chosen: str = "") -> str:
    """Where an output is saved: the folder chosen if it is on this PC and exists, else Downloads."""
    chosen = (chosen or "").strip().strip('"')
    if chosen and os.path.isdir(chosen) and not is_network_path(chosen):
        return chosen
    return downloads_dir()


def temp_path(path: str) -> str:
    """A short temporary name in the same folder (a long '<name>.tmp' could pass the path limit)."""
    return os.path.join(os.path.dirname(os.path.abspath(path)), f"~tpt{os.getpid() % 100000}{os.urandom(2).hex()}.tmp")


_BAD_NAME = None


def safe_stem(stem: str) -> str:
    """A file name only: characters Windows does not allow (including the folder separators, so a typed
    name such as '..\\x' cannot save outside the chosen folder) become '-'; trailing dots and spaces go."""
    import re
    global _BAD_NAME
    _BAD_NAME = _BAD_NAME or re.compile(r'[<>:"/\\|?*\x00-\x1f]')
    stem = _BAD_NAME.sub("-", stem).strip().rstrip(". ")
    if stem.upper().split(".")[0] in ("CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                                      *(f"LPT{i}" for i in range(1, 10))):
        stem = "_" + stem                     # names Windows reserves for devices
    return stem.strip(".") or "output"


def fit_stem(folder: str, stem: str, tails=(".xlsx",), reserve: int = 4) -> str:
    """`stem` shortened (at a word break where possible) so that folder + stem + each tail stays within
    the length Excel can open, keeping `reserve` characters for a ' (2)' added to make it unique."""
    stem = safe_stem(stem)
    room = EXCEL_MAX_PATH - len(os.path.abspath(folder or ".")) - 1 - max(len(t) for t in tails) - reserve
    if len(stem) <= room:
        return stem
    if room < MIN_STEM:              # the folder itself is too deep: keep the full name (see excel_warning)
        return stem
    cut = stem[:room]
    if " " in cut[MIN_STEM // 2:]:
        cut = cut[:cut.rstrip().rfind(" ")]
    return cut.rstrip(" -.,(") or stem[:room]


def unique_stem(folder: str, stem: str, tails=(".xlsx",)) -> str:
    """A name (shortened to fit, see fit_stem) for which none of folder/name+tail exists yet: existing
    outputs are never overwritten - ' (2)', ' (3)'... is added instead."""
    stem = fit_stem(folder, stem, tails)
    n = 1
    while True:
        name = stem if n == 1 else f"{stem} ({n})"
        if not any(os.path.exists(long_path(os.path.join(folder, name + t))) for t in tails):
            return name
        n += 1


def too_long(path: str) -> bool:
    """True when Excel will not be able to open the file (the folder alone is too deep)."""
    return len(os.path.abspath(path)) > EXCEL_MAX_PATH


def excel_warning(paths) -> str:
    """A warning to show when outputs were saved where Excel cannot open them ('' if all is well)."""
    long = [p for p in paths if p and p.lower().endswith((".xlsx", ".xlsm", ".docx")) and too_long(p)]
    if not long:
        return ""
    folder = os.path.dirname(os.path.abspath(long[0]))
    return (f"The output was saved, but the folder path is {len(folder)} characters long, so Excel or Word may not "
            f"open it (they cannot open files whose full path is over {EXCEL_MAX_PATH} characters). Choose a "
            "shorter 'Save to folder' (e.g. Documents or the desktop), or move the file to a shorter folder.")


@contextmanager
def atomic_path(path: str):
    """Yield a temporary path next to `path`; on success it replaces `path`, on failure it is removed."""
    tmp = long_path(temp_path(path))
    try:
        yield tmp
        os.replace(tmp, long_path(path))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_json(path: str, data) -> bool:
    """Save settings as JSON safely; False (and the old file kept) if the folder cannot be written."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with atomic_path(path) as tmp, open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return True
    except (OSError, TypeError, ValueError):
        return False


def plain_text(ws):
    """Store every formula-looking value on a sheet the app generated as text. openpyxl turns any string
    starting with '=' into a live formula, so text copied from an input file (a destination, a note, a
    cell of an Attune list) could otherwise run as a formula - e.g. a DDE command - when the output is
    opened. The app never writes formulas of its own, so this changes nothing else."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.data_type == "f":
                cell.data_type = "s"


# the Office file limits (rstools.limits, where they can be changed): the defaults, kept here for older imports
from rstools.limits import DEFAULTS as _LIMITS  # noqa: E402

ZIP_PART_LIMIT = _LIMITS["ZIP_PART_LIMIT"]
ZIP_TOTAL_LIMIT = _LIMITS["ZIP_TOTAL_LIMIT"]
ZIP_RATIO_LIMIT = _LIMITS["ZIP_RATIO_LIMIT"]


class UnsafeFileError(OSError):          # an OSError, so every reader reports it as an unreadable file
    pass


def check_zip(z, name: str = ""):
    """Refuse an Office file (a zip) that would unpack to far more than any real one - a 'zip bomb'
    that could fill the memory or disk of the PC. Checks the sizes recorded in the zip, before
    anything is unpacked."""
    from rstools import limits
    part, whole, most = limits.get("ZIP_PART_LIMIT"), limits.get("ZIP_TOTAL_LIMIT"), limits.get("ZIP_RATIO_LIMIT")
    infos = [z.getinfo(name)] if name else z.infolist()
    total = 0
    for info in infos:
        total += info.file_size
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size > part or (info.file_size > 50 * 1024 * 1024 and ratio > most):
            raise UnsafeFileError(f"'{os.path.basename(str(z.filename))}' unpacks to an unrealistic size "
                                  f"({info.file_size // (1024 * 1024)} MB in one part), so it was not opened. It "
                                  "may be damaged or not a genuine Office file.")
    if total > whole:
        raise UnsafeFileError(f"'{os.path.basename(str(z.filename))}' unpacks to over {limits.size_text(whole)}, so "
                              "it was not opened.")


def zip_read(z, name: str) -> bytes:
    """z.read(name) after checking the part's unpacked size (see check_zip)."""
    check_zip(z, name)
    return z.read(name)


def check_office_file(path: str):
    """check_zip for a file on disk, if it is a zip (xlsx, xlsm, docx); other files are left alone."""
    import zipfile
    try:
        if not zipfile.is_zipfile(path):
            return
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return                               # unreadable: the reader itself reports it
    with z:
        check_zip(z)                         # UnsafeFileError goes to the caller


def clean_cell(value):
    """A value safe to put in a workbook cell: strings lose the control characters Excel files cannot
    hold (openpyxl would refuse the whole file); everything else is returned unchanged."""
    if isinstance(value, str):
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


_SHEET_BAD = str.maketrans({"/": "-", "\\": "-", "?": "", "*": "", "[": "(", "]": ")", ":": "."})


def sheet_title(name: str, taken=None) -> str:
    """A worksheet name Excel accepts: no \\ / ? * [ ] :, no leading or trailing apostrophe, 31 characters at most,
    and different (ignoring case) from every name in `taken` (a ' (2)' is added where needed)."""
    t = "".join(ch for ch in str(name or "") if ch >= " " and ch != "\x7f").translate(_SHEET_BAD)
    t = " ".join(t.split()).strip("' ")[:31].strip("' ") or "Sheet"
    used = {x.lower() for x in (taken or ())}
    out, n = t, 1
    while out.lower() in used:
        n += 1
        tail = f" ({n})"
        out = t[:31 - len(tail)].rstrip("' ") + tail
    return out
