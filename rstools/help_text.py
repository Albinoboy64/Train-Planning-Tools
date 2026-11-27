"""Help shown when the mouse rests on a control, keyed by the control's own text (so it follows labels
that change with the chosen mode). Input boxes take the help of the label to their left."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from .widgets import TaskBox, Tooltip

TIPS = {
    # ---------------------------------------------------------------- shared
    "Add...": "Add files to this box. Files already in it are kept, so files from different folders can be used "
              "together.",
    "Leave out trains only in the first file (the original or reference)": "Leave out trains (or rows) found "
        "only in the first file, e.g. when a print covers only part of a timetable. Trains only in the second "
        "file are still shown.",
    "Check for differences (untick to pair trains for checking by eye)": "Untick to switch error checking off: "
        "each train is put side by side with its match for checking by eye, with nothing coloured or flagged. "
        "Trains found in only one file are still listed, so nothing is missed.",
    "Save to folder:": "Where the output is saved, on this PC (never a network or shared drive). Leave blank "
                       "to save it to your Downloads folder.",
    "Output name:": "File name for the output, without the extension. Leave blank to use the name shown "
                    "underneath. An existing file is never overwritten: (2), (3)... is added instead.",
    "Save as:": "Excel keeps colours, filters and frozen headings. PDF and Word are for printing or sending "
                "on.",
    "Task:": "What to do. The boxes below change to suit the task.",
    # ---------------------------------------------------------------- Stock Tools
    "Compare two CWNs or platform workings": "Compare an original and an updated CWN (or platform workings): a "
        "copy of the updated file with every change highlighted and noted, and a change report.",
    "Add a new round to an earlier comparison": "Compare a newer CWN with a comparison CWN made earlier by this "
                                                    "app. The earlier highlights are kept and the new round is "
                                                    "shown in another colour.",
    "Compare two folders of CWNs or workings (batch)": "Compare every CWN in one folder with its partner in "
                                                       "another folder (paired by file name).",
    "CWN:": "The multi-day CWN. It is not changed - a copy is saved.",
    "GTR VPT (optional):": "A VPT of the same timetable: its running lines settle clashes where "
        "only some lines are blocked.",
    "Other operators (optional; VPT preferred, or F3 print):": "Other operators' trains, checked too. A VPT export "
        "is preferred; an Attune Single Train Report (F3) print, PDF or Word, also works (its Line column gives the "
        "running lines).",
    "Check an Attune XML against Section 4 possessions": "Check the Attune XML against the "
        "Engineering Access Statement Section 4: every train running through a section during one of its "
        "possessions.",
    "Section 4 PDF(s):": "The Section 4 PDFs, one per route, e.g. Kent & Sussex, East Coast, East Midlands. Leave "
                         "blank to use the rule set in use: the built-in 2027 EAS v4 rules, or a newer set added "
                         "in Settings > Rules.",
    "Create a station working book from an Attune XML (TRACS-RS layout)": "One sheet each for SX, SO and Su. Needs an "
        "Attune XML with every day's unit diagrams.",
    "Station:": "The station, as named in the XML. Type to see matching stations.",
    "Platforms (optional):": "Only trains leaving from these platforms, e.g. 10-15 for London Bridge low level, "
                             "or 1, 2, 4A. Leave blank for every platform.",
    "Operator:": "Whose trains the book has, and its page header, file name and sheet names: TLGN (Thameslink and "
                 "Great Northern), SNGX (Southern and Gatwick Express) or All GTR. Each train's operator comes from "
                 "the depot of the unit diagrams working it (SNGX: BI, SU, SL; TLGN: HE, TB).",
    "Timetable:": "For the page header and file name, e.g. Dec23. Filled in from the XML's start date.",
    "Services (blank: the operator's):": "For the page header. Blank: the operator's, e.g. 'Thameslink and Great "
                                         "Northern services only' or 'Southern and Gatwick Express services only'.",
    "Other operators (XML preferred; VPT or F3 print):": "Other operators' trains at the station, merged into the "
        "book and marked with their operator. Attune XML is preferred (it gives the stock); a VPT export or an "
        "Attune Single Train Report (F3) print, PDF or Word, also works but the stock is blank.",
    "Other operators shown:": "Tick which of the other operators found in those files are shown in the book.",
    "Sheet name:": "The start of each sheet's name, before SX / SO / Su. Blank: the station and operator, e.g. "
                   "'London Kings Cross (TLGN)'.",
    "SX": "A sheet for Monday to Friday. Trains that differ by day get a row for each version, marked e.g. "
          "'Runs Monday and Friday only'.",
    "By first day run - MO first, then TO, WO, ThO, FO (then SO, Su)":
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
    "Output type:": "Full CWN with changes highlighted and noted: the whole updated CWN with changes "
                    "highlighted, previous values struck through and notes added. New or changed items "
                    "highlighted only: without the previous values. ACWN: only the amended trains.",
    "Colour for new amendments:": "Colour for this round's changes - choose one not used by earlier rounds.",
    "Create change report as": "Also write a change report listing every change by type, location and train.",
    "Days to check:": "Untick days to check and output only the trains running on the ticked days. Days the "
                      "chosen CWNs do not cover are greyed out.",
    "Reset to defaults": "Switch every change type back on.",
    "Highlight only (no previous values)": "Mark changes without showing the previous values struck through.",
    # ---------------------------------------------------------------- berthing charts
    "Create a berthing chart from an Attune XML": "Where each unit berths every night at the out-berth platforms and "
        "sidings: SNGX in the built-in layout (or like a chart you choose), TLGN laid out from the XML. A new chart "
        "has no highlights.",
    "Add a round of changes to a berthing chart": "Remakes the chart from the updated XML. Cells that differ from the "
        "original XML are filled in the chosen colour; earlier highlights are kept.",
    "Compare two berthing charts": "Highlights in the updated chart every unit or time that differs from the original. "
        "Spacing slips and the old 'L' marker do not count.",
    "STP XML (optional):": "For an STP chart: each day's STP diagrams replace the LTP ones, and STP trains are shown "
                           "in bold on lavender.",
    "Layout from chart (optional):": "Leave blank to use the app's built-in layout (from the Dec 26 Proof 2 chart). "
                                     "Or choose an earlier berthing chart: its sheets, berths, capacities and notes "
                                     "are kept and the units come from the XML.",
    "Berthing chart:": "The chart to add this round's changes to.",
    "Original XML:": "The XML the chart was made from. For an STP chart: the LTP and STP XMLs, separated by ';'.",
    "Updated XML:": "The changed XML. For an STP chart: the LTP and STP XMLs, separated by ';'.",
    "Original chart:": "The earlier berthing chart.",
    "Updated chart:": "The newer berthing chart: the differences are highlighted in a copy of it.",
    "Issue on cover:": "The line under the cover's title (the timetable, e.g. December 2026 Berthing Chart): pick a "
                       "proof or Final, or type your own. Blank: none on a new chart; a round keeps the chart's own.",
    "Chart for:": "SNGX: the built-in layout. TLGN: a sheet for every place TLGN units berth overnight in the XML "
                  "(not depots), TLGN units only.",
    "Choose locations...": "Leave sheets off the chart, or add any location units berth at in the XML (found for "
                           "you, or typed by name or TIPLOC).",
    "Add other operators' trains to a CWN or platform workings": "Other operators' trains (from their Attune XML, a "
        "VPT or a Network Rail CIF) added in time order in grey italics, the operator code as the stock. Existing rows "
        "are not changed.",
    "Other operators (optional):": "Other operators' files: Attune XML, VPT or Network Rail CIF (use Browse to add "
                                   "several). Without next-day workings or unit types, units are matched by place "
                                   "and shown by headcode (chart) or operator code (workings).",
    "Other operators' files:": "Attune XML, VPT or Network Rail CIF files of the other operators (use Browse to add "
                               "several).",
    "CWN or platform workings:": "The CWN or platform workings to add the other operators' trains to (a copy is "
                                 "saved).",
    "Show location notes on the chart": "The notes about each location (e.g. 'Max 12 CET'), with any changed for "
                                        "the XML's timetable in Settings > Berthing notes. Untick to leave every "
                                        "note off.",
    "Edit notes...": "Settings > Berthing notes: change, add or remove the notes of each location for the current "
                     "and next five timetables.",
    "Make from XML...": "Find every place the chart's units berth overnight in an Attune XML (not depots), with a "
                        "berth for each platform or road used; check the rows, add capacities, then Save.",
    "Back to default": "Forget your saved locations: SNGX goes back to the app's built-in list, TLGN to taking its "
                       "locations from each XML.",
    "Open berth list in Excel": "The list that links each SNGX berth to its TIPLOC and platform or road codes, for "
                                "big changes.",
    "Open in Excel": "Open this list in Excel for big changes; the rows are read again when you come back.",
    "Back to built-in": "Put back the app's built-in rows (press Save to keep them).",
    "Berthing locations...": "Settings > Berthing locations: the sheets and berths each chart starts from (SNGX, "
                             "or TLGN's set made from an XML), their capacities, TIPLOCs and platform codes.",
    "Create a stats pack": "Build the rolling stock stats pack for the chosen days from an Attune XML and its "
                           "TRENT diagram print.",
    "Compare two plans (two sets of XML + TRENT print)": "Build stats packs for two plans and show every "
                                                          "difference (mileage, units, formations, times...).",
    "Compare two stats pack files": "Compare two stats pack workbooks made earlier (by this app or TRACS-RS).",
    "Fuel check (171s)": "Follow each diesel unit (171/7, 171/8) through the week and check it is fuelled at least "
                         "every 48 hours; units that are not are listed first. Always covers the ticked days "
                         "together, even when 'Show each day separately' is chosen.",
    "Several stations:": "Make a book for each of several stations in one run. Pick a "
                         "station (and platforms) and press Add to list, or type them separated by ';' with "
                         "platforms in brackets, e.g. London Kings Cross; London Bridge [10-15]; Cambridge.",
    "Attune XML (optional):": "The Attune diagram export (.xml) of the plan. Unit reports can be made from the "
                              "TRENT print alone: the XML adds next-day workings for SNGX diagrams.",
    "TRENT VL29 print(s):": "The TRENT VehicleLayout29 print (saved as Word), from the same plan as the XML. "
                            "Several prints can go in this box, e.g. the LTP print and a week's STP print.",
    "Each ticked day on its own": "Report each ticked day separately, with no week total.",
    "Show each day separately": "Report each ticked day separately: units are not followed from one day to "
                                "the next.",
    "Create unit reports: washes and CETs, depot returns / swaps, captive units, fuel": "Reports on how the "
        "units are used: where they are washed and CET'd, depot returns and swaps, captive units and diesel "
        "fuelling. Made from the TRENT print; the XML adds next-day workings.",
    "Create a capacity report: by headcode group, corridor or station to station": "Seating capacity and / or standing "
        "room of every passenger train in a headcode group, on a corridor or between two stations, per day or for "
        "the week, optionally only trains at a station between two times. From the fleet data.",
    "Standing room": "Show standing capacity. With both ticked, total capacity (seats + standing) is shown too.",
    "Headcode group:": "Count the trains of one headcode group: pick from the list or type one, e.g. 1F or 9T.",
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
    "Fleet data...": "Settings > Fleet data: each unit type's operator, seats, vehicles per unit, fleet size and "
                     "unit length.",
    # ---------------------------------------------------------------- Timing Tools
    "Check the GTR timetable against the Network Rail timetable": "Check the GTR timetable against the Network Rail "
                                                         "timetable (the reference). Output: the Consolidated "
                                                         "TT Comparison workbook.",
    "Check a timetable against train prints (Attune Single Train Report)": "Use Attune 'Single Train Report' prints as "
                                                                      "the reference and check a timetable "
                                                                      "against their public times.",
    "Check a timetable against an Attune train list": "Use an Attune train list as the reference and check "
                                                      "each train's origin departure and destination arrival "
                                                      "in a timetable.",
    "GTR timetable:": "The GTR timetable check workbook (sheets such as 'OT SNGX TT Checks K - OUT SX').",
    "Network Rail timetable:": "The Network Rail timetable workbook - the reference.",
    "Attune train list - reference:": "The Attune train list export (Excel or CSV).",
    "Timetable to check:": "The timetable workbook to check (GTR or Network Rail layout).",
    # ---------------------------------------------------------------- Live View
    "Compare two sets of train prints (PDF or Word) or Attune VPT exports": "Compare two versions of the same "
        "trains location by location: times, platforms, lines and activities.",
    "Compare two Attune train list exports (Excel or CSV)": "Compare two Attune train lists column by column, "
        "train by train.",
    "Compare two sets of Section 4 documents (PDF)": "Compare two issues of Network Rail's Section 4 possession "
        "tables: every possession's times, dates, places, lines blocked and remarks.",
    "Compare two sets of Timetable Planning Rules (PDF)": "Compare two issues of the Timetable Planning Rules: "
        "every table row and paragraph.",
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
            if isinstance(source, TaskBox):          # a task list: the help of the task chosen
                self.text = lookup(source.get()) or ""
            else:
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
        if isinstance(w, TaskBox):
            w._has_tip = True
            _TextTip(w, w)
        elif isinstance(w, _LABELLED):
            w._has_tip = True
            _TextTip(w, w)
        elif isinstance(w, _INPUTS):                # the label is found when shown (rows move with the mode)
            w._has_tip = True
            _TextTip(w, None)
        if isinstance(w, ttk.Combobox):             # no tip over its own drop-down list
            from rstools.widgets import guard_popdown
            guard_popdown(w)


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
