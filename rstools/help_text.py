"""Help shown when the mouse rests on a control, keyed by the control's own text (so it follows labels
that change with the chosen mode). Input boxes take the help of the label to their left."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from .widgets import Tooltip

TIPS = {
    # ---------------------------------------------------------------- shared
    "Add...": "Add files to this box. Files already in it are kept, so files from different folders can be used "
              "together.",
    "Ignore trains in the source that are not in the files compared with it": "Leave out trains (or rows) found "
        "only in the first file - the original or the reference - e.g. when a print covers only part of a "
        "timetable. Trains only in the second file are still shown.",
    "Check for differences (untick to pair trains for checking by eye)": "Untick to switch error checking off: "
        "each train is put side by side with its match for checking by eye, with nothing coloured or flagged. "
        "Trains found in only one file are still listed, so nothing is missed.",
    "Save to folder:": "Where the output is saved, on this PC (never a network or shared drive). Leave blank "
                       "to save it to your Downloads folder.",
    "Output name:": "File name for the output, without the extension. Leave blank to use the name shown "
                    "underneath. An existing file is never overwritten: (2), (3)... is added instead.",
    "Save as:": "Excel (default) keeps colours, filters and frozen headings. PDF and Word are for printing "
                "or sending on.",
    # ---------------------------------------------------------------- Stock Tools
    "Add a new round to an earlier comparison CWN": "Compare a newer CWN with a comparison CWN made earlier by this "
                                                    "app. The earlier highlights are kept and the new round is "
                                                    "shown in another colour.",
    "Compare two folders of CWNs (batch)": "Compare every CWN in one folder with its partner in another folder "
                                           "(paired by file name).",
    "CWN:": "The multi-day CWN. It is not changed - a copy is saved.",
    "1. CWN comparison": "Choose the comparison, then its files. CWNs or folders dropped on this box go here.",
    "Utilities": "Tools that take their own files. Files dropped on this box go here.",
    "Section 4 check: trains in Network Rail's standard possession times": "Check the Attune XML against the "
        "Engineering Access Statement Section 4: every train running through a section during one of its "
        "possessions.",
    "Section 4 PDF(s):": "The Section 4 PDFs, one per route, e.g. Kent & Sussex, East Coast, East Midlands. Leave "
                         "blank to use the rule set in use: the built-in 2027 EAS v4 rules, or a newer set added "
                         "in Options > Rules and reference data.",
    "Station Working Book (TRACS-RS layout, from an Attune XML)": "One sheet each for SX, SO and Su. Needs an "
        "Attune XML with every day's unit diagrams.",
    "Station:": "The station, as named in the XML. Type to see matching stations.",
    "Platforms (optional):": "Only trains leaving from these platforms, e.g. 10-15 for London Bridge low level, "
                             "or 1, 2, 4A. Leave blank for every platform.",
    "Operator:": "For the page header and file name, e.g. GTR(TLGN). The part in brackets also goes in the sheet "
                 "names.",
    "Timetable:": "For the page header and file name, e.g. Dec23. Filled in from the XML's start date.",
    "Services:": "For the page header, e.g. 'Thameslink and Great Northern services only'.",
    "Sheet name:": "The start of each sheet's name, before SX / SO / Su. Blank: the station and operator, e.g. "
                   "'London Kings Cross (TLGN)'.",
    "SX": "A sheet for Monday to Friday. Trains that differ by day get a row for each version, marked e.g. "
          "'Runs Monday and Friday only'.",
    "By first day run - MO first, then TO, WO, ThO, FO (then SO, SuO)":
        "The first day each variant runs decides its place, whatever the times: MO or MWO first, then TO, then WO, "
        "ThFO, FO, then Saturday and Sunday.",
    "By departure time - earliest first, then by day": "The variant that departs earliest comes first (e.g. an "
                                                       "FO train at 05.30 before an MO train at 06.10); "
                                                       "variants at the same time go in day order.",
    "Earlier comparison CWN:": "A comparison CWN made by this app. Its stored data is used as the original.",
    "Updated CWN:": "The newer CWN (Excel). The output is a copy of this file with every change marked.",
    "Updated CWN folder:": "Each CWN here is paired with the original of the same name once proof, draft and "
                           "version numbers and dates are ignored (e.g. BTN_CWN_v1.2 with BTN_CWN_v2.0), "
                           "otherwise with the clearly most similar name.",
    "Output type:": "Full CWN highlighted and noted: the whole updated CWN with changes highlighted, previous "
                    "values struck through and notes added. Highlighted only: the updated CWN with anything new or "
                    "changed highlighted, without the original versions. ACWN: only the amended trains.",
    "Colour for new amendments:": "Colour for this round's changes - choose one not used by earlier rounds.",
    "Create change report as": "Also write a change report listing every change by type, location and train.",
    "Days to check:": "Untick days to check and output only the trains running on the ticked days. Days the "
                      "chosen CWNs do not cover are greyed out.",
    "Reset to defaults": "Switch every change type back on.",
    "Highlight only (no old values)": "Mark changes without showing the previous values struck through.",
    # ---------------------------------------------------------------- berthing charts
    "Berthing Charts": "Files dropped on this box go here.",
    "Make a berthing chart from an Attune XML": "Where each unit berths every night at the out-berth platforms and "
        "sidings, laid out like a chart you choose. A new chart has no highlights.",
    "Add a round of changes to a berthing chart": "Remakes the chart from the updated XML. Cells that differ from the "
        "original XML are filled in the chosen colour; earlier highlights are kept.",
    "Compare two berthing charts": "Highlights in the newer chart every unit or time that differs from the older one. "
        "Spacing slips and the old 'L' marker do not count.",
    "STP XML (optional):": "For an STP chart: each day's STP diagrams replace the LTP ones, and STP trains are shown "
                           "in bold on lavender.",
    "Layout from chart (optional):": "Leave blank to use the app's built-in layout (from the Dec 26 Proof 2 chart). "
                                     "Or choose an earlier berthing chart: its sheets, berths, capacities and notes "
                                     "are kept and the units come from the XML.",
    "Berthing chart:": "The chart to add this round's changes to.",
    "Original XML:": "The XML the chart was made from. For an STP chart: the LTP and STP XMLs, separated by ';'.",
    "Updated XML:": "The changed XML. For an STP chart: the LTP and STP XMLs, separated by ';'.",
    "Issue on cover:": "Shown on the cover, e.g. Proof 2. Leave blank to keep the chart's own.",
    "Edit berth locations...": "Open the list that links each berth to its XML location (TIPLOC and platform or "
                               "road) in Excel.",
    # ---------------------------------------------------------------- Stats Pack
    "Create a stats pack": "Build the rolling stock stats pack for the chosen days from an Attune XML and its "
                           "TRENT diagram print.",
    "Compare two plans (two sets of XML + TRENT print)": "Build stats packs for two plans and show every "
                                                          "difference (mileage, units, formations, times...).",
    "Compare two stats pack files": "Compare two stats pack workbooks made earlier (by this app or TRACS-RS).",
    "Fuel check (171s)": "Follow each diesel unit (171/7, 171/8) through the week and check it is fuelled at least "
                         "every 48 hours; units that are not are listed first. Always covers the ticked days "
                         "together, even when 'Each ticked day on its own' is chosen.",
    "Several stations:": "Make a book for each of several stations in one run. Pick a "
                         "station (and platforms) and press Add to list, or type them separated by ';' with "
                         "platforms in brackets, e.g. London Kings Cross; London Bridge [10-15]; Cambridge.",
    "Attune XML (optional):": "The Attune diagram export (.xml) of the plan. Unit reports can be made from the "
                              "TRENT print alone: the XML adds next-day workings for SNGX diagrams.",
    "TRENT VL29 print(s):": "The TRENT VehicleLayout29 print (saved as Word), from the same plan as the XML. "
                            "Several prints can go in this box, e.g. the LTP print and a week's STP print.",
    "Each ticked day on its own": "Report each ticked day separately (unit reports: no following of units "
                                  "between days; capacity report: no week total).",
    "Capacity report: by headcode group, corridor or station to station": "Seating capacity and / or standing "
        "room of every passenger train in a headcode group, on a corridor or between two stations, per day or for "
        "the week, optionally only trains at a station between two times. From the fleet data.",
    "Standing room": "Show standing capacity. With both ticked, total capacity (seats + standing) is shown too.",
    "Service group:": "Count the trains of one headcode group: pick from the list or type one, e.g. 1F or 9T.",
    "Corridor:": "Count every passenger train running along this route. Choose one direction (in the box "
                 "underneath) or both. Corridors are an editable list (Edit corridors).",
    "Station to station:": "Count the trains that stop at the first station and later at the second. Seats are "
                           "the smallest formation between them; a time window is the departure from the first "
                           "station. Type in a box to see matching stations.",
    "Only trains between": "Count only trains arriving at / departing from the chosen station between these "
                           "times (24-hour, e.g. 07:00 and 10:00), e.g. the morning peak into London Victoria.",
    "Edit corridors...": "Open the corridor list in Excel: each corridor's name and its stations in route order "
                         "(which sets the direction), plus optional rules.",
    "Compare two timetables (original and updated XML + TRENT print)": "Make the report for two timetables and "
        "show what changed: every figure side by side for the summaries, and only the changes for trains, units "
        "and diagrams.",
    "Diagram days:": "Days of the diagrams to include. Days not in the TRENT print or XML are flagged.",
    "Summary of key figures": "Start the comparison with the headline figures (miles, time, trains, units) "
                              "before and after.",
    "Flag mileage increases over": "Highlight in red any train, unit or formation mileage that rises by more "
                                   "than this many miles.",
    "Edit fleet data (operator, seats, units, lengths)...": "Open your fleet table in Excel to correct operators, "
                                                           "seats, vehicles per unit, fleet sizes and unit "
                                                           "lengths.",
    # ---------------------------------------------------------------- Timing Tools
    "GTR timetable against the Network Rail timetable": "Check the GTR timetable against the Network Rail "
                                                         "timetable (the reference). Output: the Consolidated "
                                                         "TT Comparison workbook.",
    "Train prints against a timetable (Attune Single Train Report)": "Use Attune 'Single Train Report' prints as "
                                                                      "the reference and check a timetable "
                                                                      "against their public times.",
    "Attune train list against a timetable": "Use an Attune train list as the reference and check each train's "
                                              "origin departure and destination arrival in a timetable.",
    "GTR timetable:": "The GTR timetable check workbook (sheets such as 'OT SNGX TT Checks K - OUT SX').",
    "Network Rail timetable:": "The Network Rail timetable workbook - the reference.",
    "Attune train list - reference:": "The Attune train list export (Excel or CSV).",
    "Timetable to check:": "The timetable workbook to check (GTR or Network Rail layout).",
    # ---------------------------------------------------------------- Live View
    "Compare:": "What to compare - any comparison the other tabs can do.",
    "Refresh when a file is saved": "Watch the files: when one is saved, compare again within a moment and "
                                    "mark the trains that changed.",
    "Find:": "Show only trains whose section, headcode or status contains this text.",
    "Days:": "Untick days to show only the trains running on the ticked days.",
    "Export...": "Save the trains listed (with the current filter and search) and their differences to "
                 "Excel, PDF or Word.",
    # ---------------------------------------------------------------- more Stats Pack
}


def lookup(text: str) -> Optional[str]:
    key = " ".join(str(text or "").split())
    if key in TIPS:
        return TIPS[key]
    if key == "Other depots":
        return "Include diagrams from depots that belong to neither operator."
    return None


class _TextTip(Tooltip):
    """A tooltip whose text is looked up when it is shown (labels change with the mode)."""

    def __init__(self, widget, source):
        super().__init__(widget, "")
        self.source = source

    def show(self, _e=None):
        try:
            source = self.source if self.source is not None else _label_for(self.widget)
            self.text = (lookup(source.cget("text")) or "") if source is not None else ""
        except tk.TclError:
            self.text = ""
        super().show()


_LABELLED = (ttk.Label, ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.Menubutton)
_INPUTS = (ttk.Entry, ttk.Combobox, ttk.Spinbox)


def attach(root):
    """Give every labelled control under `root` its help, and every input box the help of its label."""
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if getattr(w, "_has_tip", False):
            continue
        if isinstance(w, _LABELLED):
            w._has_tip = True
            _TextTip(w, w)
        elif isinstance(w, _INPUTS):                # the label is found when shown (rows move with the mode)
            w._has_tip = True
            _TextTip(w, None)


def _label_for(widget):
    """The label on the same grid row, to the left of an input box."""
    try:
        info = widget.grid_info()
        row, col = int(info.get("row", -1)), int(info.get("column", -1))
        if row < 0:
            return None
        best, best_col = None, -1
        for sib in widget.master.grid_slaves(row=row):
            if isinstance(sib, ttk.Label):
                c = int(sib.grid_info().get("column", 99))
                if best_col < c < col:
                    best, best_col = sib, c
        return best
    except (tk.TclError, ValueError, KeyError):
        return None
