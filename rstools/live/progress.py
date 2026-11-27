"""Live View checking progress: which trains have been ticked as confirmed, saved and loaded.

A confirmation is kept against the train's stable key together with a fingerprint of everything shown for it. If
a refresh changes what is shown (a file was corrected and saved), the tick is taken off and the train is marked
'changed since confirmed', so nothing confirmed can silently go out of date.

Progress is saved automatically (one file per comparison, in the app's data folder) and can also be saved to and
loaded from a file of the user's choosing, e.g. to hand a half-checked comparison to a colleague.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Dict, Iterable, List, Optional, Set, Tuple

VERSION = 1


def fingerprint(item) -> str:
    """A short fingerprint of everything the Live View shows for an item."""
    return hashlib.sha1(repr(item.signature()).encode("utf-8", "replace")).hexdigest()[:16]


def comparison_id(mode: str, files: Dict[str, List[str]]) -> str:
    """The same comparison (mode and files, in any letter case) always gets the same id."""
    parts = [mode] + [f"{k}=" + "|".join(os.path.normcase(os.path.abspath(p)) for p in files[k])
                      for k in sorted(files)]
    return hashlib.sha1("\n".join(parts).encode("utf-8", "replace")).hexdigest()[:20]


def autosave_path(mode: str, files: Dict[str, List[str]]) -> str:
    from rstools.branding import settings_dir
    return os.path.join(settings_dir(), "live_progress", comparison_id(mode, files) + ".json")


def reconcile(confirmed: Dict[str, str], items: Iterable) -> Tuple[Dict[str, str], Set[str]]:
    """(confirmations still valid, keys whose item changed since it was confirmed). Items no longer in the
    comparison keep their confirmation (they may come back when a day or filter is changed)."""
    now = {it.key: fingerprint(it) for it in items}
    kept, changed = {}, set()
    for key, fp in confirmed.items():
        if key in now and now[key] != fp:
            changed.add(key)
        else:
            kept[key] = fp
    return kept, changed


def save(path: str, mode: str, files: Dict[str, List[str]], confirmed: Dict[str, str], state: Optional[dict] = None,
         changed: Iterable[str] = ()) -> bool:
    """Write the progress file (atomically; the old file is kept if it cannot be written)."""
    from rstools.fsutil import write_json
    data = {"app": "Train Planning Tools", "kind": "live_progress", "version": VERSION,
            "saved": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": mode, "files": files,
            "state": state or {}, "confirmed": dict(confirmed), "changed": sorted(changed)}
    return bool(write_json(path, data))


def load(path: str) -> dict:
    """A progress file read back and checked: {'mode', 'files', 'state', 'confirmed', 'changed', 'saved'}.
    Raises ValueError for a file that is not Live View progress."""
    from rstools import limits
    try:
        limits.check_size(path, "PROGRESS_MAX_BYTES", "progress file")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError(f"The progress file could not be read ({exc}).")
    if not isinstance(data, dict) or data.get("kind") != "live_progress":
        raise ValueError("This is not a Live View progress file.")
    raw_files = data.get("files")
    files = ({str(k): [str(p) for p in v] for k, v in raw_files.items() if isinstance(v, list)}
             if isinstance(raw_files, dict) else {})
    raw_conf = data.get("confirmed")
    confirmed = {str(k): str(v) for k, v in raw_conf.items()} if isinstance(raw_conf, dict) else {}
    changed = [str(k) for k in data.get("changed", []) if isinstance(k, str)]
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    return {"mode": str(data.get("mode", "")), "files": files, "state": state, "confirmed": confirmed,
            "changed": changed, "saved": str(data.get("saved", ""))}


def load_auto(mode: str, files: Dict[str, List[str]]) -> Optional[dict]:
    """The progress saved automatically for this comparison, if any."""
    path = autosave_path(mode, files)
    if not os.path.exists(path):
        return None
    try:
        return load(path)
    except ValueError:
        return None
