"""Size limits for the files the app reads, kept in one place.

Each limit is far above the largest real planning file seen (noted beside it), so ordinary files are never refused:
the limits are there to stop a damaged or hostile file filling the PC's memory or disk, or a reader running for
hours. A limit can be raised (or lowered) without a new release in 'limits.json' in the app's data folder
(TrainPlanningTools-data), e.g. {"XML_MAX_BYTES": 8589934592}; only the names below are read, and only positive
whole numbers are used."""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

MB = 1024 * 1024
GB = 1024 * MB

DEFAULTS: Dict[str, int] = {
    "XML_MAX_BYTES": 4 * GB,            # an Attune XML (the largest full-timetable export seen is ~400 MB)
    "XML_PART_MAX_BYTES": 512 * MB,     # an XML part inside an Office file (the largest real CWN part is ~100 MB)
    "VPT_MAX_BYTES": 1 * GB,            # an Attune VPT export (a full timetable is ~60 MB)
    "PDF_MAX_BYTES": 500 * MB,          # a PDF: Section 4, TPR, train prints (the largest seen is ~40 MB)
    "PDF_MAX_PAGES": 20000,             # pages in one PDF (a whole Section 4 book is ~1,500)
    "XLS_MAX_BYTES": 512 * MB,          # an older Excel .xls CWN (the 65,536-row format limit keeps real ones small)
    "CSV_MAX_BYTES": 256 * MB,          # a train list exported as CSV (a full timetable's list is ~20 MB)
    "ZIP_PART_LIMIT": 512 * MB,         # one part of an Office file, unpacked (the largest real CWN part ~100 MB)
    "ZIP_TOTAL_LIMIT": 2 * GB,          # a whole Office file, unpacked
    "ZIP_RATIO_LIMIT": 200,             # unpacked / packed size of a part over 50 MB: real workbooks are under ~30
}
FILE_NAME = "limits.json"

_cache: Optional[Dict[str, int]] = None


def _overrides() -> Dict[str, int]:
    try:
        from .branding import settings_dir
        with open(os.path.join(settings_dir(), FILE_NAME), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items()
            if k in DEFAULTS and isinstance(v, int) and not isinstance(v, bool) and v > 0}


def get(name: str) -> int:
    """The limit `name` (one of DEFAULTS), with any override from limits.json (read once)."""
    global _cache
    if _cache is None:
        _cache = {**DEFAULTS, **_overrides()}
    return _cache[name]


def reload():
    """Forget the limits read, so limits.json is read again (tests, or after editing it)."""
    global _cache
    _cache = None


def size_text(n: int) -> str:
    """A size as '2 GB', '1.5 GB', '500 MB' or '3 KB'."""
    if n >= GB:
        return f"{n // GB} GB" if n % GB == 0 else f"{n / GB:.1f} GB"
    return f"{n // MB} MB" if n >= MB else f"{max(1, n // 1024)} KB"


class TooLargeError(OSError):           # an OSError, so every reader reports it as an unreadable file
    pass


def check_size(path: str, name: str, what: str = "file") -> int:
    """The file's size, after checking it is not over the limit `name`; raises TooLargeError if it is."""
    size = os.path.getsize(path)
    limit = get(name)
    if size > limit:
        raise TooLargeError(f"'{os.path.basename(path)}' is {size_text(size)}, larger than any real {what} "
                            f"(the limit is {size_text(limit)}), so it was not opened. If it is genuine, raise "
                            f"{name} in {FILE_NAME} in the app's data folder.")
    return size


def check_pages(count: int, path: str):
    """Refuse a PDF with more pages than PDF_MAX_PAGES."""
    limit = get("PDF_MAX_PAGES")
    if count > limit:
        raise TooLargeError(f"'{os.path.basename(path)}' has {count:,} pages, more than any real planning PDF "
                            f"(the limit is {limit:,}), so it was not read. If it is genuine, raise PDF_MAX_PAGES "
                            f"in {FILE_NAME} in the app's data folder.")


def check_pdf(path: str):
    """A PDF's size, checked before it is opened."""
    check_size(path, "PDF_MAX_BYTES", "PDF")
