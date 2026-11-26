"""User options for a comparison run (also persisted between sessions)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from .compare import CATEGORIES

PRESET_COLOURS = {
    "Yellow": "FFFF00",
    "Light green": "92D050",
    "Light blue": "9BC2E6",
    "Orange": "FFC000",
    "Pink": "FF99CC",
    "Lavender": "CCC0DA",
    "Turquoise": "66FFFF",
    "Light red": "FF7C80",
}


def default_name(original: str = "", updated: str = "") -> str:
    """Output name used when none is given: today's date and 'original vs updated' (shortened)."""
    from rstools.naming import compare_name
    return compare_name(original, updated)


def default_categories() -> Dict[str, Dict[str, bool]]:
    return {k: {"cwn": True, "show_old": has_old, "report": True}
            for k, _lbl, has_old, _d in CATEGORIES}


@dataclass
class Options:
    mode: str = "compare"            # compare | cumulative | batch | reorder | station | berth_make / round / compare
    variant_order: str = "day"       # reorder mode: day (MO first ... FO, SO, Su) | time (departure time first)
    merge_variants: bool = False     # reorder mode: merge a train's variants that differ only in their days
    merge_diagrams: bool = False     # ... also when only their diagram numbers differ (each shown with its days)
    merge_berths: bool = False       # ... also when they berth for the same next working (day codes combined)
    merge_berth_diagrams: bool = False   # ... also when that next working's diagram number differs
    book_station: str = ""           # station working book: station, platforms, title parts, day sheets
    book_platforms: str = ""
    book_list: str = ""              # several stations: 'London Kings Cross; London Bridge [10-15]; Cambridge'
    book_operator: str = "GTR(TLGN)"
    book_timetable: str = ""
    book_services: str = "Thameslink and Great Northern services only"
    book_label: str = ""
    book_merge: str = ""             # other operators' Attune XMLs merged into the book ('a.xml; b.xml')
    book_days: List[str] = field(default_factory=lambda: ["SX", "SO", "Su"])
    berth_files: Dict[str, List[str]] = field(default_factory=dict)   # berthing chart mode -> its file boxes
    berth_issue: str = ""            # berthing chart: the issue shown on the cover, e.g. 'Proof 2'
    berth_counts: bool = False       # berthing chart: unit counts under each siding location
    original: str = ""               # original CWN, or previous comparison CWN (cumulative)
    updated: str = ""
    output_type: str = "full"        # full (highlighted and noted) | highlight (highlighted only) | acwn
    colour: str = "FFFF00"           # highlight colour for this round
    highlight_tabs: bool = True
    keep_links: bool = False         # headcode hyperlinks between tabs (slow to open in Excel)
    make_report: bool = True
    report_format: str = "xlsx"      # change report as xlsx | pdf | docx
    output_dir: str = ""
    output_name: str = ""            # blank -> today's date
    ignore_spacing: bool = True      # ignore spacing / punctuation-only differences in free text
    open_when_done: bool = False     # open the output when a run finishes (both tabs)
    theme: str = "system"            # light | dark | contrast | system (follow Windows)
    text_size: str = "normal"        # small | normal | large | xlarge
    live_details_open: bool = False  # Live View: Train Header Details rows of train prints shown (unfolded)
    live_check_header: bool = True   # Live View: header differences (days, IDs, class...) are checked
    live_check_timing: bool = True   # Live View: timing differences are checked
    live_passenger_only: bool = False    # Live View: passing / one-sided intermediate times hidden
    live_window: str = ""            # Live View's own window: its last size and place, 'WxH+X+Y'
    live_window_on_top: bool = False     # Live View's own window: kept above other windows
    check_updates: bool = True       # look for a newer release on GitHub when the app starts
    notify_done: bool = True         # flash the taskbar and show a notice when a run ends in the background
    saved: Dict[str, dict] = field(default_factory=dict)     # saved comparisons: name -> {tab, state}
    github_token: str = ""           # read-only token for a private repository (DPAPI-protected)
    recent: Dict[str, List[str]] = field(default_factory=dict)   # file box -> recent files
    days: List[int] = field(default_factory=list)   # CWN days to check and output (empty = every day)
    window: str = ""                 # the window's last size and place, 'WxH+X+Y' (normal state only)
    last_tab: int = 0                # tab shown at start (0 Stock Tools, 1 Stats Pack, 2 Timing Tools, 3 Live View)
    categories: Dict[str, Dict[str, bool]] = field(default_factory=default_categories)

    def cat(self, key: str, what: str) -> bool:
        """Setting `what` (cwn / show_old / report) for change category `key` (default on)."""
        return bool(self.categories.get(key, {}).get(what, True))

    # ----- persistence (per-user, no admin rights needed) -----
    @staticmethod
    def settings_path() -> str:
        from rstools.branding import settings_dir
        return os.path.join(settings_dir(), "settings.json")

    def save(self):
        from rstools.fsutil import write_json
        write_json(self.settings_path(), asdict(self))

    @classmethod
    def load(cls) -> "Options":
        o = cls()
        try:
            with open(cls.settings_path(), encoding="utf-8") as fh:
                d = json.load(fh)
            defaults = cls()
            for k, v in d.items():         # ignore unknown keys and values of the wrong type
                if k != "categories" and hasattr(o, k) and isinstance(v, type(getattr(defaults, k))):
                    setattr(o, k, v)
            o.recent = {k: [p for p in v if isinstance(p, str)] for k, v in o.recent.items()
                        if isinstance(k, str) and isinstance(v, list)}
            o.saved = {k: v for k, v in o.saved.items() if isinstance(k, str) and isinstance(v, dict)
                       and isinstance(v.get("tab"), int) and isinstance(v.get("state"), dict)}
            cats = default_categories()
            for k, v in (d.get("categories") or {}).items():
                if k in cats:
                    cats[k].update({kk: bool(vv) for kk, vv in v.items() if kk in cats[k]})
            o.categories = cats
        except (OSError, ValueError, TypeError):
            pass
        return o
