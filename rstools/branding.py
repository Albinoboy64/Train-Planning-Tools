"""The app's name, file names and per-user settings folder (no admin rights needed)."""
from __future__ import annotations

import os
import shutil

APP_NAME = "Train Planning Tools"
FOLDER = "TrainPlanningTools"
OLD_FOLDERS = ("RollingStockTools",)          # used by 2.x, before the rename
SETTINGS_FILES = ("settings.json", "statspack.json", "timetable.json", "fleet.csv", "depots.csv")


def _base() -> str:
    return os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")


def settings_dir() -> str:
    """%LOCALAPPDATA%\\TrainPlanningTools. The first time it is needed, settings, fleet data and the depot
    list saved by Rolling Stock Tools 2.x are copied across (the old folder is left untouched)."""
    path = os.path.join(_base(), FOLDER)
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
            for old in OLD_FOLDERS:
                src = os.path.join(_base(), old)
                if os.path.isdir(src):
                    for name in SETTINGS_FILES:
                        if os.path.isfile(os.path.join(src, name)):
                            shutil.copy2(os.path.join(src, name), os.path.join(path, name))
                    break
        except OSError:
            pass                                  # read-only profile: run with the defaults
    return path
