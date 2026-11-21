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
import time
import tkinter as tk
from typing import Dict, List, Tuple
from tkinter import ttk, filedialog, messagebox

from rstools import errorlog, theme
from rstools.branding import APP_NAME
from rstools.naming import file_label

from .model import ADDED, CHANGED, DIFF_STATES, ISSUE, PAIRED, REMOVED, SAME, view

TITLE = f"{APP_NAME} - Live View"
_XL, _PR, _LI = (".xlsx", ".xlsm"), (".pdf", ".docx", ".docm"), (".xlsx", ".xlsm", ".csv")
_CWN = (".xlsx", ".xlsm", ".xls", ".xlsb")
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
    "prints": [("a", "Original train print(s):", _PR, True), ("b", "Updated train print(s):", _PR, True)],
    "lists": [("a", "Original Attune train list:", _LI, False), ("b", "Updated Attune train list:", _LI, False)],
}
FILTERS = {"Differences only": DIFF_STATES, "All": None, "Paired (check by eye)": (PAIRED,),
           "Changed": (CHANGED,), "Issues": (ISSUE,),
           "Added": (ADDED,), "Removed / missing": (REMOVED,), "Unchanged": (SAME,),
           "Updated by the last refresh": "fresh"}
MAX_LIST = 20000                    # rows put in the list at once (search or filter to narrow a bigger result)
SEP = " ; "
POLL_MS = 1500


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
        self._build()
        self._mode_changed()
        self._poll_id = self.after(100, self._poll)
        self._watch_id = self.after(POLL_MS, self._watch_files)

    # ------------------------------------------------------------------ UI
    def _build(self):
        from .adapters import MODES
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text="Live View", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        theme.tip(ttk.Label(self, text="Browse any comparison train by train: click a train to see it side by side "
                                       "with its match and every difference. Tick 'Refresh when a file is saved' to "
                                       "see changes as you save the files.", style="Small.TLabel", wraplength=1100,
                            justify="left")).grid(
            row=1, column=0, sticky="w", pady=(0, 6))

        top = ttk.Frame(self)
        top.grid(row=2, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Compare:").grid(row=0, column=0, sticky="w")
        self.mode_names = dict(MODES)
        self.mode_box = ttk.Combobox(top, values=list(MODES.values()), state="readonly", width=52)
        self.mode_box.set(MODES["cwn"])
        self.mode_box.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        self.mode_box.bind("<<ComboboxSelected>>", lambda _e: self._mode_changed())
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
        self.prog = ttk.Progressbar(ctl, mode="indeterminate", length=120)
        self.prog.grid(row=0, column=2, padx=(12, 0))
        self.prog.grid_remove()                       # shown only while comparing
        self.status = ttk.Label(ctl, text="Choose the files and press Compare (F5).", style="Small.TLabel")
        self.status.grid(row=0, column=3, sticky="w", padx=(10, 0))

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=3, column=0, sticky="nsew")
        left, right = ttk.Frame(pane, padding=(0, 0, 6, 0)), ttk.Frame(pane, padding=(6, 0, 0, 0))
        pane.add(left, weight=2)
        pane.add(right, weight=3)

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
        self._search_after = None
        self.search.trace_add("write", lambda *_a: self._search_soon())
        self.listv = ttk.Treeview(left, columns=("group", "train", "status"), show="headings", selectmode="browse")
        for col, text in (("group", "Section / tab"), ("train", "Train"), ("status", "Status")):
            self.listv.heading(col, text=text)
            self.listv.column(col, anchor="w", stretch=col == "status")
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

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.head = ttk.Label(right, text="", style="Head.TLabel", wraplength=640, justify="left")
        self.head.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.detail = ttk.Treeview(right, show="headings", selectmode="browse")
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
        self.notes = tk.Text(right, height=6, wrap="word", font="TkFixedFont", state="disabled", relief="flat",
                             borderwidth=1, highlightthickness=1)
        self.notes.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.legend = ttk.Label(right, text="Yellow: changed   Green: added   Red: removed / missing   Orange: issue   "
                                            "Grey: not compared\nClick a row to highlight it "
                                            "and see its full values above.", style="Small.TLabel")
        self.legend.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        for widget in (self.listv, self.detail):
            widget.bind("<F3>", lambda _e: self.step(1) or "break")
            widget.bind("<Shift-F3>", lambda _e: self.step(-1) or "break")
        self.bind_all("<F3>", lambda _e: self._f3(1), add="+")
        self.bind_all("<Shift-F3>", lambda _e: self._f3(-1), add="+")
        self.retheme(self.app.palette)

    def _char_width(self) -> int:
        from tkinter import font
        return font.nametofont("TkDefaultFont", self).measure("0")

    LIST_WIDTHS = {"group": 120, "train": 130, "status": 220}       # at 100% scaling, normal text

    def rescale(self):
        """Column widths for the display's scaling and the text size (called again when either changes)."""
        from rstools.theme import px
        for col, width in self.LIST_WIDTHS.items():
            self.listv.column(col, width=px(self, width))

    def retheme(self, p: dict):
        """Colours of the difference rows and the notes box for the current theme."""
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
        for col, chars in (("group", 16), ("train", 16), ("status", 28)):
            self.listv.column(col, width=chars * cw)
        self.notes.configure(background=p["field"], foreground=p["fg"], highlightbackground=p["border"],
                             insertbackground=p["fg"])

    # ------------------------------------------------------------------ mode and files
    def mode(self) -> str:
        label = self.mode_box.get()
        return next(k for k, v in self.mode_names.items() if v == label)

    def _mode_changed(self):
        mode = self.mode()
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
        self._clear()

    def _files_changed(self):
        self._days_known = set()
        self.watch = {}
        for cb in self.day_cbs:
            cb.state(["disabled"])

    def _browse(self, key):
        mode = self.mode()
        _k, label, exts, many = next(s for s in FILES[mode] if s[0] == key)
        types = [("Files", " ".join("*" + e for e in exts)), ("All files", "*.*")]
        kw = dict(parent=self, title=label.rstrip(":"), filetypes=types)
        if many:                                      # added to the files already in the box
            chosen = filedialog.askopenfilenames(**kw)
            if chosen:
                self.vars[key].set(_join(self.vars[key].get(), (os.path.normpath(p) for p in chosen)))
        else:
            chosen = filedialog.askopenfilename(**kw)
            if chosen:
                self.vars[key].set(os.path.normpath(chosen))

    def enable_drag_and_drop(self, dnd_files: str):
        self._dnd = dnd_files
        self._add_drop_target(self)

    def _add_drop_target(self, widget):
        if not self._dnd or isinstance(widget, (tk.Text, ttk.Treeview)):
            return
        key = next((k for k, (_l, box, _b) in self.rows.items() if box is widget), None)
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
        for key, _label, exts, many in spec:
            fits = [p for p in paths if p.lower().endswith(exts)]
            if not fits:
                continue
            if many and len([s for s in spec if s[2] == exts]) == 1:
                self.vars[key].set(_join(self.vars[key].get(), fits))
                paths = [p for p in paths if p not in fits]
            elif not self.vars[key].get().strip() or len(paths) > 1:
                self.vars[key].set(fits[0])
                paths.remove(fits[0])

    def _files(self):
        out = {}
        for key, label, exts, many in FILES[self.mode()]:
            paths = _split(self.vars[key].get())
            what = file_label(label)
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
                "ignore_source_only": self.ignore_var.get(), "check": self.check_var.get()}

    def set_state(self, s: dict):
        if s.get("mode") in self.mode_names:
            self.mode_box.set(self.mode_names[s["mode"]])
            self._mode_changed()
        for k, v in (s.get("files") or {}).items():
            if k in self.vars and isinstance(v, str):
                self.vars[k].set(v)
        self.auto_var.set(bool(s.get("auto", True)))
        self.ignore_var.set(bool(s.get("ignore_source_only", False)))
        self.check_var.set(bool(s.get("check", True)))
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
        """Days the CWNs cover (for the day tickboxes), once per pair of files."""
        from cwn_compare.days import read_days
        days = set()
        for key in ("a", "b"):
            try:
                found, _assumed = read_days(files[key][0])
                days |= set(found)
            except Exception:
                pass
        return days

    # ------------------------------------------------------------------ comparing
    def stop(self):
        for job in (self._poll_id, self._watch_id, getattr(self, "_search_after", None)):
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
        self.prog.grid()
        self.prog.start(12)
        self._started = time.monotonic()
        self.status.configure(text="Refreshing..." if refresh else "Comparing...")
        self.app.set_busy(True)
        days = self._days()
        stamps = {p: self._stamp(p) for ps in files.values() for p in ps}
        threading.Thread(target=self._work, args=(mode, files, days, refresh, stamps), daemon=True).start()

    @staticmethod
    def _stamp(path):
        try:
            st = os.stat(path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _work(self, mode, files, days, refresh, stamps):
        from .adapters import compute
        try:
            res = compute(mode, files, days, log=lambda m: None)
            known = self._learn_days(files) if mode == "cwn" and not self._days_known else None
            self.q.put(("done", mode, res, refresh, stamps, known))
        except Exception as exc:                  # readable messages from the readers; details logged
            known_types = ("RunError", "LoadError", "TimetableError", "TimetableRunError", "PrintError",
                           "TrainListError", "StatsPackError", "PackReadError", "TrentFormatError", "ValueError")
            if type(exc).__name__ in known_types:
                msg = str(exc)
            else:
                msg = errorlog.describe(exc)
            self.q.put(("error", msg, refresh, stamps))

    def _finished(self):
        self.running = False
        self.run_btn.state(["!disabled"])
        self.prog.stop()
        self.prog.grid_remove()
        self.app.set_busy(False)

    def _loaded(self, mode, res, refresh, stamps, known):
        self._finished()
        if mode != self.mode():
            return
        old = {k: it.signature() for k, it in self.items.items()} if refresh else {}
        self.raw = res
        self.result = res = view(res, self.ignore_var.get(), self.check_var.get())
        self.items = {it.key: it for it in res.items}
        self.fresh = {k for k, it in self.items.items() if refresh and old.get(k) != it.signature()}
        self.watch = dict(stamps)
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
                                       "differences." + (f" {len(res.warnings)} note(s)." if res.warnings else ""))
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
            initialfile=f"Live View {time.strftime('%d-%m-%Y %H%M')}",
            filetypes=[("Excel workbook", "*.xlsx"), ("PDF", "*.pdf"), ("Word document", "*.docx")])
        if not path:
            return
        items = list(self._visible())
        res, filt, find = self.result, self.filter_box.get(), self.search.get().strip()
        self.status.configure(text="Exporting...")

        def work():
            try:
                from .export import export
                export(path, res, items, filt, find)
                self.q.put(("exported", path, ""))
            except Exception as exc:
                self.q.put(("exported", path, errorlog.file_problem(exc) or f"The export failed: {exc}"))
        threading.Thread(target=work, daemon=True).start()

    def _clear(self):
        self.result, self.raw, self.items, self.fresh, self.watch = None, None, {}, set(), {}
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
            self.listv.insert("", "end", iid=it.key, values=(it.group, ("* " if it.key in self.fresh else "")
                                                             + it.label, it.status), tags=tags)
            shown += 1
        extra = f" (first {MAX_LIST:,} shown - search to narrow)" if total > shown else ""
        self.count_lbl.configure(text=f"{total:,} shown of {len(self.items):,}{extra}")
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

    def _show_selected(self):
        sel = self.listv.selection()
        it = self.items.get(sel[0]) if sel else None
        self.detail.delete(*self.detail.get_children())
        if it is None:
            return
        self.head.configure(text=f"{it.label}  -  {it.status}   ({it.group})")
        self._rows, self._details_iid = {}, ""
        details = [r for r in it.rows if r.group == "details"]
        if details:                                 # train prints: the train's details under one heading
            self._details_iid = self.detail.insert("", "end", values=self._details_label(details),
                                                   open=self._details_open(), tags=self._details_tags(details))
        for row in it.rows:
            parent = self._details_iid if row.group == "details" else ""
            iid = self.detail.insert(parent, "end", values=row.cells, tags=(row.state,) if row.state != SAME else ())
            self._rows[iid] = row
        self._item_notes = it.notes or ([it.status] if it.state != SAME else ["No differences."])
        self._set_notes(self._item_notes)

    # ------------------------------------------------------------------ train details (fold) and picked rows
    def _details_open(self) -> bool:
        return bool(getattr(self.app.opts, "live_details_open", True))

    def _details_label(self, details):
        differ = sum(1 for r in details if r.state not in (SAME, "muted"))
        text = (("▼ " if self._details_open() else "▶ ") + f"Train details ({len(details)})"
                + (f" - {differ} differ" if differ else "") + ("" if self._details_open() else "  (click to show)"))
        return [text] + [""] * (len(self.result.columns) - 1 if self.result else 0)

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
            self._set_notes(["Train details: click the heading (or press Enter) to show or hide them.", ""]
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
            self._watch_id = self.after(POLL_MS, self._watch_files)

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "done":
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
                        self.status.configure(text=f"Refresh failed at {time.strftime('%H:%M:%S')}: "
                                                   f"{msg.splitlines()[0]} - will try again when the file is saved.")
                    else:
                        self.status.configure(text="Comparison failed - see the message.")
                        self.app.notify_done("Live View failed", msg.splitlines()[0], False)
                        messagebox.showerror(TITLE, msg[:1500])
        except queue.Empty:
            pass
        finally:
            self._poll_id = self.after(100, self._poll)
