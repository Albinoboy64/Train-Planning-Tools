"""Help shown when the mouse rests on a control, keyed by the control's own text (so it follows labels
that change with the chosen mode). Input boxes take the help of the label to their left."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .widgets import Tooltip

_DAYS = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday",
         "Sat": "Saturday", "Sun": "Sunday", "MO": "Monday", "TO": "Tuesday", "WO": "Wednesday", "ThO": "Thursday",
         "FO": "Friday", "SO": "Saturday", "Su": "Sunday"}

TIPS = {
    # ---------------------------------------------------------------- shared
    "Browse...": "Choose the file (or folder) in a file window. You can also drag files onto the tab.",
    "Open folder": "Open the folder the output was saved in.",
    "Add...": "Add train prints to this box (hold Ctrl or Shift to pick several). Prints already in the box are "
              "kept, so prints from different folders can be compared together. You can also drop prints on the box.",
    "Clear": "Empty this box.",
    "Ignore trains in the source that are not in the files compared with it": "Leave out trains (or rows) found "
        "only in the first file - the original or the reference - e.g. when a print covers only part of a "
        "timetable. Trains only in the second file are still shown.",
    "Check for differences (untick to pair trains for checking by eye)": "Untick to switch error checking off: "
        "each train is put side by side with its match for checking by eye, with nothing coloured or flagged. "
        "Trains found in only one file are still listed, so nothing is missed.",
    "Open output": "Open the file that was just created.",
    "Open when finished": "Open the output automatically as soon as a run finishes.",
    "Save to folder:": "Where the output is saved. Leave blank to save it next to the (updated) input file.",
    "Output name:": "File name for the output, without the extension. Leave blank to use the name shown "
                    "underneath. An existing file is never overwritten: (2), (3)... is added instead.",
    "Save as:": "Excel (default) keeps colours, filters and frozen headings. PDF and Word are for printing "
                "or sending on.",
    "Excel (default)": "An Excel workbook (.xlsx) - the most useful format for checking and filtering.",
    "PDF": "A PDF document (A4 landscape) for printing or emailing.",
    "Word": "A Word document (.docx) for printing or adding comments.",
    # ---------------------------------------------------------------- Stock Tools
    "Compare two CWNs": "Compare an original Carriage Working Notice with an updated one.",
    "Add a new round to an earlier comparison CWN": "Compare a newer CWN with a comparison CWN made earlier by this "
                                                    "app. The earlier highlights are kept and the new round is "
                                                    "shown in another colour.",
    "Compare two folders of CWNs (batch)": "Compare every CWN in one folder with its partner in another folder "
                                           "(paired by file name), using several CPU cores at once.",
    "Put each train's day variants in order (one CWN)": "Make a tidier copy of one multi-day CWN in which "
                                                         "each train's day variants (MO, TWThO, FO...) are listed "
                                                         "in a fixed order. Nothing is changed or removed.",
    "CWN:": "The multi-day CWN (Excel) to tidy. It is not changed - a copy is saved.",
    "1. CWN comparison": "Compare CWNs: choose one of the three comparisons, then its files below. Dropping CWNs "
                         "or folders on this box puts them here.",
    "Utilities": "Tools that take one input: on Stock Tools, a CWN to put in order or an Attune XML for a station "
                 "working book; on Timing Tools, the Section 4 check. Dropping files on this box puts them here.",
    "Section 4 check: trains in Network Rail's standard possession times": "Check the timetable (Attune XML) "
        "against Network Rail's Engineering Access Statement Section 4: every train running over a section inside "
        "one of its standard possession windows, by period and night. Choose the route PDFs that cover the "
        "timetable.",
    "Section 4 PDF(s):": "Network Rail's Engineering Access Statement Section 4 (Standard Possession Opportunities) "
                         "PDFs, one per route, e.g. Kent & Sussex, East Coast, East Midlands. Add... adds to those "
                         "already chosen.",
    "1. Timetable comparison": "Compare timetables, train prints and train lists: choose the comparison, then its "
                               "two files below.",
    "Station Working Book (TRACS-RS layout, from an Attune XML)": "Make a Station Working Book like the TRACS-RS "
        "ones: every train leaving the station, with the train(s) it is formed from, its stock, platform and "
        "calling points, one sheet each for SX, SO and Su. Needs an Attune XML with every day's unit diagrams.",
    "Station:": "The station, as named in the XML. Type to narrow the list.",
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
    "Make station working book": "Make the book (F5).",
    "Open station working book": "Open the book in Excel.",
    "Order of each train's day variants:": "How the variants of the same train are ordered on each tab.",
    "By day - MO first, then TO, WO, ThO, FO (then SO, SuO)": "Monday's variant first, then the rest in day order "
                                                              "to Friday, then Saturday and Sunday.",
    "By departure time - earliest first, then by day": "The variant that departs earliest comes first (e.g. an "
                                                       "FO train at 05.30 before an MO train at 06.10); "
                                                       "variants at the same time go in day order.",
    "Put variants in order": "Save the tidied copy of the CWN (F5 or Ctrl+Enter).",
    "Open tidied CWN": "Open the copy of the CWN with the variants in order.",
    "Original CWN:": "The earlier CWN (Excel). Its trains are the starting point of the comparison.",
    "Earlier comparison CWN:": "A comparison CWN made by this app. Its stored data is used as the original.",
    "Updated CWN:": "The newer CWN (Excel). The output is a copy of this file with every change marked.",
    "Original CWN folder:": "Folder holding the earlier CWNs.",
    "Updated CWN folder:": "Folder holding the newer CWNs. Each is paired with the original of the most "
                           "similar name.",
    "Swap original / updated": "Swap the two files over.",
    "Output type:": "Full CWN: the whole updated CWN with changes highlighted. ACWN: only the amended trains.",
    "Full CWN with changes highlighted": "The whole updated CWN, with every amended cell coloured.",
    "ACWN (amended trains only)": "An Amended CWN: only the trains that changed, on only the tabs that changed.",
    "Highlight colour:": "Colour used to mark the changes found in this run.",
    "Colour for new amendments:": "Colour for this round's changes - choose one not used by earlier rounds.",
    "Highlight tabs that contain changes": "Colour the sheet tabs (at the bottom in Excel) of locations with "
                                           "changes.",
    "Create change report as": "Also write a change report listing every change by type, location and train.",
    "Days to check:": "Untick days to check and output only the trains running on the ticked days. Days the "
                      "chosen CWNs do not cover are greyed out.",
    "All": "Tick every day the CWNs cover again.",
    "Reset to defaults": "Switch every change type back on.",
    "Highlight only (no old values)": "Mark changes without showing the previous values struck through.",
    "Run comparison": "Start the comparison (F5).",
    "Open output CWN": "Open the comparison CWN in Excel.",
    "Open report": "Open the change report.",
    # ---------------------------------------------------------------- Stats Pack
    "Create a stats pack": "Build the rolling stock stats pack for the chosen days from an Attune XML and its "
                           "TRENT diagram print.",
    "Compare two plans (two sets of XML + TRENT print)": "Build stats packs for two plans and show every "
                                                          "difference (mileage, units, formations, times...).",
    "Compare two stats pack files": "Compare two stats pack workbooks made earlier (by this app or TRACS-RS).",
    "Fuel check (171s)": "Follow each diesel unit (171/7, 171/8) through the week and check it is fuelled at least "
                         "every 48 hours; units that are not are listed first. Always covers the ticked days "
                         "together, even when 'Each ticked day on its own' is chosen.",
    "Unit reports: washes and CETs, depot returns / swaps, captive units, fuel": "Reports that follow each unit "
                                                                            "through the week: washes and CETs "
                                                                            "(Controlled Emission Toilet "
                                                                            "servicing), depot returns and swaps, "
                                                                            "and units captive to one diagram.",
    "Several stations:": "Make a book for each of several stations in one run (shared over the CPU cores). Pick a "
                         "station (and platforms) and press Add to list, or type them separated by ';' with "
                         "platforms in brackets, e.g. London Kings Cross; London Bridge [10-15]; Cambridge.",
    "Add to list": "Add the chosen station (and platforms) to the list of stations to make books for.",
    "Attune XML:": "The Attune diagram export (.xml) of the plan.",
    "Original XML:": "The Attune diagram export (.xml) of the original plan.",
    "Updated XML:": "The Attune diagram export (.xml) of the updated plan.",
    "Original Attune XML:": "The Attune diagram export (.xml) of the original plan.",
    "Updated Attune XML:": "The Attune diagram export (.xml) of the updated plan.",
    "Attune XML (optional):": "The Attune diagram export (.xml) of the plan. Unit reports can be made from the "
                              "TRENT print alone: the XML adds next-day workings for SNGX diagrams.",
    "TRENT VL29 print(s):": "The TRENT VehicleLayout29 unit diagram print saved as Word (.docx), from the same plan "
                            "as the XML (TIPLOCs, LTP / STP, miles). Several VL29 prints can go in this box - e.g. "
                            "the LTP print with a week's STP print: Browse lets you pick several, or drop them all "
                            "on the box. Other TRENT layouts (VehicleLayout23, 11, 05) are not used.",
    "Original TRENT VL29 print(s):": "The TRENT VehicleLayout29 print(s) (.docx) of the original plan.",
    "Updated TRENT VL29 print(s):": "The TRENT VehicleLayout29 print(s) (.docx) of the updated plan.",
    "Original stats pack:": "The earlier stats pack workbook (.xlsx).",
    "Updated stats pack:": "The newer stats pack workbook (.xlsx).",
    "Washes and CETs": "How many washes and CETs each unit gets in the week, and where.",
    "Depot returns / swaps": "When units go back to depot, and swaps between depots.",
    "Captive units": "Units (or diagrams) that stay on the same work all week.",
    "Whole week (follows each unit with the next-day workings)": "Follow each unit from day to day using the "
                                                                 "next-day working in the Attune XML.",
    "Each ticked day on its own": "Report each ticked day separately (unit reports: no following of units "
                                  "between days; capacity report: no week total).",
    "Capacity report: by headcode group, corridor or station to station": "Seating capacity and / or standing "
        "room of every passenger train in a headcode group, on a corridor or between two stations, per day or for "
        "the week, optionally only trains at a station between two times. From the fleet data.",
    "Seating capacity": "Show First Class, Standard Class and total seats.",
    "Standing room": "Show standing capacity. With both ticked, total capacity (seats + standing) is shown too.",
    "Service group:": "Count the trains of one headcode group, e.g. 1F, 1W or 2F (the first two characters of "
                      "the headcode). The list comes from the Attune XML, with each group's main routes.",
    "Corridor:": "Count every passenger train running along this route. Choose one direction (in the box "
                 "underneath) or both. Corridors are an editable list (Edit corridors).",
    "Station to station:": "Count the trains that stop at the first station and later at the second. Seats are "
                           "the smallest formation between them; a time window is the departure from the first "
                           "station. Type in a box to narrow the list of stations.",
    "Whole week (each day, week total and daily average)": "One row per ticked day, then the week total and the "
                                                            "average per day.",
    "Only trains between": "Count only trains arriving at / departing from the chosen station between these "
                           "times (24-hour, e.g. 07:00 and 10:00), e.g. the morning peak into London Victoria.",
    "Edit corridors...": "Open the corridor list in Excel: each corridor's name and its stations in route order "
                         "(which sets the direction), plus optional rules.",
    "Create capacity report": "Start (F5).",
    "Compare two timetables (original and updated XML + TRENT print)": "Make the report for two timetables and "
        "show what changed: every figure side by side for the summaries, and only the changes for trains, units "
        "and diagrams.",
    "Diagram days:": "Days of the diagrams to include. Days not in the TRENT print or XML are flagged.",
    "All days": "Tick every day.",
    "Weekdays": "Tick Monday to Friday only.",
    "Weekend": "Tick Saturday and Sunday only.",
    "None": "Untick all.",
    "Operators and fleets:": "Which operators' depots and which unit classes to include.",
    "All fleets": "Tick every fleet in the TRENT print.",
    "Summary of key figures": "Start the comparison with the headline figures (miles, time, trains, units) "
                              "before and after.",
    "Changed tabs only": "Leave out tabs with no differences.",
    "Changed rows only": "On each tab, show only the rows that changed.",
    "Flag mileage increases over": "Highlight in red any train, unit or formation mileage that rises by more "
                                   "than this many miles.",
    "Edit fleet data (operator, seats, units, lengths)...": "Open your fleet table in Excel to correct operators, "
                                                           "seats, vehicles per unit, fleet sizes and unit "
                                                           "lengths.",
    "Create stats pack": "Start (F5).",
    "Compare plans": "Start (F5).",
    "Compare stats packs": "Start (F5).",
    "Create unit report": "Start (F5).",
    # ---------------------------------------------------------------- Timing Tools
    "GTR timetable against the Network Rail timetable": "Check the GTR timetable against the Network Rail "
                                                         "timetable (the reference). Output: the Consolidated "
                                                         "TT Comparison workbook.",
    "Train prints against a timetable (Attune Single Train Report)": "Use Attune 'Single Train Report' prints as "
                                                                      "the reference and check a timetable "
                                                                      "against their public times.",
    "Attune train list against a timetable": "Use an Attune train list as the reference and check each train's "
                                              "origin departure and destination arrival in a timetable.",
    "Two sets of train prints (PDF or Word)": "Compare two versions of the train prints train by train and call "
                                               "by call.",
    "Two Attune train list exports (Excel)": "Compare two Attune train list exports column by column.",
    "GTR timetable:": "The GTR timetable check workbook (sheets such as 'OT SNGX TT Checks K - OUT SX').",
    "Network Rail timetable:": "The Network Rail timetable workbook - the reference.",
    "Train print(s) - reference:": "One or more Attune 'Single Train Report' prints (PDF or Word). Hold Ctrl in "
                                   "the file window to choose several.",
    "Attune train list - reference:": "The Attune train list export (Excel or CSV).",
    "Timetable to check:": "The timetable workbook to check (GTR or Network Rail layout).",
    "Original train print(s):": "The earlier train prints (PDF or Word). Several files can be chosen.",
    "Updated train print(s):": "The newer train prints (PDF or Word). Several files can be chosen.",
    "Original Attune train list:": "The earlier Attune train list export.",
    "Updated Attune train list:": "The newer Attune train list export.",
    "Swap files": "Swap the two files over.",
    "Compare timetables": "Start (F5).",
    "Check timetable": "Start (F5).",
    "Compare train prints": "Start (F5).",
    "Compare train lists": "Start (F5).",
    # ---------------------------------------------------------------- Live View
    "Compare:": "What to compare - any comparison the other tabs can do.",
    "Compare": "Compare the files and list every train (F5).",
    "Refresh when a file is saved": "Watch the files: when one is saved, compare again within a moment and "
                                    "mark the trains that changed.",
    "Show:": "Which trains to list.",
    "Find:": "Show only trains whose section, headcode or status contains this text.",
    "Days:": "Untick days to show only the trains running on the ticked days.",
    "< Previous difference": "Go to the previous train with differences (Shift+F3).",
    "Next difference >": "Go to the next train with differences (F3).",
    "Export...": "Save the trains listed (with the current filter and search) and their differences to "
                 "Excel, PDF or Word.",
    # ---------------------------------------------------------------- more Stats Pack
    "Comparisons:": "Options for comparisons of two plans or two stats packs.",
    "miles": "Mileage threshold for flagging increases.",
    "One workbook: totals for the selected days, then every day's tabs": "One workbook with weekly totals first, "
                                                                         "followed by each day's own tabs.",
    "One workbook: totals for the selected days only": "One workbook with the totals for the ticked days only.",
    "A separate workbook for each day": "One workbook per ticked day.",
    # ---------------------------------------------------------------- menu bar
    "Options": "Theme, updates, notifications, fleet data and the depot list (Alt+O).",
    "Save/Load": "Save the current tab's files and options under a name (as many as you like on each tab), "
                 "and load or run them again later (Alt+S).",
    "Help": "User guide, keyboard shortcuts and version (Alt+H).",
}


def lookup(text: str) -> Optional[str]:
    key = " ".join(str(text or "").split())
    if key in TIPS:
        return TIPS[key]
    if key in _DAYS:
        return f"Include trains running on {_DAYS[key]}s."
    if re.fullmatch(r"\d{3}/\d", key):
        return f"Class {key}: include its diagrams. Untick to leave this fleet out."
    m = re.fullmatch(r"([A-Z]{3,5}) \(([^)]*)\)", key)
    if m:
        return f"Include the fleets of {m.group(1)} (depots {m.group(2)}). Untick to leave them all out."
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
