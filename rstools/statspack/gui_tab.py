"""'Stats Pack' tab of the Train Planning Tools window."""
from __future__ import annotations

import json
import os
import queue
import time
import tkinter as tk
from functools import partial
from typing import Dict, List, Tuple
from collections import Counter
from tkinter import ttk, filedialog, messagebox

from rstools import errorlog, theme
from rstools.autocomplete import Suggest
from rstools.widgets import FAILED, READY, STOPPED, Progress, TaskBox, Tooltip, day_buttons, debounce, \
    Placeholder, duration, local_folder_box, log_box
from rstools.branding import APP_NAME
from rstools.naming import file_label, plural
from rstools.fsutil import write_json

from rstools.days import DAYS, DAY_NAMES
from .engine import (OUTPUTS, PackOptions, PlanInputs, StatsPackError, build_pack, cached, compare_packs,
                     compare_plans, day_availability, load_plan, pack_name, packs_name, plans_name, seats_name,
                     seats_report, timetable, UNIT_REPORTS, unit_reports, write_pack)
from .compare import CompareOptions
from .fleet import FleetTable, user_fleet_path
from .model import OPERATOR_DEPOTS, OPERATORS, OTHER, operator_of
from .seats import shown

TITLE = f"{APP_NAME} - Stats Pack"
EXT = {"xml": ".xml", "trent": ".docx", "pack": ".xlsx"}
FILETYPES = {"xml": [("Attune diagram XML", "*.xml"), ("All files", "*.*")],
             "trent": [("TRENT VehicleLayout29 print (Word)", "*.docx"), ("All files", "*.*")],
             "pack": [("Stats pack (Excel)", "*.xlsx"), ("All files", "*.*")]}
MODES = {"create": ("Create a stats pack", "Create stats pack"),
         "plans": ("Compare two plans (two sets of XML + TRENT print)", "Compare plans"),
         "packs": ("Compare two stats pack files", "Compare stats packs"),
         "mileage": ("Create mileage for a period: the whole timetable, one month or any dates", "Create mileage"),
         "units": ("Create unit reports: washes and CETs, depot returns / swaps, captive units, fuel",
                   "Create unit reports"),
         "seats": ("Create a capacity report: by headcode group, corridor or station to station",
                   "Create capacity report")}
TASK_GROUPS = [("Stats packs", [(m, MODES[m][0]) for m in ("create", "mileage", "plans", "packs")]),  # Task list
               ("Reports", [(m, MODES[m][0]) for m in ("units", "seats")])]
FILES = {"create": [("xml_a", "Attune XML:"), ("trent_a", "TRENT VL29 print(s):")],
         "plans": [("xml_a", "Original Attune XML:"), ("trent_a", "Original TRENT VL29 print(s):"),
                   ("xml_b", "Updated Attune XML:"), ("trent_b", "Updated TRENT VL29 print(s):")],
         "packs": [("pack_a", "Original stats pack:"), ("pack_b", "Updated stats pack:")],
         "mileage": [("xml_a", "Attune XML:"), ("trent_a", "TRENT VL29 print(s):")],
         "units": [("xml_a", "Attune XML (optional):"), ("trent_a", "TRENT VL29 print(s):")],
         "seats": [("xml_a", "Attune XML:"), ("trent_a", "TRENT VL29 print(s):")]}
MILEAGE_PERIODS = (("timetable", "Whole timetable"), ("month", "One month:"), ("custom", "From:"))
UNIT_POSSIBLE = (("every", "Every unit"), ("over", "Only units overdue for it"), ("off", "Off"))
UNIT_PERIODS = (("week", "Whole week (follows each unit with the next-day workings)"),
                ("days", "Show each day separately"),
                ("timetable", "Entire timetable (totals by fleet only)"))
OPTIONAL = {("units", "xml_a")}         # boxes that may be left blank
OP_LABEL = {op: f"{op} ({', '.join(deps)})" for op, deps in OPERATOR_DEPOTS.items()}
OP_LABEL[OTHER] = "Other depots"
FLEET_COLS = 6


def _mtime(path: str):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _version() -> str:
    try:
        from cwn_compare import __version__
        return __version__
    except Exception:
        return ""


def _settings_path() -> str:
    return os.path.join(os.path.dirname(user_fleet_path()), "statspack.json")


def files_for(mode: str, two_plans: bool):
    """The file boxes a mode needs: unit and capacity reports take a second timetable to compare with."""
    return FILES["plans"] if two_plans and mode in ("units", "seats") else FILES[mode]


def _kind(key: str) -> str:
    return key.split("_")[0]


def _split(text: str):
    """The files in one box (several TRENT prints are separated by ';')."""
    return [p.strip().strip('"') for p in (text or "").split(";") if p.strip().strip('"')]


class StatsPackTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(12, 8, 12, 10))
        self.app = app
        from rstools.cancel import StopQueue
        self.q: "queue.Queue" = StopQueue()
        self.running = False
        self.outputs = []
        self.fleet_vars = {}
        self.fleet_info = {}            # fleet -> (operator, in the print?)
        self.print_days = None          # days in the TRENT print(s) / XML(s), once read
        self.xml_days = None
        self._tokens = Counter()
        self._started = 0.0
        self._dnd = ""                  # tkdnd file type, once drag and drop is available
        self._last_dir = ""
        self._saved_fleets = {}
        self._prints = []               # TRENT print(s) read for the chosen files (for the name preview)
        self._build()
        self._load_settings()
        self._mode_changed()
        app.pump.add(self.q, self._poll, lambda: self.running)

    # ------------------------------------------------------------------ UI
    def _build(self):
        self.columnconfigure(0, weight=1, minsize=520)
        self.columnconfigure(1, weight=1, minsize=470)
        self.rowconfigure(2, weight=1)
        left, right = ttk.Frame(self), ttk.Frame(self)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=2, column=1, sticky="nsew")
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # the task: one drop-down; only what the chosen task needs is shown below it
        self.mode = tk.StringVar(value="create")
        task = ttk.Frame(left)
        task.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        task.columnconfigure(1, weight=1)
        ttk.Label(task, text="Task:", font="AppBold").grid(row=0, column=0, padx=(0, 6))
        self.task_box = TaskBox(task, TASK_GROUPS)
        self.task_box.grid(row=0, column=1, sticky="ew")
        self.task_box.bind("<<ComboboxSelected>>", self._task_picked)
        self.mode.trace_add("write", lambda *_a: self._task_shown())
        self._task_shown()                      # the task chosen at the start is shown in the box
        opt = self.opt_frame = ttk.LabelFrame(left, text="2. Options", padding=8)
        opt.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        uf = self.units_frame = ttk.Frame(opt)
        uf.grid(row=0, column=0, sticky="w")
        self.unit_vars = {k: tk.BooleanVar(value=True) for k in UNIT_REPORTS}
        for i, (key, text) in enumerate((("washes", "Washes"), ("cets", "CETs"), ("fuel", "Fuel check (171s)"),
                                         ("depots", "Depot returns / swaps"), ("captive", "Captive units"))):
            ttk.Checkbutton(uf, text=text, variable=self.unit_vars[key]).grid(row=i // 3, column=i % 3, sticky="w",
                                                                            padx=(0, 10))
        self.unit_possible = tk.StringVar(value="every")
        ttk.Label(uf, text="Show where a wash, CET or fuel could be added:").grid(row=2, column=0, columnspan=2,
                                                                                    sticky="w", pady=(4, 0))
        self.possible_box = ttk.Combobox(uf, state="readonly", width=22, values=[t for _v, t in UNIT_POSSIBLE])
        self.possible_box.grid(row=2, column=2, sticky="w", pady=(4, 0))
        self.possible_box.set(dict(UNIT_POSSIBLE)["every"])
        self.possible_box.bind("<<ComboboxSelected>>", lambda _e: self.unit_possible.set(
            next(v for v, t in UNIT_POSSIBLE if t == self.possible_box.get())))
        Tooltip(self.possible_box, "Adds a 'Could be added at' note to each unit, and a tab listing stops long "
                                   "enough for a wash, CET or fuel at places where the TRENT print does them but "
                                   "this unit does not. 'Only units overdue for it': units past the wash, CET or "
                                   "fuel limit. Whole-week reports only.")
        self.two_plans = tk.BooleanVar(value=False)         # unit / capacity reports: compare two timetables
        self.unit_period = tk.StringVar(value="week")
        for r, (value, text) in enumerate(UNIT_PERIODS, start=3):
            ttk.Radiobutton(uf, text=text, variable=self.unit_period, value=value).grid(
                row=r, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(uf, text="Compare two timetables (original and updated XML + TRENT print)",
                        variable=self.two_plans, command=self._mode_changed).grid(row=6, column=0, columnspan=3,
                                                                                  sticky="w", pady=(2, 0))
        self._build_seats(opt, 1)
        self._build_mileage(opt, 2)

        # 1. input
        ff = self.in_frame = ttk.LabelFrame(left, text="1. Input", padding=8)
        opt.lift(ff)                    # the Tab key goes through Input before Options, as they are shown
        ff.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ff.columnconfigure(1, weight=1)
        self.vars = {k: tk.StringVar() for k in ("xml_a", "trent_a", "xml_b", "trent_b", "pack_a", "pack_b")}
        self.file_rows = {}
        for r, key in enumerate(self.vars):
            lab = ttk.Label(ff, text="")
            ent = self.app.file_box(ff, self.vars[key], _kind(key))
            btn = ttk.Button(ff, text="Browse...", command=lambda k=key: self._browse(k))
            lab.grid(row=r, column=0, sticky="w", pady=2)
            ent.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
            btn.grid(row=r, column=2, pady=2)
            self.file_rows[key] = (lab, ent, btn)
            if _kind(key) == "trent":                   # a box that can hold several prints can be emptied
                clear = ttk.Button(ff, text="Clear", width=6, command=lambda v=self.vars[key]: v.set(""))
                clear.grid(row=r, column=3, padx=(4, 0), pady=2)
                self.file_rows[key] += (clear,)
            self.vars[key].trace_add("write", lambda *_a, k=key: self._file_changed(k))

        # 3. output
        of = self.out_frame = ttk.LabelFrame(left, text="3. Output", padding=8)
        of.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        of.columnconfigure(1, weight=1)
        self.output = tk.StringVar(value="totals_days")
        self.output_radios = []
        for i, (val, text) in enumerate(OUTPUTS.items()):
            rb = ttk.Radiobutton(of, text=text, variable=self.output, value=val)
            rb.grid(row=i, column=0, columnspan=3, sticky="w")
            self.output_radios.append(rb)
        self.one_day_note = ttk.Label(of, text="With one day ticked, a single-day stats pack is made.",
                                      style="Small.TLabel")
        self.one_day_note.grid(row=3, column=0, columnspan=3, sticky="w")
        self.cmp_frame = cf = ttk.Frame(of)
        cf.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(cf, text="Comparisons:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.cmp_vars = {"summary": tk.BooleanVar(value=True), "changed_tabs_only": tk.BooleanVar(value=False),
                         "changed_rows_only": tk.BooleanVar(value=False)}
        for i, (key, text) in enumerate((("summary", "Summary of key figures"),
                                         ("changed_tabs_only", "Changed tabs only"),
                                         ("changed_rows_only", "Changed rows only"))):
            ttk.Checkbutton(cf, text=text, variable=self.cmp_vars[key]).grid(row=0, column=i + 1, padx=(0, 10))
        flag = ttk.Frame(cf)
        flag.grid(row=1, column=1, columnspan=3, sticky="w", pady=(3, 0))
        self.flag_var = tk.BooleanVar(value=True)
        self.flag_miles = tk.StringVar(value="10")
        flag_spin = ttk.Spinbox(flag, from_=0.5, to=9999, increment=5, width=6, textvariable=self.flag_miles)
        ttk.Checkbutton(flag, text="Flag mileage increases over", variable=self.flag_var).grid(row=0, column=0)
        flag_spin.grid(row=0, column=1, padx=4)
        flag_spin.lift()                                     # after the tick box for the Tab key
        self.flag_var.trace_add("write", lambda *_a: flag_spin.state(            # greyed when not flagging
            ["!disabled"] if self.flag_var.get() else ["disabled"]))
        ttk.Label(flag, text="miles").grid(row=0, column=2)
        ttk.Label(of, text="Save to folder:").grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.out_dir = tk.StringVar()
        out_box = local_folder_box(ttk.Entry(of, textvariable=self.out_dir), self.out_dir)
        out_box.grid(row=5, column=1, sticky="ew", padx=4, pady=(6, 0))
        Placeholder(out_box, "Downloads")
        ttk.Button(of, text="Browse...", command=self._browse_dir).grid(row=5, column=2, pady=(6, 0))
        ttk.Label(of, text="Output name:").grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.out_name = tk.StringVar()
        name_box = ttk.Entry(of, textvariable=self.out_name)
        name_box.grid(row=6, column=1, sticky="ew", padx=4, pady=(6, 0))
        self.name_hint = Placeholder(name_box)          # the name the output gets if the box is left blank
        fmtf = ttk.Frame(of)
        fmtf.grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(fmtf, text="Save as:").grid(row=0, column=0, padx=(0, 6))
        self.fmt_var = tk.StringVar(value="xlsx")
        for i, (key, text) in enumerate((("xlsx", "Excel"), ("pdf", "PDF"), ("docx", "Word"))):
            ttk.Radiobutton(fmtf, text=text, variable=self.fmt_var, value=key,
                            command=self._fmt_changed).grid(row=0, column=i + 1, padx=(0, 10))
        self.fmt_hint = theme.collapse_empty(ttk.Label(of, text="", style="Small.TLabel", wraplength=480,
                                                       justify="left"))
        self.fmt_hint.grid(row=9, column=0, columnspan=3, sticky="w")

        # 4. selection
        sel = self.sel_frame = ttk.LabelFrame(right, text="4. Days, operators and fleets", padding=8)
        sel.grid(row=0, column=0, sticky="nsew")
        sel.columnconfigure(0, weight=1)
        ttk.Label(sel, text="Diagram days:").grid(row=0, column=0, sticky="w")
        dayf = ttk.Frame(sel)
        dayf.grid(row=1, column=0, sticky="w")
        self.day_vars = []
        self.day_widgets: List[ttk.Widget] = []
        for i, _code in enumerate(DAYS):
            v = tk.BooleanVar(value=True)
            cb = ttk.Checkbutton(dayf, text=DAY_NAMES[i][:3], variable=v, command=self._days_changed)
            cb.grid(row=0, column=i, padx=(0, 8))
            self.day_vars.append(v)
            self.day_widgets.append(cb)
        self.day_widgets += day_buttons(sel, self._set_days, row=2, column=0, sticky="w", pady=(4, 0))
        self.day_note = ttk.Label(sel, text="", style="Warn.TLabel", wraplength=440, justify="left")
        self.day_note.grid(row=3, column=0, sticky="w", pady=(2, 0))

        ttk.Label(sel, text="Operators and fleets:").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.op_vars = {op: tk.BooleanVar(value=True) for op in OPERATORS}
        self.fleet_frame = ttk.Frame(sel)
        self.fleet_frame.grid(row=5, column=0, sticky="w")
        fb = ttk.Frame(sel)
        fb.grid(row=6, column=0, sticky="w", pady=(4, 0))
        ttk.Button(fb, text="All fleets", command=lambda: self._set_fleets(True)).grid(row=0, column=0)
        ttk.Button(fb, text="None", command=lambda: self._set_fleets(False)).grid(row=0, column=1, padx=4)
        ttk.Button(fb, text="Fleet data...", command=self.edit_fleet).grid(
            row=0, column=2, padx=(12, 0))
        self.fleet_note = theme.collapse_empty(ttk.Label(sel, text="", style="Small.TLabel", wraplength=440,
                                                         justify="left"))
        self.fleet_note.grid(row=7, column=0, sticky="w", pady=(4, 0))

        # 5. run
        rf = self.run_frame = ttk.LabelFrame(right, text="5. Run", padding=8)
        rf.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(2, weight=1)
        top = ttk.Frame(rf)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.run_btn = ttk.Button(top, text="Create stats pack", style="Run.TButton", command=self.run)
        self.run_btn.grid(row=0, column=0)
        self.prog = ttk.Progressbar(top, mode="determinate", maximum=1.0)
        self.prog.grid(row=0, column=1, sticky="ew", padx=8)
        self.stop_btn = ttk.Button(top, text="Stop", command=self.stop_run, state="disabled")
        self.stop_btn.grid(row=0, column=2)
        Tooltip(self.stop_btn, "Stop the run (Esc). Nothing is saved from a stopped run.")
        self.status = ttk.Label(rf, text=READY, style="Small.TLabel")
        self.status.grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.progress = Progress(self.prog, self.status)
        self.log = log_box(rf, row=2, column=0, sticky="nsew")
        ob = ttk.Frame(rf)
        ob.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.open_btn = ttk.Button(ob, text="Open output", state="disabled", command=self._open_outputs)
        self.open_btn.grid(row=0, column=0)
        self.dir_btn = ttk.Button(ob, text="Open folder", state="disabled",
                                  command=lambda: self.app.open_outputs([os.path.dirname(self.outputs[0])], force=True))
        self.dir_btn.grid(row=0, column=1, padx=6)
        ttk.Checkbutton(ob, text="Open when finished", variable=self.app.open_var).grid(row=0, column=2,
                                                                                      padx=(12, 0))
        self._show_fleets()

    # ---------------------------------------------------- drag and drop
    def enable_drag_and_drop(self, dnd_files: str):
        """Called by the window once tkdnd is loaded: drop files on a box, or anywhere on the tab."""
        self._dnd = dnd_files
        self._add_drop_target(self)

    def _add_drop_target(self, widget):
        if not self._dnd or isinstance(widget, tk.Text):
            return
        entry_key = next((k for k, row in self.file_rows.items() if widget in row), None)    # a box's whole row
        try:
            widget.drop_target_register(self._dnd)
            widget.dnd_bind("<<Drop>>", lambda e, k=entry_key: self._on_drop(e, k))
        except (tk.TclError, AttributeError):
            return
        for child in widget.winfo_children():
            self._add_drop_target(child)

    def _on_drop(self, event, key=None):
        paths = [os.path.normpath(p) for p in self.tk.splitlist(event.data) if os.path.isfile(p)]
        by_kind = {k: [p for p in paths if p.lower().endswith(ext)] for k, ext in EXT.items()}
        if not any(by_kind.values()):
            messagebox.showwarning(TITLE, "Drop an Attune XML (.xml), a TRENT unit diagram print (.docx) "
                                          "or stats packs (.xlsx).", parent=self)
            return event.action
        if key and paths and all(p.lower().endswith(EXT[_kind(key)]) for p in paths):
            if len(paths) == 1 or _kind(key) == "trent":   # dropped on its own box (prints: all of them)
                self.vars[key].set(" ; ".join(paths))
                return event.action
        mode = self.mode.get()
        if by_kind["pack"] and not by_kind["xml"] and not by_kind["trent"]:
            mode = "packs"
        elif len(by_kind["xml"]) > 1:
            mode = "plans"
        elif mode == "packs":
            mode = "create"                         # plan files dropped while comparing packs
        if mode != self.mode.get():
            self.mode.set(mode)
            self._mode_changed()
        from rstools.dropping import Slot, route_drop
        for kind, files in by_kind.items():
            keys = [k for k, _l in files_for(mode, self.two_plans.get()) if _kind(k) == kind]
            if not files or not keys:
                continue
            if kind == "trent" and (len(keys) == 1 or len(by_kind["xml"]) < 2) and len(files) > 1:
                self.vars[keys[0]].set(" ; ".join(files))    # several prints read as one (TLGN SX/SO/SU)
                continue
            slots = [Slot(self.vars[k], lambda p, e=EXT[kind]: p.lower().endswith(e)) for k in keys]
            route_drop(files, slots)
        return event.action

    def _build_mileage(self, parent, row):
        """Mileage for a period: the whole timetable, a month of it, or from one date to another."""
        mf = self.mileage_frame = ttk.Frame(parent)
        mf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.mileage_kind = tk.StringVar(value="timetable")
        self.mileage_month = tk.StringVar()
        self.mileage_from, self.mileage_to = tk.StringVar(), tk.StringVar()
        ttk.Label(mf, text="Add up the mileage tabs over:").grid(row=0, column=0, columnspan=4, sticky="w")
        for r, (value, text) in enumerate(MILEAGE_PERIODS, start=1):
            ttk.Radiobutton(mf, text=text, variable=self.mileage_kind, value=value,
                            command=self._update_name_hint).grid(row=r, column=0, sticky="w")
        self.month_box = ttk.Combobox(mf, textvariable=self.mileage_month, width=18, values=[])
        self.month_box.grid(row=2, column=1, columnspan=3, sticky="w", padx=4)
        Tooltip(self.month_box, "A month of the timetable (from the TRENT print), or type one, e.g. January 2027. "
                                "A month the timetable starts or ends in is cut to the timetable's dates.")
        ent_from = ttk.Entry(mf, textvariable=self.mileage_from, width=12)
        ent_from.grid(row=3, column=1, sticky="w", padx=4)
        ttk.Label(mf, text="to").grid(row=3, column=2, sticky="w")
        ent_to = ttk.Entry(mf, textvariable=self.mileage_to, width=12)
        ent_to.grid(row=3, column=3, sticky="w", padx=4)
        for ent in (ent_from, ent_to):
            Tooltip(ent, "Dates as DD/MM/YYYY, e.g. 01/02/2027 to 28/02/2027.")
        for var, kind in ((self.mileage_month, "month"), (self.mileage_from, "custom"), (self.mileage_to, "custom")):
            var.trace_add("write", lambda *_a, k=kind: (self.mileage_kind.set(k), self._update_name_hint()))
        theme.tip(ttk.Label(mf, text="Each date counts the diagrams that run on it (from the TRENT print's dates), "
                                     "with STP and draft diagrams only on the dates they are valid for; the days "
                                     "ticked below are not used. The workbook has Mileage by Date and each mileage "
                                     "tab added up.", style="Small.TLabel", wraplength=470, justify="left"),
                  "About the period").grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))

    def _fill_months(self):
        from .period import months
        values = months(self._prints[0]) if self._prints else []
        self.month_box.configure(values=values)

    def _build_seats(self, parent, row):
        """Capacity report options: which trains (headcode group, corridor and direction, or station to station),
        day / week, an optional time window, and comparing two timetables."""
        from .seats import DIRECTIONS, JOURNEY
        sf = self.seats_frame = ttk.Frame(parent)
        sf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        sf.columnconfigure(1, weight=1)
        self.seat_kind = tk.StringVar(value="Service group")
        self.seat_group = {"Service group": tk.StringVar(), "Corridor": tk.StringVar()}
        self.seat_boxes = {}
        labels = {"Service group": "Headcode group:", "Corridor": "Corridor:"}
        for r, kind in enumerate(("Service group", "Corridor")):
            ttk.Radiobutton(sf, text=labels[kind], variable=self.seat_kind, value=kind,
                            command=self._seat_kind_changed).grid(row=2 * r, column=0, sticky="w")
            box = ttk.Combobox(sf, textvariable=self.seat_group[kind], width=30,     # pick or type
                               style="Suggest.TCombobox")
            box.grid(row=2 * r, column=1, sticky="ew", padx=(4, 0), pady=1)
            pick = (lambda _v=None, k=kind: (self.seat_kind.set(k), self._seat_kind_changed()))
            box.bind("<<ComboboxSelected>>", lambda _e, f=pick: f())
            box.bind("<Key>", lambda e, f=pick: f() if e.char and e.char.isprintable() else None, add="+")
            Suggest(box, lambda b=box: b.cget("values"), pick)
            self.seat_boxes[kind] = box
        self.seat_group_note = theme.collapse_empty(ttk.Label(sf, text="", style="Small.TLabel", wraplength=440,
                                                              justify="left"))
        self.seat_group_note.grid(row=1, column=1, sticky="w", padx=(4, 0))
        self.corridor_dir = tk.StringVar(value="both")
        self.corridor_dir_box = cdf = ttk.Frame(sf)               # which way along the corridor
        cdf.grid(row=3, column=1, sticky="w", padx=(4, 0), pady=1)
        self.corridor_dir_radios = {}
        for i, k in enumerate(("forward", "reverse", "both")):
            rb = ttk.Radiobutton(cdf, text=k, variable=self.corridor_dir, value=k,
                                 command=lambda: (self.seat_kind.set("Corridor"), self._seat_kind_changed()))
            rb.grid(row=0, column=i, sticky="w", padx=(0, 8))
            self.corridor_dir_radios[k] = rb
        self.seat_group["Corridor"].trace_add("write", lambda *_a: self._fill_corridor_dirs())
        ttk.Radiobutton(sf, text="Station to station:", variable=self.seat_kind, value=JOURNEY,
                        command=self._seat_kind_changed).grid(row=4, column=0, sticky="w")
        jf = ttk.Frame(sf)
        jf.grid(row=4, column=1, sticky="ew", padx=(4, 0), pady=1)
        jf.columnconfigure(0, weight=1)
        jf.columnconfigure(2, weight=1)
        self.journey_from, self.journey_to = tk.StringVar(), tk.StringVar()
        self.journey_boxes = []
        for c, var in ((0, self.journey_from), (2, self.journey_to)):
            box = ttk.Combobox(jf, textvariable=var, width=16, style="Suggest.TCombobox")
            box.grid(row=0, column=c, sticky="ew")
            box.bind("<<ComboboxSelected>>", lambda _e: (self.seat_kind.set(JOURNEY), self._seat_kind_changed()))
            journey = (lambda _v=None: (self.seat_kind.set(JOURNEY), self._seat_kind_changed()))
            box.bind("<Key>", lambda e, f=journey: f() if e.char and e.char.isprintable() else None, add="+")
            Suggest(box, self._station_names, journey)
            self.journey_boxes.append(box)
        ttk.Label(jf, text="to").grid(row=0, column=1, padx=4)
        self.seat_week = tk.BooleanVar(value=True)
        pf = ttk.Frame(sf)
        pf.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.seating_var, self.standing_var = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        cap = ttk.Frame(pf)
        cap.grid(row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Label(cap, text="Show:").grid(row=0, column=0, padx=(0, 6))
        ttk.Checkbutton(cap, text="Seating capacity", variable=self.seating_var).grid(row=0, column=1, padx=(0, 10))
        ttk.Checkbutton(cap, text="Standing room", variable=self.standing_var).grid(row=0, column=2)
        ttk.Radiobutton(pf, text="Whole week (days, total, average)", variable=self.seat_week,
                        value=True).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(pf, text="Each ticked day on its own", variable=self.seat_week, value=False).grid(
            row=1, column=1, sticky="w", padx=(12, 0))
        cap.grid_configure(columnspan=2)
        wf = ttk.Frame(sf)
        wf.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.seat_window = tk.BooleanVar(value=False)
        ttk.Checkbutton(wf, text="Only trains between", variable=self.seat_window,
                        command=self._seat_window_changed).grid(row=0, column=0)
        self.seat_from, self.seat_to = tk.StringVar(value="07:00"), tk.StringVar(value="10:00")
        self.seat_from_box = ttk.Entry(wf, textvariable=self.seat_from, width=6)
        self.seat_from_box.grid(row=0, column=1, padx=4)
        ttk.Label(wf, text="and").grid(row=0, column=2)
        self.seat_to_box = ttk.Entry(wf, textvariable=self.seat_to, width=6)
        self.seat_to_box.grid(row=0, column=3, padx=4)
        af = self.seat_at_frame = ttk.Frame(sf)
        af.grid(row=7, column=0, columnspan=2, sticky="ew", padx=(22, 0), pady=(2, 0))
        af.columnconfigure(1, weight=1)
        self.seat_dir = tk.StringVar(value="arriving")
        self.seat_dir_box = sdf = ttk.Frame(af)
        sdf.grid(row=0, column=0, sticky="w")
        for i, k in enumerate(("arriving", "departing", "both")):
            ttk.Radiobutton(sdf, text=DIRECTIONS[k], variable=self.seat_dir, value=k).grid(row=0, column=i,
                                                                                         padx=(0, 6))
        self.seat_station = tk.StringVar(value="London Victoria")
        self.seat_station_box = ttk.Combobox(af, textvariable=self.seat_station, width=22, style="Suggest.TCombobox")
        self.seat_station_box.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        Suggest(self.seat_station_box, self._station_names)
        self.seat_at_note = ttk.Label(sf, text="(departing the first station)", style="Small.TLabel")
        self.seat_at_note.grid(row=7, column=0, columnspan=2, sticky="w", padx=(22, 0))
        ttk.Checkbutton(sf, text="Compare two timetables (original and updated XML + TRENT print)",
                        variable=self.two_plans, command=self._mode_changed).grid(row=8, column=0, columnspan=2,
                                                                                  sticky="w", pady=(4, 0))
        ttk.Button(sf, text="Edit corridors...", command=self.edit_groups).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._stations: list = []
        self._headcode_groups: list = []
        self._load_groups()
        self._seat_window_changed()
        for v in (self.seat_kind, self.seat_window, self.seat_from, self.seat_to, self.journey_from,
                  self.journey_to, *self.seat_group.values()):
            v.trace_add("write", lambda *_a: self._update_name_hint())

    def _load_groups(self):
        """Fill the lists: headcode groups and stations from the XML, corridors from the editable list."""
        from .seats import load_groups
        try:
            self._groups = [g for g in load_groups() if g.kind == "Corridor"]
        except Exception:
            self._groups = []
        names = [g.name for g in self._groups]
        self.seat_boxes["Corridor"].configure(values=names)
        if self.seat_group["Corridor"].get() not in names:
            self.seat_group["Corridor"].set(names[0] if names else "")
        from .seats import default_headcode_groups
        built_in = not self._headcode_groups
        heads = [f"{code}   {desc}" for code, desc in (self._headcode_groups or default_headcode_groups())]
        self.seat_boxes["Service group"].configure(values=heads)
        cur = self.seat_group["Service group"].get().split(" ")[0]
        match = next((h for h in heads if h.split(" ")[0] == cur), None)
        if match:
            self.seat_group["Service group"].set(match)
        elif heads and not cur:
            self.seat_group["Service group"].set(heads[0])
        self.seat_group_note.configure(text="Built-in GTR groups. Choose the Attune XML for this timetable's own "
                                            "list, or type any group.")
        (self.seat_group_note.grid if built_in else self.seat_group_note.grid_remove)()
        stations = self._stations or sorted({shown(s) for g in self._groups for s in g.route}, key=str.casefold)
        for box in (self.seat_station_box, *self.journey_boxes):
            box.configure(values=stations)
        self._fill_corridor_dirs()

    def _fill_corridor_dirs(self):
        g = next((g for g in getattr(self, "_groups", []) if g.name == self.seat_group["Corridor"].get()), None)
        if g is None or len(g.route) < 2:
            self.corridor_dir_box.grid_remove()
            return
        opts = {k: g.with_direction(k).direction_text for k in ("forward", "reverse", "both")}
        for k, v in opts.items():                                        # 'Both directions', station names kept
            self.corridor_dir_radios[k].configure(text=v[:1].upper() + v[1:])
        if self.corridor_dir.get() not in opts:
            self.corridor_dir.set("both")
        self.corridor_dir_box.grid()

    def _corridor_dir_key(self) -> str:
        return self.corridor_dir.get() or "both"

    def _station_names(self):
        """The stations offered as you type: the XML's, else every station on the corridors."""
        return self._stations or sorted({shown(s) for g in self._groups for s in g.route}, key=str.casefold)

    def _seat_kind_changed(self):
        self.corridor_dir.set(self._corridor_dir_key())
        self._seat_window_changed()
        self._update_name_hint()

    def _seat_window_changed(self):
        from .seats import JOURNEY
        on = self.seat_window.get()
        journey = self.seat_kind.get() == JOURNEY
        for w in (self.seat_from_box, self.seat_to_box):
            w.state(["!disabled"] if on else ["disabled"])
        (self.seat_at_frame.grid_remove if journey else self.seat_at_frame.grid)()
        (self.seat_at_note.grid if journey else self.seat_at_note.grid_remove)()
        self.seat_station_box.state(["!disabled"] if on else ["disabled"])
        for rb in self.seat_dir_box.winfo_children():
            rb.state(["!disabled"] if on else ["disabled"])

    def _seat_direction_key(self) -> str:
        from .seats import DIRECTIONS
        return self.seat_dir.get() if self.seat_dir.get() in DIRECTIONS else "both"

    def edit_groups(self):
        """Settings > Corridors (read again here when they are saved there)."""
        self.app.open_settings("Corridors")

    def _task_picked(self, _event=None):
        mode = self.task_box.picked()
        if mode and mode != self.mode.get():
            self.mode.set(mode)
            self._mode_changed()
        self._task_shown()                      # a group heading chosen: show its first task

    def _task_shown(self):
        self.task_box.show(self.mode.get())

    def _mode_changed(self):
        mode = self.mode.get()
        shown = dict(files_for(mode, self.two_plans.get()))
        for key, row in self.file_rows.items():
            lab = row[0]
            for w in row:
                (w.grid if key in shown else w.grid_remove)()
            if key in shown:
                lab.configure(text=shown[key])
        self.run_btn.configure(text=MODES[mode][1])
        self._set_state(self.sel_frame, mode != "packs")
        if mode == "mileage":                  # every date of the period is counted: the day ticks are not used
            for w in self.day_widgets:
                w.state(["disabled"])
        (self.fleet_note.grid_remove if mode == "packs" else self.fleet_note.grid)()
        self._update_day_note()
        pack_out = mode in ("create", "plans")             # the workbook layout only applies to stats packs
        for w in (*self.output_radios, self.one_day_note):
            (w.grid if pack_out else w.grid_remove)()
        (self.cmp_frame.grid if mode in ("plans", "packs") else self.cmp_frame.grid_remove)()
        self._set_state(self.cmp_frame, mode in ("plans", "packs"))
        (self.units_frame.grid if mode == "units" else self.units_frame.grid_remove)()
        (self.seats_frame.grid if mode == "seats" else self.seats_frame.grid_remove)()
        (self.mileage_frame.grid if mode == "mileage" else self.mileage_frame.grid_remove)()
        (self.opt_frame.grid if mode in ("units", "seats", "mileage") else self.opt_frame.grid_remove)()
        if mode == "seats":
            self._load_groups()
        self._number_frames()
        self._update_name_hint()
        if not self.running:
            self.status.configure(text=READY)
        if mode != "packs":
            self._read_inputs()

    def _number_frames(self):
        """Number the frames shown, in order, with no gap when 'Options' is hidden."""
        frames = [(self.in_frame, "Input"), (self.opt_frame, "Options"), (self.out_frame, "Output"),
                  (self.sel_frame, "Days, operators and fleets"), (self.run_frame, "Run")]
        n = 0
        for frame, title in frames:
            if frame is self.opt_frame and not frame.winfo_manager():
                continue
            n += 1
            frame.configure(text=f"{n}. {title}")

    def _set_state(self, widget, enabled: bool):
        for child in widget.winfo_children():
            if isinstance(child, (ttk.Checkbutton, ttk.Button, ttk.Radiobutton)):
                if enabled and getattr(child, "_keep_disabled", False):
                    continue
                child.state(["!disabled"] if enabled else ["disabled"])
            self._set_state(child, enabled)

    def _file_changed(self, key):
        kind = _kind(key)
        if kind in ("xml", "trent") and self.mode.get() != "packs":      # read once typing in the box pauses
            debounce(self, f"read_{kind}", 400, lambda: self._read_inputs(only=kind))
        self._update_name_hint()

    def _update_name_hint(self):
        """Show the name the output will get if the name box is left blank."""
        mode = self.mode.get()
        ticked = [d for d, v in enumerate(self.day_vars) if v.get()]
        get = {k: v.get().strip().strip('"') for k, v in self.vars.items()}
        name = None
        try:
            if mode == "packs" and get["pack_a"] and get["pack_b"]:
                name = packs_name(get["pack_a"], get["pack_b"])
            elif mode == "create" and self._prints:
                name = pack_name(self._prints[0], ticked)
            elif mode == "mileage" and self._prints:
                from .engine import period_name
                from .period import resolve
                st = self._mileage_state()
                name = period_name(self._prints[0], resolve(self._prints[0], st["kind"], st["month"], st["from"],
                                                            st["to"]))
            elif mode == "units" and self._prints:
                tt = timetable(self._prints[0])
                name = f"Unit report for {tt}" + (f" {DAYS[ticked[0]]}" if len(ticked) == 1 else "") if tt else None
            elif mode == "seats" and self._prints:
                win = f"{self.seat_from.get()}-{self.seat_to.get()}" if self.seat_window.get() else ""
                st = self._seat_state()
                what = (f"{st['journey'][0]} to {st['journey'][1]}" if st["kind"] == "Station to station" else
                        st["groups"][st["kind"]].split("   ")[0])
                name = seats_name(self._prints[0], what, ticked, win)
            elif mode == "plans" and len(self._prints) == 2:
                name = plans_name(self._prints[0], self._prints[1], get["xml_a"], get["xml_b"], ticked)
        except Exception:
            name = None
        self.name_hint.configure(text=name or ("named from the two packs" if mode == "packs" else
                                               "named from the timetable, e.g. Stats pack for DEC26"))

    def _browse(self, key):
        cur = self.vars[key].get().strip() or self.vars.get(key.replace("_b", "_a"), tk.StringVar()).get().strip()
        cur = (_split(cur) or [""])[0]
        start = os.path.dirname(cur) if cur else (self._last_dir or None)
        title = "Choose the " + file_label(self.file_rows[key][0].cget("text"))
        if _kind(key) == "trent":                   # one or more prints (TLGN: one per day type)
            ps = filedialog.askopenfilenames(parent=self, title=title, filetypes=FILETYPES["trent"], initialdir=start)
            if ps:
                self._last_dir = os.path.dirname(ps[0])
                self.vars[key].set(" ; ".join(os.path.normpath(p) for p in ps))
            return
        p = filedialog.askopenfilename(parent=self, title=title, filetypes=FILETYPES[_kind(key)], initialdir=start)
        if p:
            self._last_dir = os.path.dirname(p)
            self.vars[key].set(os.path.normpath(p))

    def _browse_dir(self):
        from rstools.fsutil import output_folder
        p = filedialog.askdirectory(parent=self, title="Choose the output folder",
                                    initialdir=output_folder(self.out_dir.get()))
        if p:
            self.out_dir.set(os.path.normpath(p))

    def edit_depots(self):
        self.app.open_settings("Depots")

    def edit_fleet(self):
        self.app.open_settings("Fleet data")

    def _fmt_changed(self):
        doc = self.fmt_var.get() != "xlsx"
        self.fmt_hint.configure(text="A full stats pack runs to hundreds of pages as a document - for a long "
                                     "document choose 'totals only', fewer days, or 'Changed rows only' for "
                                     "comparisons." if doc else "")

    def _days_changed(self):
        self._update_day_note()
        self._update_name_hint()

    def _set_days(self, pick):
        for d, v in enumerate(self.day_vars):
            v.set(pick(d))
        self._update_day_note()
        self._update_name_hint()

    def _set_fleets(self, on: bool):
        for f, v in self.fleet_vars.items():
            if self.fleet_info.get(f, ("", True))[1]:
                v.set(on)
        for op in self.op_vars:
            self.op_vars[op].set(on)

    def _set_operator(self, op):
        on = self.op_vars[op].get()
        for f, (fop, present) in self.fleet_info.items():
            if fop == op and present and f.upper() != "MAINT":
                self.fleet_vars[f].set(on)

    # ---------------------------------------------- reading the inputs
    def _paths(self, kind):
        """Files of a kind, one list per box."""
        keys = [k for k, _l in files_for(self.mode.get(), self.two_plans.get()) if _kind(k) == kind]
        boxes = [[p for p in _split(self.vars[k].get()) if os.path.isfile(p) and p.lower().endswith(EXT[kind])]
                 for k in keys]
        return [b for b in boxes if b]

    def _read_inputs(self, only=None):
        """Read the TRENT print(s) / XML(s) in the background to list fleets and days."""
        for kind in ("trent", "xml"):
            if only and kind != only:
                continue
            paths = self._paths(kind)
            self._tokens[kind] += 1
            token = self._tokens[kind]
            if not paths:
                self.q.put(("inputs", kind, token, None, None))
                continue
            if kind == "trent":
                self.fleet_note.configure(text="Reading the TRENT print...")
            self.app.pump.start(self._read_worker, kind, token, paths)
            self.app.pump.kick()

    def _read_worker(self, kind, token, paths):
        try:
            if kind == "trent":
                from .engine import _read_trents
                table = FleetTable.load()
                fleets: Counter = Counter()
                days = None
                prints = []
                for box in paths:
                    data = _read_trents(box, lambda m: None)
                    prints.append(data)
                    for d in data.diagrams:
                        fleets[(d.fleet, operator_of(d.depot, table.operator(d.fleet)))] += 1
                    days = data.days() if days is None else days & data.days()
                self.q.put(("inputs", kind, token, (fleets, days, prints), None))
            else:
                from .attune import parse_attune_xml
                from .seats import headcode_groups, network_stations
                days, groups, stations, starts = None, {}, set(), []
                for p in (box[0] for box in paths):
                    data = cached(parse_attune_xml, p)
                    starts.append(data.start)
                    days = data.days() if days is None else days & data.days()
                    for code, desc in headcode_groups(data):
                        groups.setdefault(code, desc)
                    stations |= set(network_stations(data))
                self.q.put(("inputs", kind, token, (days, sorted(groups.items()),
                                                    sorted(stations, key=str.casefold), starts), None))
        except Exception as exc:
            self.q.put(("inputs", kind, token, None, str(exc)))

    def _inputs_read(self, kind, result, error):
        if kind == "xml":
            self.xml_days = result[0] if result and not error else None
            self._headcode_groups, self._stations = (result[1], result[2]) if result and not error else ([], [])
            self._load_groups()
            for start in (result[3] if result and not error and len(result) > 3 else []):
                self.after(200, lambda st=start: self.app.rules_reminder(st))
            if error:
                self._append(f"XML: {error}", "error")
        else:
            self._prints = []
            if error:
                self.print_days = None
                self._show_fleets()
                self.fleet_note.configure(text=error)
                self._append(f"TRENT print: {error}", "error")
            elif result is None:
                self.print_days = None
                self._show_fleets()
            else:
                fleets, days, self._prints = result
                self.print_days = days
                self._show_fleets(fleets)
                self._fill_months()
        self._update_day_note()
        self._update_name_hint()

    def _show_fleets(self, found: "Counter | None" = None):
        """One row per operator: its fleets from the fleet table, plus any others in the print.
        Fleets not in the TRENT print are greyed out."""
        previous = {f: v.get() for f, v in self.fleet_vars.items()}
        table = FleetTable.load()
        groups: Dict[str, List[str]] = {op: [] for op in OPERATORS}
        in_print = {}
        if found:
            best: Dict[str, Tuple[str, int]] = {}
            for (fleet, op), n in found.items():
                if fleet not in best or n > best[fleet][1]:
                    best[fleet] = (op, n)
            for fleet, (op, _n) in best.items():
                in_print[fleet] = op
        for r in table.rows:
            if r.operator in OPERATOR_DEPOTS and r.cls not in in_print and (r.available or 0) > 0:
                groups[r.operator].append(r.cls)
        for fleet, op in in_print.items():
            groups[op].append(fleet)
        key = (tuple((op, tuple(sorted(f))) for op, f in groups.items()), tuple(sorted(in_print.items())),
               tuple((r.cls, r.operator, r.available) for r in table.rows))
        if key == getattr(self, "_fleet_key", None):
            return                                  # the same tick boxes: nothing is rebuilt (or flickers)
        self._fleet_key = key
        for w in self.fleet_frame.winfo_children():
            w.destroy()
        self.fleet_info = {}
        new_vars = {}
        row = 0
        for op in OPERATORS:
            fleets = sorted(groups[op], key=lambda f: (f.upper() == "MAINT", f))
            if op == OTHER and not fleets:
                continue
            cb = ttk.Checkbutton(self.fleet_frame, text=OP_LABEL[op], variable=self.op_vars[op],
                                 command=partial(self._set_operator, op), style="Bold.TCheckbutton")
            cb.grid(row=row, column=0, columnspan=FLEET_COLS, sticky="w", pady=(4 if row else 0, 0))
            row += 1
            for i, f in enumerate(fleets):
                present = found is None or f in in_print
                default = f.upper() != "MAINT" and present
                v = self.fleet_vars.get(f) or tk.BooleanVar()
                v.set(previous.get(f, self._saved_fleets.get(f, default)) and present)
                c = ttk.Checkbutton(self.fleet_frame, text=f, variable=v)
                c.grid(row=row + i // FLEET_COLS, column=i % FLEET_COLS, sticky="w", padx=(18 if i % FLEET_COLS == 0
                                                                                      else 0, 10))
                if not present:
                    c.state(["disabled"])
                    setattr(c, "_keep_disabled", True)
                new_vars[f] = v
                self.fleet_info[f] = (op, present)
            row += (len(fleets) + FLEET_COLS - 1) // FLEET_COLS or 1
        self.fleet_vars = new_vars
        if found is None:
            self.fleet_note.configure(text="Choose the TRENT print to see which fleets it contains.")
        else:
            absent = sorted(f for f, (_o, p) in self.fleet_info.items() if not p)
            self.fleet_note.configure(text=("Greyed out - not in this TRENT print: " + ", ".join(absent))
                                      if absent else "")
        if self.mode.get() == "packs":
            self._set_state(self.sel_frame, False)
        self._add_drop_target(self.fleet_frame)
        from rstools.help_text import attach
        attach(self.fleet_frame)                     # the fleet tickboxes are rebuilt for each print

    def _update_day_note(self):
        ticked = [d for d, v in enumerate(self.day_vars) if v.get()]
        parts = []
        if self.mode.get() in ("packs", "mileage"):
            ticked = []
        for label, have in (("TRENT print", self.print_days), ("XML", self.xml_days)):
            if have is not None:
                missing = [DAY_NAMES[d][:3] for d in ticked if d not in have]
                if missing:
                    parts.append(f"Not in the {label}: {', '.join(missing)}")
        self.day_note.configure(text=" · ".join(parts))

    # ------------------------------------------------------------ settings
    def _load_settings(self):
        self._last_dir = ""
        self._saved_fleets = {}
        try:
            with open(_settings_path(), encoding="utf-8") as fh:
                s = json.load(fh)
            if isinstance(s, dict):
                self._apply_settings(s)
        except (OSError, ValueError, TypeError, AttributeError):
            pass                       # missing or damaged settings: start with the defaults

    def _apply_settings(self, s: dict):
        if s.get("mode") in MODES:
            self.mode.set(s["mode"])
        if s.get("output") in OUTPUTS:
            self.output.set(s["output"])
        self.out_dir.set(s.get("output_dir", ""))
        self._last_dir = s.get("last_dir", "")
        days = s.get("days")
        if isinstance(days, list):
            for d, v in enumerate(self.day_vars):
                v.set(d in days)
        for op, on in (s.get("operators") or {}).items():
            if op in self.op_vars:
                self.op_vars[op].set(bool(on))
        self._saved_fleets = {f: bool(on) for f, on in (s.get("fleets") or {}).items()}
        for k, on in (s.get("compare") or {}).items():
            if k in self.cmp_vars:
                self.cmp_vars[k].set(bool(on))
        for k, on in (s.get("unit_reports") or {}).items():
            if k in self.unit_vars:
                self.unit_vars[k].set(bool(on))
        period = s.get("unit_period")
        self.unit_period.set(period if period in dict(UNIT_PERIODS)
                             else "week" if s.get("unit_week", True) else "days")
        possible = s.get("unit_possible")
        self.unit_possible.set(possible if possible in dict(UNIT_POSSIBLE) else "every")
        self.possible_box.set(dict(UNIT_POSSIBLE)[self.unit_possible.get()])
        self.two_plans.set(bool(s.get("two_plans", False)))
        seats = s.get("seats")
        if isinstance(seats, dict):
            if seats.get("kind") in ("Service group", "Corridor", "Station to station"):
                self.seat_kind.set(seats["kind"])
            for kind, var in self.seat_group.items():
                if isinstance((seats.get("groups") or {}).get(kind), str):
                    var.set(seats["groups"][kind])
            if seats.get("corridor_dir") in ("forward", "reverse", "both"):
                self.corridor_dir.set(seats["corridor_dir"])
                self._fill_corridor_dirs()
            journey = seats.get("journey")
            if isinstance(journey, list) and len(journey) == 2 and all(isinstance(x, str) for x in journey):
                self.journey_from.set(journey[0])
                self.journey_to.set(journey[1])
            self.seat_week.set(bool(seats.get("week", True)))
            self.seating_var.set(bool(seats.get("seating", True)))
            self.standing_var.set(bool(seats.get("standing", True)))
            self.seat_window.set(bool(seats.get("window", False)))
            for key, var in (("from", self.seat_from), ("to", self.seat_to), ("station", self.seat_station)):
                if isinstance(seats.get(key), str):
                    var.set(seats[key])
            from .seats import DIRECTIONS
            if seats.get("direction") in DIRECTIONS:
                self.seat_dir.set(seats["direction"])
            self._seat_window_changed()
        mileage = s.get("mileage")
        if isinstance(mileage, dict):
            for key, var in (("month", self.mileage_month), ("from", self.mileage_from), ("to", self.mileage_to)):
                if isinstance(mileage.get(key), str):
                    var.set(mileage[key])
            if mileage.get("kind") in dict(MILEAGE_PERIODS):
                self.mileage_kind.set(mileage["kind"])          # after the boxes, whose typing picks a kind
        if s.get("fmt") in ("xlsx", "pdf", "docx"):
            self.fmt_var.set(s["fmt"])
            self._fmt_changed()
        flag = s.get("flag_miles", 10)
        self.flag_var.set(flag is not None)
        if flag is not None:
            self.flag_miles.set(f"{float(flag):g}")

    def _save_settings(self):
        s = {"mode": self.mode.get(), "output": self.output.get(), "output_dir": self.out_dir.get().strip(),
             "last_dir": self._last_dir, "days": [d for d, v in enumerate(self.day_vars) if v.get()],
             "operators": {op: v.get() for op, v in self.op_vars.items()},
             "fleets": {f: v.get() for f, v in self.fleet_vars.items() if self.fleet_info.get(f, ("", True))[1]},
             "compare": {k: v.get() for k, v in self.cmp_vars.items()},
             "flag_miles": self._flag_threshold(),
             "unit_reports": {k: v.get() for k, v in self.unit_vars.items()}, "unit_period": self.unit_period.get(),
             "unit_possible": self.unit_possible.get(), "seats": self._seat_state(),
             "two_plans": self.two_plans.get(), "fmt": self.fmt_var.get(), "mileage": self._mileage_state()}
        write_json(_settings_path(), s)

    # ------------------------------------------------------------ saved comparisons
    def get_state(self) -> dict:
        return {"mode": self.mode.get(), "files": {k: v.get() for k, v in self.vars.items()},
                "output": self.output.get(), "fmt": self.fmt_var.get(), "output_dir": self.out_dir.get(),
                "output_name": self.out_name.get(), "days": [d for d, v in enumerate(self.day_vars) if v.get()],
                "operators": {op: v.get() for op, v in self.op_vars.items()},
                "compare": {k: v.get() for k, v in self.cmp_vars.items()}, "flag_miles": self._flag_threshold(),
                "unit_reports": {k: v.get() for k, v in self.unit_vars.items()}, "unit_period": self.unit_period.get(),
                "unit_possible": self.unit_possible.get(), "seats": self._seat_state(),
                "two_plans": self.two_plans.get(), "mileage": self._mileage_state()}

    def _mileage_state(self) -> dict:
        return {"kind": self.mileage_kind.get(), "month": self.mileage_month.get().strip(),
                "from": self.mileage_from.get().strip(), "to": self.mileage_to.get().strip()}

    def _seat_state(self) -> dict:
        return {"kind": self.seat_kind.get(), "groups": {k: v.get() for k, v in self.seat_group.items()},
                "corridor_dir": self._corridor_dir_key(),
                "journey": [self.journey_from.get().strip(), self.journey_to.get().strip()],
                "week": self.seat_week.get(), "window": self.seat_window.get(), "from": self.seat_from.get(),
                "to": self.seat_to.get(), "station": self.seat_station.get(),
                "direction": self._seat_direction_key(), "seating": self.seating_var.get(),
                "standing": self.standing_var.get()}

    def set_state(self, s: dict):
        self._apply_settings(s)
        self._mode_changed()
        for k, v in (s.get("files") or {}).items():
            if k in self.vars and isinstance(v, str):
                self.vars[k].set(v)
        self.out_name.set(s.get("output_name", "") if isinstance(s.get("output_name"), str) else "")

    def files_in_state(self, s: dict) -> list:
        keys = [k for k, _l in (files_for(s["mode"], bool(s.get("two_plans"))) if s.get("mode") in FILES else [])]
        return [v for k, v in (s.get("files") or {}).items() if k in keys and v]

    # ---------------------------------------------------------------- log
    def _append(self, msg, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", (tag,) if tag else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_outputs(self):
        self.app.open_outputs(self.outputs, force=True)

    # ---------------------------------------------------------------- run
    def _flag_threshold(self):
        """The mileage-increase threshold, or None when flagging is off / the box is not a number."""
        if not self.flag_var.get():
            return None
        try:
            value = float(self.flag_miles.get())
        except ValueError:
            return 10.0
        return value if value > 0 else None

    def run(self):
        """Start the selected run (Run button, F5 or Ctrl+Enter)."""
        if self.running:
            return
        mode = self.mode.get()
        days = [d for d, v in enumerate(self.day_vars) if v.get()]
        ops = {op for op, v in self.op_vars.items() if v.get()}
        fleets = None
        if self.fleet_info and any(p for _o, p in self.fleet_info.values()):
            fleets = {f for f, v in self.fleet_vars.items() if v.get() and self.fleet_info[f][1]}
        files = {k: v.get().strip().strip('"') for k, v in self.vars.items()}
        for key, label in files_for(mode, self.two_plans.get()):
            if not files[key]:
                if (mode, key) in OPTIONAL and not self.two_plans.get():
                    continue
                return messagebox.showwarning(TITLE, f"Choose the {file_label(label)}.", parent=self)
            parts = _split(files[key]) if _kind(key) == "trent" else [files[key]]
            for p in parts:
                if not os.path.isfile(p):
                    return messagebox.showwarning(TITLE, f"This file could not be found:\n{p}", parent=self)
                if not p.lower().endswith(EXT[_kind(key)]):
                    return messagebox.showwarning(TITLE, f"The {file_label(label)} should be a "
                                                         f"{EXT[_kind(key)]} file:\n{p}", parent=self)
        if mode == "mileage":
            st = self._mileage_state()
            if st["kind"] == "month" and not st["month"]:
                return messagebox.showwarning(TITLE, "Choose or type the month, e.g. January 2027.", parent=self)
            if st["kind"] == "custom":
                from .period import PeriodError, parse_date
                try:
                    a, b = parse_date(st["from"], "first date"), parse_date(st["to"], "last date")
                except PeriodError as exc:
                    return messagebox.showwarning(TITLE, str(exc), parent=self)
                if b < a:
                    return messagebox.showwarning(TITLE, "The last date is before the first date.", parent=self)
        if mode != "packs":
            if not days and mode != "mileage":
                return messagebox.showwarning(TITLE, "Tick at least one diagram day.", parent=self)
            if not ops:
                return messagebox.showwarning(TITLE, "Tick at least one operator.", parent=self)
            if fleets is not None and not fleets:
                return messagebox.showwarning(TITLE, "Tick at least one fleet.", parent=self)
        out_dir = self.out_dir.get().strip().strip('"')
        if out_dir and not os.path.isdir(out_dir):
            return messagebox.showwarning(TITLE, f"The output folder does not exist:\n{out_dir}", parent=self)
        if mode in ("plans", "packs") and self.flag_var.get():
            try:
                float(self.flag_miles.get())
            except ValueError:
                return messagebox.showwarning(TITLE, "Type the mileage increase to flag as a number of miles, "
                                                     "e.g. 10, or untick 'Flag mileage increases over'.", parent=self)
        opts = PackOptions(days=days, operators=ops, fleets=fleets, output=self.output.get(),
                           output_dir=out_dir, output_name=self.out_name.get().strip(),
                           compare=CompareOptions(**{k: v.get() for k, v in self.cmp_vars.items()},
                                                  flag_miles=self._flag_threshold()),
                           fmt=self.fmt_var.get(), possible=self.unit_possible.get())
        if mode == "units" and not any(v.get() for v in self.unit_vars.values()):
            return messagebox.showwarning(TITLE, "Tick at least one unit report.", parent=self)
        if mode == "seats":
            st = self._seat_state()
            if not st["seating"] and not st["standing"]:
                return messagebox.showwarning(TITLE, "Tick seating capacity, standing room or both.", parent=self)
            if st["kind"] == "Station to station":
                if not all(st["journey"]):
                    return messagebox.showwarning(TITLE, "Choose the two stations.", parent=self)
                if st["journey"][0].casefold() == st["journey"][1].casefold():
                    return messagebox.showwarning(TITLE, "Choose two different stations.", parent=self)
            elif not st["groups"][st["kind"]]:
                return messagebox.showwarning(TITLE, "Choose or type a headcode group (e.g. 1F)." if
                                              st["kind"] == "Service group" else "Choose or type a corridor.",
                                              parent=self)
            if self.seat_window.get():
                from .seats import SeatsError, parse_time
                try:
                    parse_time(self.seat_from.get()), parse_time(self.seat_to.get())
                except SeatsError as exc:
                    return messagebox.showwarning(TITLE, str(exc), parent=self)
                if not self.seat_station.get().strip() and st["kind"] != "Station to station":
                    return messagebox.showwarning(TITLE, "Choose the station for the time window.", parent=self)
        for key, _label in files_for(mode, self.two_plans.get()):
            for p in (_split(files[key]) if _kind(key) == "trent" else [files[key]] if files[key] else []):
                self.app.add_recent(_kind(key), p)
        self._save_settings()
        self.app.save_app_settings()
        self.running = True
        self.outputs = []
        for b in (self.open_btn, self.dir_btn, self.run_btn):
            b.state(["disabled"])
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress.begin()
        self._started = time.monotonic()
        self.app.set_busy(True)
        extra = {"two_plans": self.two_plans.get() and mode in ("units", "seats"), "seats": self._seat_state(),
                 "which": [k for k, v in self.unit_vars.items() if v.get()], "unit_period": self.unit_period.get(),
                 "mileage": self._mileage_state()}
        self.app.pump.start(self._work, mode, files, opts, extra)
        self.app.pump.kick()

    def _work(self, mode, files, opts, extra):
        """Runs in a helper thread: uses only its arguments (Tk variables are read in run())."""
        def progress(f, m):
            self.q.put(("prog", f, m))

        def log(m, tag=None):
            self.q.put(("log", m, tag))
        try:
            version = _version()
            if mode == "packs":
                progress(0.1, "Reading and comparing the stats packs...")
                out, n = compare_packs(files["pack_a"], files["pack_b"], opts.output_dir, opts.output_name,
                                       opts.compare, opts.fmt)
                self.q.put(("done", [out], [], f"{plural(n, 'difference')} found between the stats packs."))
                return
            progress(0.02, "Reading the files...")
            plans = [load_plan(PlanInputs(files["xml_a"], files["trent_a"]), log, xml_optional=mode == "units")]
            two = mode == "plans" or extra["two_plans"]
            if two:
                plans.append(load_plan(PlanInputs(files["xml_b"], files["trent_b"]), log))
            labels = ("Original plan: ", "Updated plan: ") if two else ("",)
            warnings, flagged = [], []
            if mode == "mileage":
                from .engine import period_mileage
                st = extra["mileage"]
                warnings += plans[0].warnings
                outs, w, summary = period_mileage(plans[0], opts, st["kind"], version, st["month"], st["from"],
                                                  st["to"], progress)
                warnings += w
                for msg in warnings:
                    log("WARNING: " + msg, "warn")
                self.q.put(("done", outs, warnings, "Mileage created for " + summary))
                return
            for pre, p in zip(labels, plans):
                flagged += [pre + m for m in day_availability(p, opts.days)]
                warnings += [pre + w for w in p.warnings]
            if flagged:
                self.q.put(("missing_days", flagged))
            usable = sorted(set(opts.days) & set.intersection(*[p.trent.days() for p in plans]))
            if not usable:
                raise StatsPackError("None of the ticked days are in the TRENT print.")
            opts.days = usable
            old = plans[0] if two and mode != "plans" else None
            if mode == "seats":
                st = extra["seats"]
                window = (st["station"], st["from"], st["to"]) if st["window"] else None
                outs, w, summary = seats_report(plans[-1], opts, st["kind"], st["groups"].get(st["kind"], ""),
                                                st["week"], window, st["direction"], progress, log, old=old,
                                                corridor_dir=st["corridor_dir"], journey=tuple(st["journey"]),
                                                seating=st["seating"], standing=st["standing"])
                warnings += w
            elif mode == "units":
                which = extra["which"]
                outs, w = unit_reports(plans[-1], opts, which, extra["unit_period"], progress, old=old)
                warnings += w
                summary = ("Unit report comparison created: " if old else "Unit report created: ") + "; ".join(
                    UNIT_REPORTS[k] for k in which) + "."
            elif mode == "create":
                per_day, w = build_pack(plans[0], opts, version, progress)
                warnings += w
                progress(0.75, "Writing the stats pack...")
                outs = write_pack(per_day, opts, plans[0], version)
                summary = f"Stats pack created for {', '.join(DAY_NAMES[d] for d, _t in per_day)}."
            else:
                outs, w, n = compare_plans(plans[0], plans[1], opts, version, progress)
                warnings += w
                summary = f"{plural(n, 'difference')} found between the plans."
            for msg in warnings:
                log("WARNING: " + msg, "warn")
            self.q.put(("done", outs, warnings, summary))
        except StatsPackError as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:
            self.q.put(("error", errorlog.describe(exc)))

    def stop_run(self, _event=None):
        """Stop the running task at its next step (Stop button or Esc)."""
        if getattr(self, "running", False) and not self.q.stopping:
            self.q.stop()
            self.stop_btn.state(["disabled"])
            self.status.configure(text="Stopping...")
        return "break"

    def _finish(self, ok: bool):
        self.running = False
        self.app.set_busy(False)
        self.run_btn.state(["!disabled"])
        self.status.configure(text=("Finished in " + duration(time.monotonic() - self._started) if ok else FAILED))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "prog":
                    self.progress.set(item[1], item[2])
                elif kind == "log":
                    self._append(item[1], item[2])
                elif kind == "inputs":
                    _k, what, token, result, error = item
                    if token == self._tokens[what]:
                        self._inputs_read(what, result, error)
                elif kind == "missing_days":
                    for m in item[1]:
                        self._append("MISSING DAY: " + m, "warn")
                    messagebox.showwarning(TITLE, "Some ticked days are not in the files:\n\n" + "\n".join(item[1])
                                           + "\n\nDays missing from the TRENT print are left out. For days missing "
                                             "from the XML, calling points and times come from the TRENT print "
                                             "only (no passes, seconds or public times).", parent=self)
                elif kind == "done":
                    _k, outs, warnings, summary = item
                    self._finish(True)
                    self.outputs = outs
                    self.app.open_outputs(outs)
                    self.progress.finish()
                    self._append(summary, "ok")
                    for p in outs:
                        self._append(f"Saved: {p}", "ok")
                    if outs:
                        self.open_btn.state(["!disabled"])
                        self.dir_btn.state(["!disabled"])
                    note = f"\n\n{plural(len(warnings), 'warning')} - see the log." if warnings else ""
                    from rstools.fsutil import excel_warning
                    long_warn = excel_warning(outs)
                    if long_warn:
                        self._append("WARNING: " + long_warn, "warn")
                        note += f"\n\n{long_warn}"
                    self.app.notify_done("Stats Pack finished", summary)
                    messagebox.showinfo(TITLE, f"{summary}\n\n" + "\n".join(outs) + note, parent=self)
                elif kind == "stopped":
                    self._finish(False)
                    self.status.configure(text=STOPPED)
                    self._append("Stopped - nothing was saved.", "warn")
                elif kind == "error":
                    self._finish(False)
                    self._append("ERROR: " + item[1], "error")
                    self.app.notify_done("Stats Pack failed", item[1].splitlines()[0], False)
                    messagebox.showerror(TITLE, item[1][:1500], parent=self)
        except queue.Empty:
            pass
