"""'Live View' tab: any comparison in the app, browsed train by train inside the window.

Pick a comparison and its files, press Compare (F5): every train (or stats row) is listed on the left
and the selected one is shown side by side on the right, differences coloured and described. With
'Refresh when a file is saved' ticked, the files are watched: saving either one (e.g. after fixing a
time in Excel) re-runs the comparison within a couple of seconds, keeps the train selected, and
marks the trains that changed since the last refresh.
"""
from __future__ import annotations

import os
import queue
import threading
import traceback
import time
import tkinter as tk
from typing import Dict, List, Tuple
from tkinter import ttk, filedialog, messagebox

from rstools import errorlog, theme
from rstools.widgets import Progress, TaskBox, Tooltip
from rstools.branding import APP_NAME
from rstools.naming import file_label

from .model import ADDED, CHANGED, DIFF_STATES, ISSUE, PAIRED, REMOVED, SAME, view

TITLE = f"{APP_NAME} - Live View"
_XL, _PR, _LI = (".xlsx", ".xlsm"), (".pdf", ".docx", ".docm"), (".xlsx", ".xlsm", ".csv")
_PV = _PR + (".vpt",)                                   # train prints, or Attune VPT exports
_CWN = (".xlsx", ".xlsm", ".xls", ".xlsb", ".xltx", ".xltm")
_TYPE_NAMES = {".xlsx": "Excel", ".xlsm": "Excel", ".xls": "Excel", ".xlsb": "Excel", ".xltx": "Excel",
               ".xltm": "Excel", ".csv": "CSV", ".pdf": "PDF", ".docx": "Word", ".docm": "Word", ".xml": "Attune XML",
               ".vpt": "Attune VPT export"}
FILES: Dict[str, List[Tuple[str, str, Tuple[str, ...], bool]]] = {   # box key, label, file types, several?
    "cwn": [("a", "Original CWN:", _CWN, False), ("b", "Updated CWN:", _CWN, False)],
    "sp_plans": [("xa", "Original Attune XML:", (".xml",), False),
                 ("ta", "Original TRENT VL29 print(s):", (".docx",), True),
                 ("xb", "Updated Attune XML:", (".xml",), False),
                 ("tb", "Updated TRENT VL29 print(s):", (".docx",), True)],
    "sp_packs": [("a", "Original stats pack:", _XL, False), ("b", "Updated stats pack:", _XL, False)],
    "timetables": [("a", "GTR timetable:", _XL, False), ("b", "Network Rail timetable:", _XL, False)],
    "print_tt": [("a", "Train print(s) - reference:", _PR, True), ("b", "Timetable to check:", _XL, False)],
    "list_tt": [("a", "Attune train list - reference:", _LI, False), ("b", "Timetable to check:", _XL, False)],
    "prints": [("a", "Original train print(s) or VPT:", _PV, True), ("b", "Updated train print(s) or VPT:", _PV, True)],
    "lists": [("a", "Original Attune train list:", _LI, False), ("b", "Updated Attune train list:", _LI, False)],
    "s4docs": [("a", "Original Section 4 PDF(s):", (".pdf",), True),
               ("b", "Updated Section 4 PDF(s):", (".pdf",), True)],
    "tprs": [("a", "Original TPR PDF(s):", (".pdf",), True), ("b", "Updated TPR PDF(s):", (".pdf",), True)],
    "s4check": [("xa", "Attune XML:", (".xml",), False),
                ("a", "Section 4 PDF(s) (blank: the rule set in use):", (".pdf",), True),
                ("xb", "Our VPT (optional, for running lines):", (".vpt",), False),
                ("tb", "Other operators' VPT(s) (optional):", (".vpt",), True)],
    "berthing": [("a", "Older berthing chart:", _XL, False), ("b", "Newer berthing chart:", _XL, False)],
    "units": [("xa", "Original Attune XML (optional):", (".xml",), False),
              ("ta", "Original TRENT print(s):", (".docx",), True),
              ("xb", "Updated Attune XML (optional):", (".xml",), False),
              ("tb", "Updated TRENT print(s):", (".docx",), True)],
}
OPTIONAL = {("s4check", "a"), ("s4check", "xb"), ("s4check", "tb"),          # boxes that may be left blank
            ("units", "xa"), ("units", "xb")}
PASSENGER_MODES = ("cwn", "timetables", "print_tt", "list_tt", "prints")     # where 'passenger times only' applies
CHECK_MODES = ("timetables", "print_tt", "list_tt", "prints")      # where header / timing differences can be switched
FILTERS = {"Differences only": DIFF_STATES, "All": None,                      # then by result, then by progress, A-Z
           "Added": (ADDED,), "Changed": (CHANGED,), "Issues": (ISSUE,), "Paired (check by eye)": (PAIRED,),
           "Removed / missing": (REMOVED,), "Unchanged": (SAME,),
           "Changed since confirmed": "reopened", "Confirmed": "confirmed", "Not yet confirmed": "unconfirmed",
           "Updated by the last refresh": "fresh"}
TICK = "\u2714"
MAX_LIST = 20000                    # rows put in the list at once (search or filter to narrow a bigger result)
SEP = " ; "
POLL_MS = 1500


LAYOUTS = {"side": "Side by side", "stacked": "Stacked"}
ZOOM_MIN, ZOOM_MAX = -2, 5                       # steps of text size in the list and details


def _pick(value, allowed, default):
    return value if value in allowed else default


def _orient(layout: str) -> str:
    return "vertical" if layout == "stacked" else "horizontal"


def _split(text: str):
    return [p.strip().strip('"') for p in text.split(SEP.strip()) if p.strip().strip('"')]


def _join(existing: str, new) -> str:
    """The files already in a box plus new ones, each once, in the order added."""
    return SEP.join(dict.fromkeys(_split(existing) + list(new)))


class LiveTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(12, 8, 12, 10))
        self.app = app
        self.q: "queue.Queue" = queue.Queue()
        self.running = False
        self.result = None
        self.raw = None                 # the comparison as computed; self.result is it as shown (toggles)
        self.items = {}                 # key -> LiveItem
        self.fresh = set()              # keys changed by the last refresh
        self.watch = {}                 # path -> (mtime, size) when last compared
        self._pending_change = None     # (path, mtime, size) seen changing, waiting to settle
        self._started = 0.0
        self._dnd = ""
        self._days_known = set()
        self.confirmed: Dict[str, str] = {}      # key -> fingerprint when ticked as confirmed (see progress.py)
        self.reopened: set = set()               # confirmed, then changed by a refresh: the tick was taken off
        self._progress_for = ""                  # the comparison the confirmations belong to
        self._autosave_after = None
        self._build()
        self._mode_changed()
        app.pump.add(self.q, self._poll, lambda: self.running)
        self._watch_id = None                # the saved-file check runs only while there is something to watch

    # ------------------------------------------------------------------ UI
    def _build(self):
        from .adapters import MODE_GROUPS
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        theme.tip(ttk.Label(self, text="Browse any comparison train by train: click a train to see it side by side "
                                       "with its match and every difference. Tick 'Refresh when a file is saved' to "
                                       "see changes as you save the files.", style="Small.TLabel", wraplength=1100,
                            justify="left")).grid(
            row=1, column=0, sticky="w", pady=(0, 6))

        top = ttk.Frame(self)
        top.grid(row=2, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Task:", font="AppBold").grid(row=0, column=0, sticky="w")
        self.mode_box = TaskBox(top, MODE_GROUPS, width=52)
        self.mode_names = {m: lab for m, lab in self.mode_box.tasks}
        last = getattr(self.app.opts, "live_mode", "") or "cwn"
        self.mode_box.show(last if last in FILES else "cwn")        # the task used last time
        self.mode_box.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        self.mode_box.bind("<<ComboboxSelected>>", lambda _e: (self.mode_box.show(self.mode()), self._mode_changed()))
        self.files_frame = ttk.Frame(top)
        self.files_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.files_frame.columnconfigure(1, weight=1)
        self.vars, self.rows = {}, {}
        self.clear_btns = {}
        for key in ("a", "b", "xa", "ta", "xb", "tb"):
            var = self.vars[key] = tk.StringVar()
            lab = ttk.Label(self.files_frame, text="")
            box = self.app.file_box(self.files_frame, var, f"live_{key}")
            btn = ttk.Button(self.files_frame, text="Browse...", command=lambda k=key: self._browse(k))
            self.rows[key] = (lab, box, btn)
            self.clear_btns[key] = ttk.Button(self.files_frame, text="Clear", width=6,
                                              command=lambda v=var: v.set(""))
        for var in self.vars.values():               # new files: days and watched files start afresh
            var.trace_add("write", lambda *_a: self._files_changed())
        self.days_frame = ttk.Frame(top)
        self.days_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Label(self.days_frame, text="Days:").grid(row=0, column=0, padx=(0, 6))
        from cwn_compare.days import DAY_LABELS
        self.day_vars = [tk.BooleanVar(value=True) for _d in DAY_LABELS]
        self.day_cbs = []
        for i, lab in enumerate(DAY_LABELS):
            cb = ttk.Checkbutton(self.days_frame, text=lab, variable=self.day_vars[i], state="disabled",
                                 command=self._days_changed)
            cb.grid(row=0, column=i + 1, padx=(0, 4))
            self.day_cbs.append(cb)
        self.days_note = ttk.Label(self.days_frame, text="(available once the CWNs are loaded)", style="Small.TLabel")
        self.days_note.grid(row=0, column=len(DAY_LABELS) + 1, padx=(6, 0))
        ctl = ttk.Frame(top)
        ctl.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        ctl.columnconfigure(3, weight=1)
        self.run_btn = ttk.Button(ctl, text="Compare", style="Run.TButton", command=self.run)
        self.run_btn.grid(row=0, column=0)
        self.auto_var = tk.BooleanVar(value=True)
        self.auto_var.trace_add("write", lambda *_a: self._keep_watching())
        ttk.Checkbutton(ctl, text="Refresh when a file is saved", variable=self.auto_var).grid(row=0, column=1,
                                                                                            padx=(12, 0))
        opts = ttk.Frame(top)
        opts.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.ignore_var = tk.BooleanVar(value=False)
        self.check_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Ignore trains in the source that are not in the files compared with it",
                        variable=self.ignore_var, command=self._view_changed).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Check for differences (untick to pair trains for checking by eye)",
                        variable=self.check_var, command=self._view_changed).grid(row=0, column=1, sticky="w",
                                                                                 padx=(16, 0))
        self.pax_var = tk.BooleanVar(value=bool(getattr(self.app.opts, "live_passenger_only", False)))
        self.pax_cb = ttk.Checkbutton(opts, text="Passenger times only", variable=self.pax_var,
                                      command=self._pax_changed)
        self.pax_cb.grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.hdr_var = tk.BooleanVar(value=bool(getattr(self.app.opts, "live_check_header", True)))
        self.hdr_cb = ttk.Checkbutton(opts, text="Check header differences", variable=self.hdr_var,
                                      command=self._checks_changed)
        self.hdr_cb.grid(row=0, column=3, sticky="w", padx=(16, 0))
        self.tim_var = tk.BooleanVar(value=bool(getattr(self.app.opts, "live_check_timing", True)))
        self.tim_cb = ttk.Checkbutton(opts, text="Check timing differences", variable=self.tim_var,
                                      command=self._checks_changed)
        self.tim_cb.grid(row=0, column=4, sticky="w", padx=(16, 0))
        Tooltip(self.hdr_cb, "Train header details (days run, train ID, UID, class...). Untick to ignore them: "
                             "differences in them are greyed and do not make a train 'changed'.")
        Tooltip(self.tim_cb, "Arrival, departure and passing times. Untick to compare only the header and the "
                             "calling points: time differences are greyed and do not make a train 'changed'.")
        Tooltip(self.pax_cb, "Hide passing times and times shown in one file only (intermediate timing points), "
                             "for comparing timetables where one file does not show them.")
        self.prog = ttk.Progressbar(ctl, mode="determinate", maximum=1.0, length=120)
        self.prog.grid(row=0, column=2, padx=(12, 0))          # always in place: nothing moves when it runs
        self.status = ttk.Label(ctl, text="Choose the files and press Compare (F5).", style="Small.TLabel")
        self.status.grid(row=0, column=3, sticky="w", padx=(10, 0))
        self.window = None                  # popout.LiveWindow, set by the app: the output in its own window
        self.progress = Progress(self.prog)

        # the output (train list and details) is a frame of its own: it is what pops out into a window
        self.out_holder = tk.Frame(self)
        self.out_holder.grid(row=3, column=0, sticky="nsew")
        tool = self.toolbar = ttk.Frame(self.out_holder, padding=(0, 0, 0, 4))
        tool.pack(fill="x")
        self.layout_var = tk.StringVar(value=_pick(getattr(self.app.opts, "live_layout", "side"), LAYOUTS, "side"))
        self.changed_only = tk.BooleanVar(value=bool(getattr(self.app.opts, "live_changed_only", False)))
        self.list_hidden = tk.BooleanVar(value=bool(getattr(self.app.opts, "live_list_hidden", False)))
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, int(getattr(self.app.opts, "live_zoom", 0) or 0)))
        self.display_ratio = 1.0              # the window's display scaling against the main window's (pop-out)
        ttk.Label(tool, text="Layout:").grid(row=0, column=0, padx=(0, 4))
        self.layout_box = ttk.Combobox(tool, state="readonly", width=13, values=list(LAYOUTS.values()))
        self.layout_box.set(LAYOUTS[self.layout_var.get()])
        self.layout_box.grid(row=0, column=1)
        self.layout_box.bind("<<ComboboxSelected>>", lambda _e: self._layout_picked())
        ttk.Checkbutton(tool, text="Changed rows only", variable=self.changed_only,
                        command=self._display_changed).grid(row=0, column=2, padx=(10, 0))
        ttk.Checkbutton(tool, text="Hide train list", variable=self.list_hidden,
                        command=self._list_visibility).grid(row=0, column=3, padx=(10, 0))
        self.smaller_btn = ttk.Button(tool, text="A-", width=3, command=lambda: self.set_zoom(self.zoom - 1))
        self.bigger_btn = ttk.Button(tool, text="A+", width=3, command=lambda: self.set_zoom(self.zoom + 1))
        ttk.Label(tool, text="Text:").grid(row=0, column=4, padx=(10, 4))
        self.smaller_btn.grid(row=0, column=5)
        self.bigger_btn.grid(row=0, column=6, padx=(2, 0))
        ttk.Button(tool, text="< Previous", command=lambda: self.step(-1)).grid(row=0, column=7, padx=(12, 0))
        ttk.Button(tool, text="Next >", command=lambda: self.step(1)).grid(row=0, column=8, padx=(2, 0))
        win = ttk.Frame(tool)
        win.grid(row=0, column=9, sticky="e", padx=(12, 0))
        tool.columnconfigure(9, weight=1)
        self.pop_btn = ttk.Button(win, text="Pop out", command=self.toggle_window)
        self.pop_btn.grid(row=0, column=0)
        self.full_btn = ttk.Button(win, text="Full screen (F11)", command=lambda: self.window and
                                   self.window.toggle_fullscreen())
        self.full_btn.grid(row=0, column=1, padx=(4, 0))
        self.top_cb = ttk.Checkbutton(win, text="Always on top", command=lambda: self.window and
                                      self.window.set_on_top())
        self.top_cb.grid(row=0, column=2, padx=(4, 0))
        self.full_btn.grid_remove()
        self.top_cb.grid_remove()
        Tooltip(self.pop_btn, "Show only the results (train list and details) in a window of their own "
                              "(Ctrl+Shift+P), to put them on another monitor or full screen. The task, files and "
                              "options stay here: Compare (F5) updates the window.")
        Tooltip(self.layout_box, "Side by side: the train list beside the details (wide screens). Stacked: the list "
                                 "above the details (tall or narrow windows).")
        # the two panes are children of the output frame (not of the paned window), so the paned window can be
        # rebuilt the other way round without losing them
        self.left = left = ttk.Frame(self.out_holder, padding=(0, 0, 6, 0))
        self.right = right = ttk.Frame(self.out_holder, padding=(6, 0, 0, 0))
        self.pane = ttk.Panedwindow(self.out_holder)         # replaced at once by the layout's own
        self._arrange_panes()

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        lf = ttk.Frame(left)
        lf.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        lf.columnconfigure(3, weight=1)
        ttk.Label(lf, text="Show:").grid(row=0, column=0)
        self.filter_box = ttk.Combobox(lf, values=list(FILTERS), state="readonly", width=24)
        self.filter_box.set("Differences only")
        self.filter_box.grid(row=0, column=1, padx=4)
        self.filter_box.bind("<<ComboboxSelected>>", lambda _e: self._fill_list())
        ttk.Label(lf, text="Find:").grid(row=0, column=2, padx=(8, 0))
        self.search = tk.StringVar()
        ent = ttk.Entry(lf, textvariable=self.search)
        ent.grid(row=0, column=3, sticky="ew", padx=4)
        self.find_entry = ent
        self._search_after = None
        self.search.trace_add("write", lambda *_a: self._search_soon())
        self.listv = ttk.Treeview(left, columns=("ok", "group", "train", "status"), show="headings",
                                  selectmode="browse", height=6)
        for col, text in (("ok", TICK), ("group", "Section / tab"), ("train", "Train"), ("status", "Status")):
            self.listv.heading(col, text=text)
            self.listv.column(col, anchor="center" if col == "ok" else "w", stretch=col == "status")
        self.listv.bind("<ButtonRelease-1>", self._list_click, add="+")
        self.listv.bind("<space>", lambda _e: self.toggle_confirmed() or "break")
        self.rescale()
        self.listv.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listv.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.listv.configure(yscrollcommand=sb.set)
        self.listv.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())
        nav = ttk.Frame(left)
        nav.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(nav, text="< Previous", command=lambda: self.step(-1)).grid(row=0, column=0)
        ttk.Button(nav, text="Next >", command=lambda: self.step(1)).grid(row=0, column=1, padx=4)
        self.export_btn = ttk.Button(nav, text="Export...", command=self.export, state="disabled")
        self.export_btn.grid(row=0, column=2, padx=(4, 0))
        self.count_lbl = ttk.Label(nav, text="", style="Small.TLabel")
        self.count_lbl.grid(row=0, column=3, padx=(8, 0))
        prog = ttk.Frame(left)
        prog.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.confirm_btn = ttk.Button(prog, text=f"{TICK} Confirm (Space)", command=self.toggle_confirmed)
        self.confirm_btn.grid(row=0, column=0)
        ttk.Button(prog, text="Save progress...", command=self.save_progress).grid(row=0, column=1, padx=4)
        ttk.Button(prog, text="Load progress...", command=self.load_progress).grid(row=0, column=2)
        self.progress_lbl = ttk.Label(prog, text="", style="Small.TLabel")
        self.progress_lbl.grid(row=0, column=3, padx=(8, 0))
        Tooltip(self.confirm_btn, "Tick the selected train as checked. Ticks are saved automatically for these "
                                  "files; a train that changes after it was ticked is un-ticked and listed under "
                                  "'Changed since confirmed'.")

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.head = ttk.Label(right, text="", style="Head.TLabel", wraplength=640, justify="left")
        self.head.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.detail = ttk.Treeview(right, show="headings", selectmode="browse", height=6)
        self.detail.grid(row=1, column=0, sticky="nsew")
        self.detail.bind("<<TreeviewSelect>>", lambda _e: self._row_picked())
        self.detail.bind("<ButtonRelease-1>", self._detail_click, add="+")
        for key in ("<Return>", "<space>"):
            self.detail.bind(key, lambda _e: (self._toggle_details() if self._details_iid and
                                              self.detail.focus() == self._details_iid else None))
        self._rows: dict = {}                       # detail row id -> LiveRow
        self._details_iid = ""
        dsb = ttk.Scrollbar(right, orient="vertical", command=self.detail.yview)
        dsb.grid(row=1, column=1, sticky="ns")
        hsb = ttk.Scrollbar(right, orient="horizontal", command=self.detail.xview)
        hsb.grid(row=2, column=0, sticky="ew")
        self.detail.configure(yscrollcommand=dsb.set, xscrollcommand=hsb.set)
        self.notes = tk.Text(right, height=4, wrap="word", font="TkFixedFont", state="disabled", relief="flat",
                             borderwidth=1, highlightthickness=1)
        self.notes.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.legend = ttk.Label(right, text="Yellow: changed   Green: added   Red: removed / missing   Orange: issue   "
                                            "Grey: not compared   "
                                            "(click a row to see its full values)", style="Small.TLabel")
        self.legend.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        for widget in (self.listv, self.detail):
            widget.bind("<F3>", lambda _e: self.step(1) or "break")
            widget.bind("<Shift-F3>", lambda _e: self.step(-1) or "break")
        self.bind_all("<Control-f>", lambda _e: self._find_key(), add="+")      # Ctrl+F: the Find box
        self.bind_all("<F3>", lambda _e: self._f3(1), add="+")
        self.bind_all("<Shift-F3>", lambda _e: self._f3(-1), add="+")
        self._apply_zoom()
        self.retheme(self.app.palette)

    def _char_width(self) -> int:
        from tkinter import font
        return font.nametofont("TkDefaultFont", self).measure("0")

    LIST_WIDTHS = {"ok": 28, "group": 120, "train": 130, "status": 220}       # at 100% scaling, normal text

    def rescale(self):
        """Column widths for the display's scaling and the text size (called again when either changes)."""
        from rstools.theme import px
        self._apply_zoom()
        for col, width in self.LIST_WIDTHS.items():
            self.listv.column(col, width=int(px(self, width) * self.zoom_factor()))

    def zoom_factor(self) -> float:
        return (1.12 ** self.zoom) * self.display_ratio

    def _apply_zoom(self):
        """The list and details have a text size of their own: the main text size, zoomed with A- / A+, and
        sized for the display the window is on (a popped-out window can be on a display with other scaling)."""
        from tkinter import font
        from rstools.theme import row_height
        base = font.nametofont("TkDefaultFont", self)
        if "LiveText" not in font.names(self):
            self._live_font = font.Font(self, name="LiveText", exists=False)
        live = font.nametofont("LiveText", self)
        size = int(base.cget("size"))
        scaled = max(6, round(abs(size) * self.zoom_factor()))
        live.configure(family=base.cget("family"), size=scaled if size > 0 else -scaled)
        style = ttk.Style(self)
        style.configure("Live.Treeview", font="LiveText",
                        rowheight=max(row_height(self), live.metrics("linespace") + 6))
        for name in ("listv", "detail"):                  # (the details are built after the first call)
            tv = getattr(self, name, None)
            if tv is not None:
                tv.configure(style="Live.Treeview")
        if hasattr(self, "smaller_btn"):
            self.smaller_btn.state(["!disabled" if self.zoom > ZOOM_MIN else "disabled"])
            self.bigger_btn.state(["!disabled" if self.zoom < ZOOM_MAX else "disabled"])

    def set_zoom(self, zoom: int):
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self.app.opts.live_zoom = self.zoom
        self.app.save_app_settings()
        self.rescale()

    def set_display_ratio(self, ratio: float):
        """The popped-out window moved to a display whose scaling is `ratio` times the main window's."""
        ratio = round(ratio, 3)
        if ratio != self.display_ratio:
            self.display_ratio = ratio
            self.rescale()

    def _layout_picked(self):
        layout = next(k for k, v in LAYOUTS.items() if v == self.layout_box.get())
        self.layout_var.set(layout)
        self.app.opts.live_layout = layout
        self.app.save_app_settings()
        self._apply_layout()

    def _arrange_panes(self):
        """(Re)build the paned window for the chosen layout, with the train list unless it is hidden."""
        old = self.pane
        for pane in list(old.panes()):
            old.forget(pane)
        old.destroy()
        self.pane = ttk.Panedwindow(self.out_holder, orient=_orient(self.layout_var.get()))
        self.pane.pack(fill="both", expand=True)
        if not self.list_hidden.get():
            self.pane.add(self.left, weight=2)
        self.pane.add(self.right, weight=3)
        for pane in (self.left, self.right):             # panes that are not its children must be above it
            pane.lift(self.pane)

    def _apply_layout(self):
        """Side by side or stacked: the same two panes in a paned window turned round (the selection stays)."""
        self._arrange_panes()

    def _list_visibility(self):
        """Hide the train list (details only, Previous / Next in the toolbar) or show it again."""
        self.app.opts.live_list_hidden = self.list_hidden.get()
        self.app.save_app_settings()
        self._arrange_panes()

    def _display_changed(self):
        """Changed rows only was ticked or unticked: show the selected train again."""
        self.app.opts.live_changed_only = self.changed_only.get()
        self.app.save_app_settings()
        self._show_selected()

    def retheme(self, p: dict):
        """Colours of the difference rows and the notes box for the current theme."""
        self.out_holder.configure(background=p["bg"])     # the plain frame that pops out into a window
        for tv in (self.listv, self.detail):
            tv.tag_configure(CHANGED, background=p["d_changed"])
            tv.tag_configure(ADDED, background=p["d_added"])
            tv.tag_configure(REMOVED, background=p["d_removed"])
            tv.tag_configure(ISSUE, background=p["d_issue"])
            tv.tag_configure("muted", foreground=p["d_muted"])
        self.listv.tag_configure("fresh", font="AppBold")
        self.detail.tag_configure("dhead", font="AppBold")
        # the clicked row, right across; configured last so it shows over the difference colours
        self.detail.tag_configure("picked", background=p["select"], foreground=p["select_fg"])
        cw = self._char_width()                              # columns follow the text size
        for col, chars in (("ok", 3), ("group", 16), ("train", 16), ("status", 28)):
            self.listv.column(col, width=chars * cw)
        self.notes.configure(background=p["field"], foreground=p["fg"], highlightbackground=p["border"],
                             insertbackground=p["fg"])

    # ------------------------------------------------------------------ mode and files
    def mode(self) -> str:
        return self.mode_box.picked() or "cwn"          # a group heading counts as its first task

    def _mode_changed(self):
        mode = self.mode()
        try:
            self.app.opts.live_mode = mode
        except AttributeError:
            pass
        spec = FILES[mode]
        shown = {k for k, *_ in spec}
        for key, (lab, box, btn) in self.rows.items():
            if key in shown:
                r = next(i for i, s in enumerate(spec) if s[0] == key)
                lab.configure(text=spec[r][1])
                lab.grid(row=r, column=0, sticky="w", pady=1)
                box.grid(row=r, column=1, sticky="ew", padx=4, pady=1)
                btn.grid(row=r, column=2, pady=1)
                many = spec[r][3]
                btn.configure(text="Add..." if many else "Browse...")       # several prints: each adds to the list
                if many:
                    self.clear_btns[key].grid(row=r, column=3, padx=(4, 0), pady=1)
                else:
                    self.clear_btns[key].grid_remove()
                exts = spec[r][2]
                if self.vars[key].get() and not all(p.lower().endswith(exts) for p in _split(self.vars[key].get())):
                    self.vars[key].set("")
            else:
                lab.grid_remove()
                box.grid_remove()
                btn.grid_remove()
                self.clear_btns[key].grid_remove()
        if mode == "cwn":
            self.days_frame.grid()
        else:
            self.days_frame.grid_remove()
        (self.pax_cb.grid if mode in PASSENGER_MODES else self.pax_cb.grid_remove)()
        for cb in (self.hdr_cb, self.tim_cb):
            (cb.grid if mode in CHECK_MODES else cb.grid_remove)()
        self._clear()

    def _files_changed(self):
        self._days_known = set()
        self.watch = {}
        for cb in self.day_cbs:
            cb.state(["disabled"])

    def _browse(self, key):
        mode = self.mode()
        _k, label, exts, many = next(s for s in FILES[mode] if s[0] == key)
        kinds = " or ".join(dict.fromkeys(_TYPE_NAMES.get(e, e) for e in exts))
        types = [(kinds + " files", " ".join("*" + e for e in exts)), ("All files", "*.*")]
        kw = dict(parent=self, title=label.rstrip(":"), filetypes=types)
        start = os.path.dirname(self.vars[key].get().split(";")[0].strip().strip('"')) or self._last_folder()
        if start and os.path.isdir(start):
            kw["initialdir"] = start
        if many:                                      # added to the files already in the box
            chosen = filedialog.askopenfilenames(**kw)
            if chosen:
                self.vars[key].set(_join(self.vars[key].get(), (os.path.normpath(p) for p in chosen)))
                self._remember_folder(chosen[0])
        else:
            chosen = filedialog.askopenfilename(**kw)
            if chosen:
                self.vars[key].set(os.path.normpath(chosen))
                self._remember_folder(chosen)

    def _last_folder(self) -> str:
        return getattr(self.app.opts, "live_folder", "") or ""

    def _remember_folder(self, path: str):
        try:
            self.app.opts.live_folder = os.path.dirname(os.path.normpath(path))
        except AttributeError:
            pass

    def enable_drag_and_drop(self, dnd_files: str):
        self._dnd = dnd_files
        self._add_drop_target(self)

    def _add_drop_target(self, widget):
        if not self._dnd or isinstance(widget, (tk.Text, ttk.Treeview)):
            return
        key = next((k for k, row in self.rows.items() if widget in row), None)       # a box's whole row
        try:
            widget.drop_target_register(self._dnd)
            widget.dnd_bind("<<Drop>>", lambda e, k=key: self._on_drop(e, k))
        except (tk.TclError, AttributeError):
            return
        for child in widget.winfo_children():
            self._add_drop_target(child)

    def _on_drop(self, event, key=None):
        paths = [os.path.normpath(p) for p in self.tk.splitlist(event.data) if os.path.isfile(p)]
        self.place_files(paths, key)
        return event.action

    def place_files(self, paths, key=None):
        """Dropped on a box: the files go in that box (a box taking several train prints adds them all).
        Dropped anywhere else: they fill this comparison's boxes in order, each by its file type."""
        spec = FILES[self.mode()]
        target = next((s for s in spec if s[0] == key), None)
        if target is not None:
            _k, label, exts, many = target
            fits = [p for p in paths if p.lower().endswith(exts)]
            if fits:
                self.vars[key].set(_join(self.vars[key].get(), fits) if many else fits[0])
                if not many and len(fits) > 1:
                    self.status.configure(text=f"{label.rstrip(':')} takes one file - the first was used.")
                return
            messagebox.showwarning(TITLE, f"The {file_label(label)} box takes {' / '.join(exts)} files.",
                                   parent=self)
            return
        from rstools.dropping import Slot, route_drop
        slots = [Slot(self.vars[k], lambda p, e=exts: p.lower().endswith(e), multi=many) for k, _l, exts, many in spec]
        _placed, left = route_drop(paths, slots, join=lambda fs: _join("", fs))
        if left:
            self.status.configure(text=f"{len(left)} file(s) did not fit a box for this comparison and were left out.")

    def _files(self):
        out = {}
        mode = self.mode()
        for key, label, exts, many in FILES[mode]:
            paths = _split(self.vars[key].get())
            what = file_label(label)
            if not paths and (mode, key) in OPTIONAL:
                continue
            if not paths:
                raise ValueError(f"Choose the {what} file.")
            if not many and len(paths) > 1:
                raise ValueError(f"Choose one file for the {what}.")
            for p in paths:
                if not os.path.isfile(p):
                    raise ValueError(f"This file could not be found:\n{p}")
                if not p.lower().endswith(exts):
                    raise ValueError(f"The {what} should be a {' / '.join(exts)} file:\n{p}")
            out[key] = paths
        return out

    # ------------------------------------------------------------------ saved comparisons
    def get_state(self) -> dict:
        keys = [k for k, *_r in FILES[self.mode()]]
        return {"mode": self.mode(), "files": {k: self.vars[k].get() for k in keys}, "auto": self.auto_var.get(),
                "ignore_source_only": self.ignore_var.get(), "check": self.check_var.get(),
                "passenger_only": self.pax_var.get(), "check_header": self.hdr_var.get(),
                "check_timing": self.tim_var.get()}

    def set_state(self, s: dict):
        if s.get("mode") in self.mode_names:
            self.mode_box.show(s["mode"])
            self._mode_changed()
        for k, v in (s.get("files") or {}).items():
            if k in self.vars and isinstance(v, str):
                self.vars[k].set(v)
        self.auto_var.set(bool(s.get("auto", True)))
        self.ignore_var.set(bool(s.get("ignore_source_only", False)))
        self.check_var.set(bool(s.get("check", True)))
        if isinstance(s.get("passenger_only"), bool):
            self.pax_var.set(s["passenger_only"])
        self.hdr_var.set(s.get("check_header") is not False)
        self.tim_var.set(s.get("check_timing") is not False)
        self._view_changed()

    @staticmethod
    def files_in_state(s: dict) -> list:
        return [p for v in (s.get("files") or {}).values() for p in _split(v)]

    # ------------------------------------------------------------------ days (CWN)
    def _days(self):
        if self.mode() != "cwn" or not self._days_known:
            return None
        ticked = {i for i, v in enumerate(self.day_vars) if v.get()} & self._days_known
        return None if ticked == self._days_known else sorted(ticked)

    def _days_changed(self):
        if self._days_known and not any(v.get() for i, v in enumerate(self.day_vars) if i in self._days_known):
            return
        if self.result is not None:
            self.run(refresh=True)

    def _learn_days(self, files):
        """Days the CWNs cover (for the day tickboxes), once per pair of files. The CWNs were just read for the
        comparison, so their trains come from the app's store of files read rather than being read again."""
        from cwn_compare.days import coverage
        from rstools.timetable.engine import read_jobs

        from .adapters import model_of
        days = set()
        for key in ("a", "b"):
            try:
                path = files[key][0]
                (model,) = read_jobs([(model_of, path)])
                days |= set(coverage(model, path)[0])
            except Exception:
                errorlog.write(f"The days of a CWN could not be read for the day tickboxes:\n{traceback.format_exc()}")
        return days

    # ------------------------------------------------------------------ comparing
    # ------------------------------------------------------------------ own window
    def toggle_window(self):
        if self.window is not None:
            self.window.toggle()

    def window_changed(self, out: bool):
        """The Live View was moved into its own window (out) or back into its tab: show the window's controls."""
        self.pop_btn.configure(text="Bring back" if out else "Pop out")
        if out and self.window is not None:
            self.top_cb.configure(variable=self.window.on_top)
            self.full_btn.configure(text="Leave full screen (Esc)" if self.window.fullscreen else "Full screen (F11)")
            self.full_btn.grid()
            self.top_cb.grid()
        else:
            self.full_btn.grid_remove()
            self.top_cb.grid_remove()

    def display_changed(self):
        """The main window is on a display with other scaling: the list and details follow it."""
        self.rescale()
        if self.window is not None and self.window.out:       # the popped-out window's display, against the new one
            self.window._rescale_for_display()

    def output_place(self, back: bool):
        """The output goes out into its window (the tab keeps a note in its place) or comes back."""
        if back:
            self.out_holder.grid(row=3, column=0, sticky="nsew")
        else:
            self.out_holder.grid_remove()

    def stop(self):
        if self._autosave_after:                      # closing: save the confirmations now
            try:
                self.after_cancel(self._autosave_after)
            except tk.TclError:
                pass
            self._autosave()
        for job in (self._watch_id, getattr(self, "_search_after", None)):
            if not job:
                continue
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    def run(self, refresh: bool = False):
        if self.running:
            return
        try:
            files = self._files()
        except ValueError as exc:
            if not refresh:
                messagebox.showwarning(TITLE, str(exc))
            return
        mode = self.mode()
        if not refresh:
            for key, paths in files.items():
                self.app.add_recent(f"live_{key}", *paths[:1])
        self.running = True
        self.run_btn.state(["disabled"])
        self.progress.begin()
        self.progress.set(0.05)
        self._started = time.monotonic()
        self.status.configure(text="Refreshing..." if refresh else "Comparing...")
        self.app.set_busy(True)
        days = self._days()
        stamps = {p: self._stamp(p) for ps in files.values() for p in ps}
        extra = dict(passenger_only=mode in PASSENGER_MODES and self.pax_var.get(),
                     header=self.hdr_var.get() or mode not in CHECK_MODES,
                     timing=self.tim_var.get() or mode not in CHECK_MODES,
                     loose=bool(getattr(self.app.opts, "ignore_spacing", True)))
        threading.Thread(target=self._work, args=(mode, files, days, refresh, stamps, extra), daemon=True).start()
        self.app.pump.kick()

    @staticmethod
    def _stamp(path):
        try:
            st = os.stat(path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _work(self, mode, files, days, refresh, stamps, extra=None):
        from .adapters import compute
        try:
            res = compute(mode, files, days, log=lambda m: self.q.put(("step", m)), **(extra or {}))
            known = self._learn_days(files) if mode == "cwn" and not self._days_known else None
            self.q.put(("done", mode, res, refresh, stamps, known, files))
        except Exception as exc:                  # readable messages from the readers; details logged
            known_types = ("RunError", "LoadError", "TimetableError", "TimetableRunError", "PrintError",
                           "TrainListError", "StatsPackError", "PackReadError", "TrentFormatError", "ValueError",
                           "Section4Error", "TPRError", "BerthingError", "StationBookError")
            if type(exc).__name__ in known_types:
                msg = str(exc)
            else:
                msg = errorlog.describe(exc)
            self.q.put(("error", msg, refresh, stamps))

    def _finished(self):
        self.running = False
        self.run_btn.state(["!disabled"])
        self.app.set_busy(False)

    def _loaded(self, mode, res, refresh, stamps, known, files=None):
        self._finished()
        if mode != self.mode():
            return
        old = {k: it.signature() for k, it in self.items.items()} if refresh else {}
        self.raw = res
        self.result = res = view(res, self.ignore_var.get(), self.check_var.get())
        self.items = {it.key: it for it in res.items}
        self._restore_progress(mode, files or {})
        self.fresh = {k for k, it in self.items.items() if refresh and old.get(k) != it.signature()}
        self.watch = dict(stamps)
        self._keep_watching()
        if known is not None:
            self._days_known = known
            for i, (cb, var) in enumerate(zip(self.day_cbs, self.day_vars)):
                cb.state(["!disabled"] if i in known else ["disabled"])
                var.set(i in known)
            from cwn_compare.days import label
            self.days_note.configure(text=f"The CWNs cover {label(known)}. Untick days to show only trains "
                                          "running on the ticked days.")
        diffs = sum(1 for it in res.items if it.state in DIFF_STATES)
        stamp = time.strftime("%H:%M:%S")
        took = time.monotonic() - self._started
        if refresh:
            self.status.configure(text=f"Refreshed {stamp} ({took:.1f} s): {len(self.fresh)} item(s) changed since "
                                       f"the last refresh; {diffs} difference(s) in all.")
        else:
            self.status.configure(text=f"Compared {stamp} ({took:.1f} s): {len(res.items)} item(s), {diffs} with "
                                       "differences." + (f" {len(res.warnings)} note(s)." if res.warnings else "")
                                       + (f" {len(self.confirmed)} confirmed earlier (restored)." if self.confirmed
                                          else ""))
        cols = list(res.columns)
        widths = [len(c) for c in cols]                 # columns sized to what they hold
        for it in res.items[:3000]:
            for row in it.rows:
                cap = 24 if row.state == "muted" else 200      # long train details (operator name...) may be
                for i, cell in enumerate(row.cells[:len(cols)]):   # cut short rather than widen every column
                    widths[i] = max(widths[i], min(cap, len(str(cell))))
        self.detail.configure(columns=[f"c{i}" for i in range(len(cols))])
        for i, name in enumerate(cols):
            self.detail.heading(f"c{i}", text=name)
            cw = self._char_width()
            self.detail.column(f"c{i}", width=max(6 * cw, min(52 * cw, cw * widths[i] + 2 * cw)), anchor="w",
                               stretch=i == len(cols) - 1)    # columns keep their widths (scroll sideways if
                                                              # wider than the pane); the last takes any spare
        self._fill_list()
        self.export_btn.state(["!disabled"] if res.items else ["disabled"])
        if not refresh:
            self.app.notify_done("Live View ready", f"{len(res.items)} item(s), {diffs} with differences.")

    # ------------------------------------------------------------------ export
    def export(self):
        """Save the trains listed (filter and search applied) and their differences."""
        if not self.items or self.result is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Export the Live View", defaultextension=".xlsx",
            initialfile=f"Live View {time.strftime('%d-%m-%Y %H%M')}", initialdir=self._export_folder(),
            filetypes=[("Excel workbook", "*.xlsx"), ("PDF", "*.pdf"), ("Word document", "*.docx")])
        if not path:
            return
        from rstools.fsutil import NETWORK_REFUSED, is_network_path
        if is_network_path(path):                       # outputs are only ever saved on this PC
            messagebox.showwarning(TITLE, NETWORK_REFUSED, parent=self)
            return
        items = list(self._visible())
        res, filt, find = self.result, self.filter_box.get(), self.search.get().strip()
        confirmed = set(self.confirmed) & set(self.items)
        self.status.configure(text="Exporting...")

        def work():
            try:
                from .export import export
                export(path, res, items, filt, find, confirmed)
                self.q.put(("exported", path, ""))
            except Exception as exc:
                self.q.put(("exported", path, errorlog.file_problem(exc) or f"The export failed: {exc}"))
        threading.Thread(target=work, daemon=True).start()
        self.app.pump.kick()

    def _export_folder(self) -> str:
        """The app's output folder (the 'Save to folder' chosen, else Downloads)."""
        from rstools.fsutil import output_folder
        try:
            return output_folder(getattr(self.app.opts, "output_dir", "") or "")
        except Exception:
            return ""

    def _clear(self):
        self.result, self.raw, self.items, self.fresh, self.watch = None, None, {}, set(), {}
        self.confirmed, self.reopened, self._progress_for = {}, set(), ""
        if hasattr(self, "progress_lbl"):
            self.progress_lbl.configure(text="")
        self._days_known = set()
        for cb in self.day_cbs:
            cb.state(["disabled"])
        self.export_btn.state(["disabled"])
        self.listv.delete(*self.listv.get_children())
        self.detail.delete(*self.detail.get_children())
        self.head.configure(text="")
        self._set_notes([])
        self.count_lbl.configure(text="")
        if not self.running:
            self.status.configure(text="Choose the files and press Compare (F5).")

    # ------------------------------------------------------------------ list and detail
    def _search_soon(self):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(250, self._fill_list)

    def _view_changed(self):
        """A toggle changed: show the same comparison again with it (no need to read the files again)."""
        if not self.check_var.get() and self.filter_box.get() == "Differences only":
            self.filter_box.set("All")                 # paired trains are what is checked by eye
        elif self.check_var.get() and self.filter_box.get() == "Paired (check by eye)":
            self.filter_box.set("Differences only")
        if self.raw is None:
            return
        self.result = view(self.raw, self.ignore_var.get(), self.check_var.get())
        self.items = {it.key: it for it in self.result.items}
        self.fresh &= set(self.items)
        self._fill_list()

    def _visible(self):
        want = FILTERS[self.filter_box.get()]
        text = self.search.get().strip().casefold()
        for it in self.items.values():
            if want == "fresh":
                if it.key not in self.fresh:
                    continue
            elif want == "unconfirmed":
                if it.key in self.confirmed:
                    continue
            elif want == "confirmed":
                if it.key not in self.confirmed:
                    continue
            elif want == "reopened":
                if it.key not in self.reopened:
                    continue
            elif want is not None and it.state not in want:
                continue
            if text and text not in f"{it.group} {it.label} {it.status}".casefold():
                continue
            yield it

    def _fill_list(self):
        self._search_after = None
        keep = self.listv.selection()
        self.listv.delete(*self.listv.get_children())
        shown = 0
        total = 0
        for it in self._visible():
            total += 1
            if shown >= MAX_LIST:
                continue
            tags = (it.state,) + (("fresh",) if it.key in self.fresh else ())
            self.listv.insert("", "end", iid=it.key, values=(self._tick(it.key), it.group,
                                                             ("* " if it.key in self.fresh else "") + it.label,
                                                             it.status), tags=tags)
            shown += 1
        extra = f" (first {MAX_LIST:,} shown - search to narrow)" if total > shown else ""
        self.count_lbl.configure(text=f"{total:,} shown of {len(self.items):,}{extra}")
        self._progress_text()
        target = keep[0] if keep and self.listv.exists(keep[0]) else None
        if target is None:
            kids = self.listv.get_children()
            target = kids[0] if kids else None
        if target:
            self.listv.selection_set(target)
            self.listv.see(target)
        else:
            self.detail.delete(*self.detail.get_children())
            self.head.configure(text="Nothing to show" if self.items else "")
            self._set_notes([])

    # ------------------------------------------------------------------ confirmations (manual checking)
    def _tick(self, key: str) -> str:
        return TICK if key in self.confirmed else ("!" if key in self.reopened else "")

    def _progress_text(self):
        if not self.items:
            self.progress_lbl.configure(text="")
            return
        done = len(set(self.confirmed) & set(self.items))
        text = f"{done:,} of {len(self.items):,} confirmed"
        if self.reopened:
            text += f"; {len(self.reopened)} changed since confirmed (!)"
        self.progress_lbl.configure(text=text)

    def _list_click(self, event):
        if self.listv.identify_column(event.x) == "#1" and self.listv.identify_region(event.x, event.y) == "cell":
            row = self.listv.identify_row(event.y)
            if row:
                self.toggle_confirmed(row)

    def toggle_confirmed(self, key: str = ""):
        """Tick (or untick) a train as confirmed: the selected one, or `key`."""
        from .progress import fingerprint
        if not key:
            sel = self.listv.selection()
            key = sel[0] if sel else ""
        it = self.items.get(key)
        if it is None:
            return
        if key in self.confirmed:
            del self.confirmed[key]
        else:
            self.confirmed[key] = fingerprint(it)
            self.reopened.discard(key)
        if self.listv.exists(key):
            self.listv.set(key, "ok", self._tick(key))
        self._progress_text()
        self._autosave_soon()

    def _files_now(self) -> Dict[str, List[str]]:
        return {k: _split(self.vars[k].get()) for k, *_r in FILES[self.mode()] if _split(self.vars[k].get())}

    def _restore_progress(self, mode: str, files: Dict[str, List[str]]):
        """After a comparison: the confirmations for these files (restored from the automatic save the first time),
        checked against what is shown now."""
        from .progress import comparison_id, load_auto, reconcile
        ident = comparison_id(mode, files) if files else ""
        if ident != self._progress_for:
            self._progress_for = ident
            saved = load_auto(mode, files) if files else None
            self.confirmed = dict(saved["confirmed"]) if saved else {}
            self.reopened = set(saved["changed"]) if saved else set()
        kept, changed = reconcile(self.confirmed, self.items.values())
        if changed:
            self.confirmed = kept
            self.reopened |= changed
            self._autosave_soon()

    def _autosave_soon(self):
        if self._autosave_after:
            self.after_cancel(self._autosave_after)
        self._autosave_after = self.after(800, self._autosave)

    def _autosave(self):
        from .progress import autosave_path, save
        self._autosave_after = None
        files = self._files_now()
        if files and self.items:
            save(autosave_path(self.mode(), files), self.mode(), files, self.confirmed, self.get_state(),
                 self.reopened)

    def save_progress(self):
        """Save the files, options and confirmations to a file (to carry on later or pass to a colleague)."""
        from .progress import save
        if not self.items:
            messagebox.showinfo(TITLE, "Compare first, then save your progress.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="Save Live View progress", defaultextension=".json",
                                            initialfile=f"Live View progress {time.strftime('%d-%m-%Y %H%M')}",
                                            filetypes=[("Live View progress", "*.json")])
        if not path:
            return
        from rstools.fsutil import is_network_path, NETWORK_REFUSED
        if is_network_path(path):
            messagebox.showwarning(TITLE, NETWORK_REFUSED, parent=self)
            return
        if save(path, self.mode(), self._files_now(), self.confirmed, self.get_state(), self.reopened):
            self.status.configure(text=f"Progress saved: {path}")
        else:
            messagebox.showerror(TITLE, f"The progress could not be saved to:\n{path}", parent=self)

    def load_progress(self):
        """Load saved progress: the same files and options, compared again, with the confirmations restored."""
        from .progress import comparison_id, load
        path = filedialog.askopenfilename(parent=self, title="Load Live View progress",
                                          filetypes=[("Live View progress", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = load(path)
        except ValueError as exc:
            messagebox.showerror(TITLE, str(exc), parent=self)
            return
        state = dict(data["state"])
        state.setdefault("mode", data["mode"])
        state["files"] = {k: SEP.join(v) for k, v in data["files"].items()}
        self.set_state(state)
        self.confirmed, self.reopened = dict(data["confirmed"]), set(data["changed"])
        self._progress_for = comparison_id(self.mode(), self._files_now())
        self._autosave_soon()
        self.status.configure(text=f"Progress loaded ({len(self.confirmed)} confirmed, saved {data['saved']}).")
        self.run()

    def _checks_changed(self):
        self.app.opts.live_check_header = self.hdr_var.get()
        self.app.opts.live_check_timing = self.tim_var.get()
        self.app.save_app_settings()
        if self.result is not None:
            self.run(refresh=True)

    def _pax_changed(self):
        self.app.opts.live_passenger_only = self.pax_var.get()
        self.app.save_app_settings()
        if self.result is not None:
            self.run(refresh=True)

    def _show_selected(self):
        sel = self.listv.selection()
        it = self.items.get(sel[0]) if sel else None
        self.detail.delete(*self.detail.get_children())
        if it is None:
            return
        self.head.configure(text=f"{it.label}  -  {it.status}   ({it.group})")
        self._rows, self._details_iid = {}, ""
        only = self.changed_only.get()
        shown = [r for r in it.rows if not only or r.state not in (SAME, "muted")]
        details = [r for r in it.rows if r.group == "details"]
        if details and (not only or any(r in shown for r in details)):
            # train prints: the train's details under one heading
            self._details_iid = self.detail.insert("", "end", values=self._details_label(details),
                                                   open=self._details_open(), tags=self._details_tags(details))
        for row in shown:
            parent = self._details_iid if row.group == "details" else ""
            iid = self.detail.insert(parent, "end", values=row.cells, tags=(row.state,) if row.state != SAME else ())
            self._rows[iid] = row
        if only and it.rows and not shown:
            self.detail.insert("", "end", values=["(every row is the same on both sides)"]
                               + [""] * (len(self.result.columns) - 1 if self.result else 0), tags=("muted",))
        self._item_notes = it.notes or ([it.status] if it.state != SAME else ["No differences."])
        self._set_notes(self._item_notes)

    # ------------------------------------------------------------------ train details (fold) and picked rows
    def _details_open(self) -> bool:
        return bool(getattr(self.app.opts, "live_details_open", False))

    def _fit(self, options, column: str) -> str:
        """The first of `options` that fits the column (the last, shortest one if none does)."""
        from tkinter import font
        f = font.nametofont("AppBold" if "AppBold" in font.names(self) else "TkDefaultFont", self)
        room = int(self.detail.column(column, "width")) - 2 * self._char_width()
        return next((t for t in options if f.measure(t) <= room), options[-1])

    def _details_label(self, details):
        differ = sum(1 for r in details if r.state not in (SAME, "muted"))
        arrow = "▼ " if self._details_open() else "▶ "
        title = self._fit([arrow + "Train Header Details", arrow + "Header Details", arrow + "Header"], "c0")
        info = (f"{len(details)} items" + (f" - {differ} differ" if differ else "")
                + ("" if self._details_open() else "   (click to show)"))
        cells = [title] + [""] * (len(self.result.columns) - 1 if self.result else 0)
        if len(cells) > 2:
            cells[2] = info                        # in a wide column: nothing is clipped by the next one
        else:
            cells[0] = title + f" ({len(details)})"
        return cells

    def _details_tags(self, details):
        return ("dhead",) + ((CHANGED,) if any(r.state not in (SAME, "muted") for r in details) else ())

    def _toggle_details(self):
        self.app.opts.live_details_open = not self._details_open()
        self.app.save_app_settings()
        iid = self._details_iid
        details = [self._rows[k] for k in self.detail.get_children(iid)]
        self.detail.item(iid, open=self._details_open(), values=self._details_label(details))

    def _detail_click(self, event):
        if self._details_iid and self.detail.identify_row(event.y) == self._details_iid:
            self.detail.selection_remove(self._details_iid)
            self._toggle_details()

    def _row_picked(self):
        """A row clicked: highlighted right across (original and updated side by side), with its full values in
        the notes below; the train-details heading folds or unfolds instead."""
        sel = self.detail.selection()
        if not sel:
            return
        if sel[0] == self._details_iid:
            self._set_notes(["Train Header Details: click the heading (or press Enter) to show or hide them.", ""]
                            + list(getattr(self, "_item_notes", [])))
            return
        row = self._rows.get(sel[0])
        if row is None or self.result is None:
            return
        for iid in self.detail.tag_has("picked"):
            self.detail.item(iid, tags=tuple(t for t in self.detail.item(iid, "tags") if t != "picked"))
        self.detail.item(sel[0], tags=tuple(self.detail.item(sel[0], "tags")) + ("picked",))
        cols = self.result.columns
        shown = [f"{c}: {v}" for c, v in zip(cols, row.cells) if str(v).strip()]
        self._set_notes(["Selected row - " + "   |   ".join(shown), ""] + list(getattr(self, "_item_notes", [])))

    def _set_notes(self, lines):
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("end", "\n".join(lines))
        self.notes.configure(state="disabled")

    def _find_key(self):
        if self.winfo_ismapped() or self.out_holder.winfo_ismapped():
            self.find_entry.focus_set()
            self.find_entry.select_range(0, "end")
            return "break"
        return None

    def _f3(self, direction):
        if self.winfo_ismapped() and self.items:
            self.step(direction)
        return None

    def step(self, direction: int):
        """Select the next (or previous) train with differences in the list."""
        kids = list(self.listv.get_children())
        if not kids:
            return
        sel = self.listv.selection()
        i = kids.index(sel[0]) if sel and sel[0] in kids else -1
        for j in range(1, len(kids) + 1):
            k = kids[(i + direction * j) % len(kids)]
            if self.items[k].state in DIFF_STATES:
                self.listv.selection_set(k)
                self.listv.see(k)
                self.listv.focus(k)
                return

    # ------------------------------------------------------------------ watching the files
    def _watch_files(self):
        """Re-run the comparison when a compared file has been saved (and has stopped changing)."""
        try:
            if self.auto_var.get() and self.result is not None and not self.running and self.watch:
                changed = [p for p, st in self.watch.items() if self._stamp(p) != st]
                if changed:
                    now = tuple((p, self._stamp(p)) for p in changed)
                    if now == self._pending_change and all(s is not None for _p, s in now):
                        self._pending_change = None
                        self.run(refresh=True)          # unchanged since the last check: the save is complete
                    else:
                        self._pending_change = now
        finally:
            self._watch_id = None
            self._keep_watching()

    def _keep_watching(self):
        """Look for saved files every POLL_MS while a comparison is shown with 'Refresh when a file is saved'
        ticked; otherwise no timer runs."""
        if self._watch_id is None and self.auto_var.get() and self.result is not None and self.watch:
            self._watch_id = self.after(POLL_MS, self._watch_files)

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "step":                    # each step read or compared moves the bar on
                    self.progress.set(self.progress.value + (0.9 - self.progress.value) * 0.3)
                elif item[0] == "done":
                    self.progress.finish()
                    self._loaded(*item[1:])
                elif item[0] == "exported":
                    _k, path, err = item
                    if err:
                        self.status.configure(text=err)
                        messagebox.showerror(TITLE, err)
                    else:
                        from rstools.fsutil import excel_warning
                        warn = excel_warning([path])
                        self.status.configure(text=f"Exported to {path}")
                        if warn:
                            messagebox.showwarning(TITLE, warn)
                        self.app.open_outputs([path])
                elif item[0] == "error":
                    _k, msg, refresh, stamps = item
                    self._finished()
                    if refresh:                          # e.g. a file saved while half-written: try later
                        self.watch.update(stamps)
                        self._keep_watching()
                        self.status.configure(text=f"Refresh failed at {time.strftime('%H:%M:%S')}: "
                                                   f"{msg.splitlines()[0]} - will try again when the file is saved.")
                    else:
                        self.status.configure(text="Comparison failed - see the message.")
                        self.app.notify_done("Live View failed", msg.splitlines()[0], False)
                        messagebox.showerror(TITLE, msg[:1500])
        except queue.Empty:
            pass
