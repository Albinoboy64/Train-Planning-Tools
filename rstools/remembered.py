"""Clearing the inputs the app remembers from earlier runs (Settings > Clear remembered inputs...).

Each tab fills its boxes with what was used last time: files, the output folder, station and location names, the
berthing chart's left-out and added locations, recent-file lists, Stats Pack's groups, stations and dates. This
clears those back to empty (or to the app's own default where a box has one), and keeps everything that is a
choice or a preference: the highlight colour, theme, text size, change categories, output type and format, operator
choices, tick-box options, the task chosen, saved Load/Save settings, and the data in Settings (fleet, depots,
corridors, berthing locations and notes, rules). No file other than the settings files themselves is touched."""
from __future__ import annotations

from typing import List

# the Options (settings.json) fields that hold remembered inputs
OPTION_FIELDS: List[str] = [
    "original", "updated", "output_dir", "output_name", "days",
    "book_station", "book_platforms", "book_list", "book_timetable", "book_services", "book_label", "book_merge",
    "book_hidden_ops", "book_days",
    "berth_files", "berth_issue", "berth_timetable", "berth_leave_out", "berth_add",
    "recent", "live_folder",
]

CLEARED = ("the files chosen and the recent-file lists, the output folders and names, station and platform names, "
           "the berthing chart's issue, timetable and left-out or added locations, Stats Pack's service groups, "
           "corridors, stations, times, fleets and mileage dates")
KEPT = ("colours, theme, text size, output options, operator choices, tick-box options, your saved settings "
        "(Load/Save) and everything in Settings (fleet data, depots, corridors, berthing locations, notes, rules)")


def clear_options(opts) -> None:
    """Put the remembered-input fields of `opts` (an Options) back to their defaults; the rest is kept."""
    from cwn_compare.options import Options
    fresh = Options()
    for name in OPTION_FIELDS:
        setattr(opts, name, getattr(fresh, name))


def question() -> str:
    """The confirmation shown before clearing."""
    return (f"Clear the inputs remembered from earlier runs?\n\nCleared: {CLEARED}.\n\nKept: {KEPT}.\n\n"
            "No input or output files are deleted.")
