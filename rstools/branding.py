"""The app's name, file names and data folder (settings, rule sets, fleet data, error log - no admin rights
or registry needed).

The exe keeps its data in a 'TrainPlanningTools-data' folder beside itself, so it is portable: copy the exe
and that folder together and everything comes too. If the exe's folder cannot be written to (e.g. a shared
or read-only folder), the per-user %LOCALAPPDATA%\\TrainPlanningTools folder is used instead; if that cannot
be written either, the app runs with its defaults. Running from source uses %LOCALAPPDATA%."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from typing import Dict

APP_NAME = "Train Planning Tools"
FOLDER = "TrainPlanningTools"
PORTABLE_FOLDER = FOLDER + "-data"            # beside the exe

_chosen: Dict[str, str] = {}                  # portable folder -> the folder in use (checked once per run)


def _base() -> str:
    return os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")


def _portable_dir() -> str:
    """The data folder beside the exe ('' when running from source)."""
    if not getattr(sys, "frozen", False):
        return ""
    return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), PORTABLE_FOLDER)


def _writable(path: str) -> bool:
    """True if the folder exists (or can be made) and a file can be written in it."""
    try:
        os.makedirs(path, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix="~write", suffix=".tmp", dir=path)   # a new, unique file
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        return False


def _copy_previous(dest: str):
    """A new portable folder starts with the settings already saved in %LOCALAPPDATA% (left untouched)."""
    src = os.path.join(_base(), FOLDER)
    if not os.path.isdir(src):
        return
    try:
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.tmp", "~*"))
    except (OSError, shutil.Error):
        pass                                  # whatever could not be copied falls back to the defaults


def _appdata_dir() -> str:
    """%LOCALAPPDATA%\\TrainPlanningTools."""
    path = os.path.join(_base(), FOLDER)
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass                                  # read-only profile: run with the defaults
    return path


def settings_dir() -> str:
    """The app's data folder: beside the exe when it can be written to, else %LOCALAPPDATA% (see above)."""
    portable = _portable_dir()
    if not portable:
        return _appdata_dir()
    if portable not in _chosen:
        fresh = not os.path.isdir(portable)
        if _writable(portable):
            if fresh:
                _copy_previous(portable)
            _chosen[portable] = portable
        else:
            if fresh:
                try:
                    os.rmdir(portable)        # made but not writable: leave nothing behind
                except OSError:
                    pass
            _chosen[portable] = _appdata_dir()
    return _chosen[portable]
