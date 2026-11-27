"""'Timing Tools' tab of the Train Planning Tools window."""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from rstools import errorlog, theme, icons
from rstools.widgets import (FAILED, READY, STOPPED, Placeholder, Progress, TaskBox, Tooltip, debounce,
                             duration, local_folder_box, log_box)
from rstools.branding import APP_NAME, settings_dir
from rstools.naming import file_label, plural
from rstools.fsutil import output_folder, write_json

from .engine import MODES, TimetableRunError, default_name, run

TITLE = f"{APP_NAME} - Timing Tools"
MODE_TEXT = {
    "timetables": ("Check the GTR timetable against the Network Rail timetable", "Check timetable"),
    "print_tt": ("Check a timetable against train prints (Attune Single Train Report)", "Check timetable"),
    "list_tt": ("Check a timetable against an Attune train list", "Check timetable"),
    "prints": ("Compare two sets of train prints (PDF or Word) or Attune VPT exports", "Compare train prints"),
    "lists": ("Compare two Attune train list exports (Excel or CSV)", "Compare train lists"),
    "s4docs": ("Compare two sets of Section 4 documents (PDF)", "Compare Section 4 documents"),
    "tprs": ("Compare two sets of Timetable Planning Rules (PDF)", "Compare TPRs"),
}
SIDES = {
    "timetables": ("GTR timetable:", "Network Rail timetable:"),
    "print_tt": ("Train print(s) - reference:", "Timetable to check:"),
    "list_tt": ("Attune train list - reference:", "Timetable to check:"),
    "prints": ("Original train print(s) or VPT:", "Updated train print(s) or VPT:"),
    "lists": ("Original Attune train list:", "Updated Attune train list:"),
    "s4docs": ("Original Section 4 PDF(s):", "Updated Section 4 PDF(s):"),
    "tprs": ("Original TPR PDF(s):", "Updated TPR PDF(s):"),
}
_XL, _PR, _LI = (".xlsx", ".xlsm"), (".pdf", ".docx", ".docm"), (".xlsx", ".xlsm", ".csv")
_PV = _PR + (".vpt",)                                   # two sets of train prints: or Attune VPT exports
_FT = {_PV: [("Train prints and VPT exports", "*.pdf *.docx *.docm *.vpt"), ("PDF", "*.pdf"),
             ("Word", "*.docx *.docm"),
             ("Attune VPT export", "*.vpt"), ("All files", "*.*")],
       _XL: [("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")],
       _PR: [("Train prints", "*.pdf *.docx *.docm"), ("PDF", "*.pdf"), ("Word", "*.docx *.docm"),
             ("All files", "*.*")],
       _LI: [("Excel workbook or CSV", "*.xlsx *.xlsm *.csv"), ("All files", "*.*")],
       (".pdf",): [("PDF", "*.pdf"), ("All files", "*.*")]}
EXTS = {"timetables": (_XL, _XL), "print_tt": (_PR, _XL), "list_tt": (_LI, _XL), "prints": (_PV, _PV),
        "lists": (_LI, _LI), "s4docs": ((".pdf",), (".pdf",)), "tprs": ((".pdf",), (".pdf",))}
MULTI = {"print_tt": (True, False), "prints": (True, True), "s4docs": (True, True),     # boxes that take several
         "tprs": (True, True)}                                                          # files
SEP = " ; "
S4 = "section4"                 # Utilities: the Section 4 possession check
TASK_GROUPS = [          # the Task list: each group in the order the work goes
    ("Timetable checks", [("timetables", MODE_TEXT["timetables"][0]), ("print_tt", MODE_TEXT["print_tt"][0]),
                          ("list_tt", MODE_TEXT["list_tt"][0])]),
    ("Train prints and lists", [("prints", MODE_TEXT["prints"][0]), ("lists", MODE_TEXT["lists"][0])]),
    ("Section 4 and Planning Rules", [(S4, "Check an Attune XML against Section 4 possessions"),
                                      ("s4docs", MODE_TEXT["s4docs"][0]), ("tprs", MODE_TEXT["tprs"][0])]),
]


def is_section4(path: str) -> bool:
    """A Section 4 (Engineering Access Statement) PDF, judged from its first page."""
    if not path.lower().endswith(".pdf"):
        return False
    try:                                    # pypdf (pure Python): PDFium only ever runs in helper processes
        from pypdf import PdfReader

        from rstools import limits
        limits.check_pdf(path)
        reader = PdfReader(path)
        text = reader.pages[0].extract_text() if len(reader.pages) else ""
    except Exception:
        return False
    return "Engineering Access Statement" in text and "Section 4" in text


def _settings_path() -> str:
    return os.path.join(settings_dir(), "timetable.json")


def split_paths(text: str) -> list:
    return [p.strip().strip('"') for p in text.split(SEP.strip()) if p.strip().strip('"')]


def sheet_names(path: str) -> list[str]:
    """The workbook's sheet names, in order, read from its index part alone - the same names openpyxl
    gives, without loading the shared strings and styles (a big workbook took up to half a second)."""
    import zipfile
    from rstools import safexml
    from rstools.fsutil import check_zip
    with zipfile.ZipFile(path) as z:
        check_zip(z, "xl/workbook.xml")     # refuse a 'zip bomb' before unpacking
        root = safexml.fromstring(z.read("xl/workbook.xml"), "xl/workbook.xml")
    return [el.get("name") or "" for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "sheet"]


def sniff_timetable(path: str) -> str:
    """'nr' for a Network Rail timetable table, 'gtr' for a GTR timetable check workbook, '' otherwise
    (judged from the sheet names, which is quick)."""
    try:
        names = sheet_names(path)
    except Exception:
        return ""
    if any(re.search(r"notes$", n, re.I) or re.match(r"^(OUT|RTN)_", n) for n in names):
        return "nr"
    if any(re.search(r"\b(OUT|RTN)\s+(SX|SO|SUO|SU)\b", n, re.I) for n in names):
        return "gtr"
    return ""


class TimetableTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(12, 8, 12, 10))
        self.app = app
        from rstools.cancel import StopQueue
        self.q: "queue.Queue" = StopQueue()
        self.running = False
        self.outputs = []
        self._started = 0.0
        self._dnd = ""
        self._last_dir = ""
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
        right.rowconfigure(0, weight=1)

        self.mode = tk.StringVar(value="timetables")
        task = ttk.Frame(left)                           # the task: one drop-down; only its inputs are shown below
        task.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        task.columnconfigure(1, weight=1)
        ttk.Label(task, text="Task:", font="AppBold").grid(row=0, column=0, padx=(0, 6))
        self.task_box = TaskBox(task, TASK_GROUPS)
        self.task_box.grid(row=0, column=1, sticky="ew")
        self.task_box.bind("<<ComboboxSelected>>", self._task_picked)
        self.mode.trace_add("write", lambda *_a: self._task_shown())
        mf = self.cmp_frame = ttk.LabelFrame(left, text="1. Input", padding=8)
        mf.grid(row=1, column=0, sticky="ew")
        mf.columnconfigure(1, weight=1)
        self.vars = {"a": tk.StringVar(), "b": tk.StringVar()}
        self.rows, self.clear_btns = {}, {}
        for r, key in enumerate(self.vars, start=1):
            side = r - 1
            lab = ttk.Label(mf, text="")
            box = self.app.file_box(mf, self.vars[key], f"tt_{key}",          # this task's file types only
                                    exts=lambda side=side: EXTS[self._cmp_mode()][side])
            box.bind("<FocusIn>", lambda _e: self._pick_section("compare"), add="+")
            btn = ttk.Button(mf, text="Browse...", command=lambda k=key: self._browse(k))
            pad = 2
            lab.grid(row=r, column=0, sticky="w", pady=pad)
            box.grid(row=r, column=1, sticky="ew", padx=4, pady=pad)
            btn.grid(row=r, column=2, pady=pad)
            self.rows[key] = (lab, box, btn)
            clear = ttk.Button(mf, text="Clear", width=6, command=lambda k=key: self.vars[k].set(""))
            clear.grid(row=r, column=3, padx=(4, 0), pady=pad)
            self.clear_btns[key] = clear
            self.vars[key].trace_add("write", lambda *_a: self._update_name_hint())
        ttk.Button(mf, text="Swap the two files", command=self._swap).grid(row=3, column=2, pady=(2, 0))
        self.pax_var = tk.BooleanVar(value=False)
        self.pax_cb = ttk.Checkbutton(mf, text="Passenger times only (leave out passing and working-only times)",
                                      variable=self.pax_var)
        self.pax_cb.grid(row=6, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.hl_var = tk.BooleanVar(value=False)
        self.hl_cb = ttk.Checkbutton(mf, text="Also save the PDFs with the changes highlighted", variable=self.hl_var)
        self.hl_cb.grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))
        Tooltip(self.hl_cb, "Saves a copy of the updated PDFs (changes yellow, additions green) and of the original "
                            "PDFs (removals red) beside the report. Each highlight has a note saying what changed.")
        Tooltip(self.pax_cb, "For prints where one side does not show the intermediate timing points: passing "
                             "times and calls without a public time are not compared.")

        self._cmp_widgets = [w for w in mf.grid_slaves() if int(w.grid_info()["row"]) >= 1]

        # --- utilities: the Section 4 possession check (Attune XML + Network Rail's Section 4 PDFs)
        uf = self.util_frame = ttk.LabelFrame(left, text="1. Input", padding=8)
        uf.grid(row=1, column=0, sticky="ew")
        uf.columnconfigure(1, weight=1)
        self.s4_vars = {"xml": tk.StringVar(), "pdf": tk.StringVar(), "vpt": tk.StringVar(),
                        "others": tk.StringVar()}
        self.s4_boxes = {}
        rows = (("xml", "Attune XML:", "Browse..."), ("pdf", "Section 4 PDF(s):", "Add..."),
                ("vpt", "GTR VPT (optional):", "Browse..."),
                ("others", "Other operators (optional):", "Add..."))
        for r, (key, text, btn) in enumerate(rows, start=1):
            pad = 2
            ttk.Label(uf, text=text).grid(row=r, column=0, sticky="w", pady=pad)
            box = self.app.file_box(uf, self.s4_vars[key], f"s4_{key}")
            box.grid(row=r, column=1, sticky="ew", padx=4, pady=pad)
            box.bind("<FocusIn>", lambda _e: self._pick_section("util"), add="+")
            self.s4_boxes[key] = box
            ttk.Button(uf, text=btn, command=lambda k=key: self._browse_s4(k)).grid(row=r, column=2, pady=pad)
            if key in ("pdf", "others", "vpt"):
                ttk.Button(uf, text="Clear", width=6, command=lambda k=key: self.s4_vars[k].set("")).grid(
                    row=r, column=3, padx=(4, 0), pady=2)
            self.s4_vars[key].trace_add("write", lambda *_a: self._update_name_hint())
        self.s4_set = theme.collapse_empty(ttk.Label(uf, text="", style="Small.TLabel", wraplength=480,
                                                     justify="left"))
        self.s4_set.grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.s4_vars["pdf"].trace_add("write", lambda *_a: debounce(self, "rules", 400, self.show_rule_set))
        self.show_rule_set()
        self._last_cmp = "timetables"

        of = ttk.LabelFrame(left, text="2. Output", padding=8)
        of.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        of.columnconfigure(1, weight=1)
        ttk.Label(of, text="Save to folder:").grid(row=0, column=0, sticky="w")
        self.out_dir = tk.StringVar()
        out_box = local_folder_box(ttk.Entry(of, textvariable=self.out_dir), self.out_dir)
        out_box.grid(row=0, column=1, sticky="ew", padx=4)
        Placeholder(out_box, "Downloads")
        ttk.Button(of, text="Browse...", command=self._browse_dir).grid(row=0, column=2)
        ttk.Label(of, text="Output name:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.out_name = tk.StringVar()
        name_box = ttk.Entry(of, textvariable=self.out_name)
        name_box.grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        self.name_hint = Placeholder(name_box)          # the name the output gets if the box is left blank
        fmtf = ttk.Frame(of)
        fmtf.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(fmtf, text="Save as:").grid(row=0, column=0, padx=(0, 6))
        self.fmt_var = tk.StringVar(value="xlsx")
        for i, (key, text) in enumerate((("xlsx", "Excel"), ("pdf", "PDF"), ("docx", "Word"))):
            ttk.Radiobutton(fmtf, text=text, variable=self.fmt_var, value=key).grid(row=0, column=i + 1,
                                                                                  padx=(0, 10))

        rf = ttk.LabelFrame(right, text="3. Run", padding=8)
        rf.grid(row=0, column=0, sticky="nsew")
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(2, weight=1)
        top = ttk.Frame(rf)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.run_btn = ttk.Button(top, text="Compare timetables", style="Run.TButton", command=self.run)
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
        self.open_btn = ttk.Button(ob, text="Open output", state="disabled",
                                   command=lambda: self.app.open_outputs(self.outputs, force=True))
        self.open_btn.grid(row=0, column=0)
        self.dir_btn = ttk.Button(ob, text="Open folder", state="disabled",
                                  command=lambda: self.app.open_outputs([os.path.dirname(self.outputs[0])],
                                                                        force=True))
        self.dir_btn.grid(row=0, column=1, padx=6)
        ttk.Checkbutton(ob, text="Open when finished", variable=self.app.open_var).grid(row=0, column=2,
                                                                                      padx=(12, 0))

    # ---------------------------------------------------- drag and drop
    def enable_drag_and_drop(self, dnd_files: str):
        self._dnd = dnd_files
        self._add_drop_target(self)

    def _add_drop_target(self, widget, util=False):
        if not self._dnd or isinstance(widget, tk.Text):
            return
        util = util or widget is self.util_frame
        key = next((k for k, row in self.rows.items() if widget in row), None)       # a box's whole row
        try:
            widget.drop_target_register(self._dnd)
            widget.dnd_bind("<<Drop>>", lambda e, k=key, u=util: self._on_drop(e, k, u))
        except (tk.TclError, AttributeError):
            return
        for child in widget.winfo_children():
            self._add_drop_target(child, util)

    def _on_drop(self, event, key=None, util=False):
        paths = [os.path.normpath(p) for p in self.tk.splitlist(event.data) if os.path.isfile(p)]
        xmls = [p for p in paths if p.lower().endswith(".xml")]
        if util or xmls or (self.mode.get() == S4 and any(p.lower().endswith(".vpt") for p in paths)):
            self.place_section4(paths)
        elif paths and all(p.lower().endswith(".pdf") for p in paths):
            def sniff():                           # opening PDFs takes a moment: not on the window's thread
                try:   # Section 4 PDFs only when every file is one: stop reading at the first that is not
                    s4 = all(is_section4(p) for p in paths)
                except Exception:
                    s4 = False
                self.q.put(("dropped", paths, key, s4))
            self.app.pump.start(sniff)
            self.app.pump.kick()
        else:
            self.place_files(paths, key)
        return event.action

    def place_section4(self, paths):
        """The Attune XML and Section 4 PDFs into the Section 4 check's boxes."""
        xmls = [p for p in paths if p.lower().endswith(".xml")]
        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        vpts = [p for p in paths if p.lower().endswith(".vpt")]
        if not xmls and not pdfs and not vpts:
            messagebox.showwarning(TITLE, "Drop the Attune XML (.xml), Network Rail's Section 4 PDF(s) and any VPT(s).",
                                   parent=self)
            return
        self._set_mode(S4)
        if vpts:                         # the first goes in "GTR VPT" when it is empty, the rest are other operators'
            if not self.s4_vars["vpt"].get().strip():
                self.s4_vars["vpt"].set(vpts.pop(0))
            if vpts:
                self.s4_vars["others"].set(self._join(self.s4_vars["others"].get(), vpts))
        if xmls:
            self.s4_vars["xml"].set(xmls[0])
        if pdfs:
            self.s4_vars["pdf"].set(self._join(self.s4_vars["pdf"].get(), pdfs))

    def place_files(self, paths, key=None):
        """Put dropped files in the right boxes, switching the comparison type when the files say so."""
        prints = [p for p in paths if p.lower().endswith(_PR)]
        vpts = [p for p in paths if p.lower().endswith(".vpt")]
        sheets = [p for p in paths if p.lower().endswith(_LI)]
        if not prints and not sheets and not vpts:
            messagebox.showwarning(TITLE, "Drop Excel timetables or train lists (.xlsx), train prints (.pdf / "
                                          ".docx) or Attune VPT exports (.vpt).", parent=self)
            return
        self._pick_section("compare")
        mode = self.mode.get()
        if vpts:                                        # VPT exports are compared as train prints
            self._set_mode("prints")
            files = sorted(vpts + prints, key=os.path.getmtime)         # older file(s) are the original
            if len(files) >= 2:
                half = len(files) // 2
                self.vars["a"].set(SEP.join(files[:half]))
                self.vars["b"].set(SEP.join(files[half:]))
            else:
                empty = [k for k in ("a", "b") if not self.vars[k].get().strip()]
                self.vars[(empty or ["b"])[0]].set(files[0])
            return
        if key:                                         # dropped on a box that takes these files: they go there
            side = 0 if key == "a" else 1
            fits = [p for p in paths if p.lower().endswith(EXTS[mode][side])]
            if fits and len(fits) == len(paths):
                many = MULTI.get(mode, (False, False))[side]
                self.vars[key].set(self._join(self.vars[key].get(), fits) if many else fits[0])
                if not many and len(fits) > 1:
                    self.status.configure(text="That box takes one file - the first was used.")
                return
        if mode in ("s4docs", "tprs") and all(p.lower().endswith(".pdf") for p in paths):
            files = sorted(paths, key=os.path.getmtime)         # older file(s) are the original
            if len(files) >= 2:
                half = len(files) // 2
                self.vars["a"].set(SEP.join(files[:half]))
                self.vars["b"].set(SEP.join(files[half:]))
            else:
                empty = [k for k in ("a", "b") if not self.vars[k].get().strip()]
                self.vars[(empty or ["b"])[0]].set(files[0])
            return
        kinds = {p: sniff_timetable(p) for p in sheets}
        tts = sorted((p for p in sheets if kinds[p]), key=lambda p: kinds[p] != "gtr")      # GTR first
        lists = [p for p in sheets if not kinds[p]]
        if prints and (tts or mode == "print_tt"):
            self._set_mode("print_tt")
            self.vars["a"].set(self._join("" if tts else self.vars["a"].get(), prints))
            if tts:
                self.vars["b"].set(tts[0])
        elif prints:
            self._set_mode("prints")
            files = sorted(prints, key=os.path.getmtime)        # older file(s) are the original
            if len(files) >= 2:
                half = len(files) // 2
                self.vars["a"].set(SEP.join(files[:half]))
                self.vars["b"].set(SEP.join(files[half:]))
            else:
                empty = [k for k in ("a", "b") if not self.vars[k].get().strip()]
                self.vars[(empty or ["b"])[0]].set(files[0])
        elif tts and lists:
            self._set_mode("list_tt")
            self.vars["a"].set(lists[0])
            self.vars["b"].set(tts[0])
        elif tts:
            if mode in ("print_tt", "list_tt") and len(tts) == 1:
                self.vars["b"].set(tts[0])
                return
            self._set_mode("timetables")
            gtr = [p for p in tts if kinds[p] == "gtr"]
            nr = [p for p in tts if kinds[p] == "nr"]
            if gtr:
                self.vars["a"].set(gtr[0])
            if nr:
                self.vars["b"].set(nr[0])
        else:
            if mode == "list_tt" and len(lists) == 1:
                self.vars["a"].set(lists[0])
                return
            self._set_mode("lists")
            if len(lists) >= 2:
                older, newer = sorted(lists[:2], key=os.path.getmtime)
                self.vars["a"].set(older)
                self.vars["b"].set(newer)
            else:
                empty = [k for k in ("a", "b") if not self.vars[k].get().strip()]
                self.vars[(empty or ["b"])[0]].set(lists[0])

    @staticmethod
    def _join(existing: str, new) -> str:
        return SEP.join(dict.fromkeys(split_paths(existing) + list(new)))

    # ------------------------------------------------------------ helpers
    def _set_mode(self, mode):
        if mode != self.mode.get():
            self.mode.set(mode)
            self._mode_changed()

    def show_rule_set(self):
        """Say which Section 4 rules the check will use: the PDFs chosen, else the rule set in use."""
        from rstools import rules
        info = rules.active_set_info()
        if split_paths(self.s4_vars["pdf"].get()):
            text = "The PDFs chosen above are used." + (f" (Leave the box blank to use the rule set '{info['name']}'.)"
                                                       if info else "")
        elif info:
            text = (f"Leave the PDF box blank to use the Section 4 rule set in use: {info['name']} "
                    f"({info['possessions']} possession rows). Change it in Settings > Rules.")
        else:
            text = ("No Section 4 rule set has been added: choose the PDFs, or add them once as a rule set in "
                    "Settings > Rules.")
        self.s4_set.configure(text=text)

    def _cmp_mode(self) -> str:
        """The comparison chosen in the Timetable comparison section (kept while the Section 4 check is on)."""
        mode = self.mode.get()
        return mode if mode in MODE_TEXT else self._last_cmp

    def _pick_section(self, section: str):
        if section == "util" and self.mode.get() != S4:
            self._set_mode(S4)
        elif section == "compare" and self.mode.get() == S4:
            self._set_mode(self._last_cmp)

    def _mode_changed(self):
        mode = self.mode.get()
        util = mode == S4
        (self.util_frame.grid if util else self.util_frame.grid_remove)()
        for w in self._cmp_widgets:
            (w.grid_remove if util else w.grid)()
        self._task_shown()
        if not util:
            self._last_cmp = mode
        cmp = self._cmp_mode()                       # the comparison section keeps its own choice
        for side, (key, text) in enumerate(zip(("a", "b"), SIDES[cmp])):
            self.rows[key][0].configure(text=text)
            many = MULTI.get(cmp, (False, False))[side]
            self.rows[key][2].configure(text="Add..." if many else "Browse...")   # several prints: each adds
            icons.refresh_button(self.rows[key][2])
            (self.clear_btns[key].grid if many else self.clear_btns[key].grid_remove)()
            current = self.vars[key].get()
            if current and not all(p.lower().endswith(EXTS[cmp][side]) for p in split_paths(current)):
                self.vars[key].set("")
        (self.pax_cb.grid if cmp == "prints" else self.pax_cb.grid_remove)()
        (self.hl_cb.grid if cmp in ("s4docs", "tprs") else self.hl_cb.grid_remove)()
        self.run_btn.configure(text="Check Section 4" if util else MODE_TEXT[cmp][1])
        if not self.running:
            self.status.configure(text=READY)
        self._update_name_hint()

    def _task_picked(self, _event=None):
        mode = self.task_box.picked()
        if mode:
            self._set_mode(mode)
        self._task_shown()                      # a group heading chosen: show its first task

    def _task_shown(self):
        self.task_box.show(self.mode.get())

    def _update_name_hint(self):
        mode = self.mode.get()
        if mode == S4:
            xml = self.s4_vars["xml"].get().strip()
            stem = os.path.splitext(os.path.basename(xml))[0] if xml else "XML name"
            self.name_hint.configure(text=f"Section 4 check - {stem}")
            return
        if mode == "timetables":
            hint = "[NR timetable] Consolidated TT Comparison"
        elif mode in ("print_tt", "list_tt"):
            hint = "[reference] vs [timetable] Consolidated TT Comparison"
        else:
            name = default_name(mode, split_paths(self.vars["a"].get()), split_paths(self.vars["b"].get()))
            hint = name or "today's date and 'original vs updated'"
        self.name_hint.configure(text=hint)

    def _browse(self, key):
        self._pick_section("compare")
        mode = self.mode.get()
        start = os.path.dirname(split_paths(self.vars[key].get())[0]) if self.vars[key].get().strip() else \
            self._last_dir
        side = 0 if key == "a" else 1
        kw = dict(parent=self, title="Choose the " + file_label(SIDES[mode][side]), filetypes=_FT[EXTS[mode][side]],
                  initialdir=start or None)
        if MULTI.get(mode, (False, False))[side]:          # added to the prints already in the box
            chosen = filedialog.askopenfilenames(**kw)
            if chosen:
                self.vars[key].set(self._join(self.vars[key].get(), (os.path.normpath(p) for p in chosen)))
                self._last_dir = os.path.dirname(chosen[0])
        else:
            chosen = filedialog.askopenfilename(**kw)
            if chosen:
                self.vars[key].set(os.path.normpath(chosen))
                self._last_dir = os.path.dirname(chosen)

    def _browse_s4(self, key):
        start = self._last_dir or None
        if key == "xml":
            chosen = filedialog.askopenfilename(parent=self, title="Choose the Attune XML", initialdir=start,
                                                filetypes=[("Attune diagram XML", "*.xml"), ("All files", "*.*")])
            if chosen:
                self.s4_vars["xml"].set(os.path.normpath(chosen))
                self._last_dir = os.path.dirname(chosen)
        elif key in ("vpt", "others"):
            many = key == "others"
            ask = filedialog.askopenfilenames if many else filedialog.askopenfilename
            from rstools.dropping import filetypes
            kinds = (("Attune VPT export", ".vpt"),) + ((("Attune F3 print", ".pdf", ".docx", ".docm"),) if many
                                                        else ())
            chosen = ask(parent=self, title="Choose other operators' VPTs (preferred) or F3 prints" if many
                         else "Choose the GTR VPT", initialdir=start, filetypes=filetypes(*kinds))
            if chosen:
                paths = [os.path.normpath(p) for p in (chosen if many else [chosen])]
                self.s4_vars[key].set(self._join(self.s4_vars[key].get(), paths) if many else paths[0])
                self._last_dir = os.path.dirname(paths[0])
        else:
            chosen = filedialog.askopenfilenames(parent=self, title="Choose the Section 4 PDFs", initialdir=start,
                                                 filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
            if chosen:
                self.s4_vars["pdf"].set(self._join(self.s4_vars["pdf"].get(), (os.path.normpath(p) for p in chosen)))
                self._last_dir = os.path.dirname(chosen[0])
        self._set_mode(S4)

    def _browse_dir(self):
        d = filedialog.askdirectory(parent=self, title="Choose the output folder",
                                    initialdir=output_folder(self.out_dir.get()))
        if d:
            self.out_dir.set(os.path.normpath(d))

    def _swap(self):
        a, b = self.vars["a"].get(), self.vars["b"].get()
        self.vars["a"].set(b)
        self.vars["b"].set(a)

    # ------------------------------------------------------------ settings
    def _load_settings(self):
        try:
            with open(_settings_path(), encoding="utf-8") as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(s, dict):
            return
        if s.get("mode") in MODES or s.get("mode") == S4:
            self.mode.set(s["mode"])
        if s.get("fmt") in ("xlsx", "pdf", "docx"):
            self.fmt_var.set(s["fmt"])
        if isinstance(s.get("output_dir"), str):
            self.out_dir.set(s["output_dir"])
        if isinstance(s.get("last_dir"), str):
            self._last_dir = s["last_dir"]
        if isinstance(s.get("passenger_only"), bool):
            self.pax_var.set(s["passenger_only"])

    def _save_settings(self):
        s = {"mode": self.mode.get(), "fmt": self.fmt_var.get(), "output_dir": self.out_dir.get().strip(),
             "last_dir": self._last_dir, "passenger_only": self.pax_var.get()}
        write_json(_settings_path(), s)

    # ------------------------------------------------------------ saved comparisons
    def get_state(self) -> dict:
        return {"mode": self.mode.get(), "a": self.vars["a"].get(), "b": self.vars["b"].get(),
                "s4_xml": self.s4_vars["xml"].get(), "s4_pdf": self.s4_vars["pdf"].get(),
                "s4_vpt": self.s4_vars["vpt"].get(), "s4_others": self.s4_vars["others"].get(),
                "fmt": self.fmt_var.get(), "output_dir": self.out_dir.get(), "output_name": self.out_name.get(),
                "passenger_only": self.pax_var.get(), "highlight_pdfs": self.hl_var.get()}

    def set_state(self, s: dict):
        if s.get("mode") in MODES or s.get("mode") == S4:
            self._set_mode(s["mode"])
        for key in ("a", "b"):
            self.vars[key].set(s.get(key, "") if isinstance(s.get(key), str) else "")
        for key in ("xml", "pdf", "vpt", "others"):
            v = s.get(f"s4_{key}", "")
            self.s4_vars[key].set(v if isinstance(v, str) else "")
        if s.get("fmt") in ("xlsx", "pdf", "docx"):
            self.fmt_var.set(s["fmt"])
        self.out_dir.set(s.get("output_dir", "") if isinstance(s.get("output_dir"), str) else "")
        self.out_name.set(s.get("output_name", "") if isinstance(s.get("output_name"), str) else "")
        self.pax_var.set(s.get("passenger_only") is True)
        self.hl_var.set(s.get("highlight_pdfs") is True)

    @staticmethod
    def files_in_state(s: dict) -> list:
        if s.get("mode") == S4:
            return (split_paths(s.get("s4_xml", "")) + split_paths(s.get("s4_pdf", ""))
                    + split_paths(s.get("s4_vpt", "")) + split_paths(s.get("s4_others", "")))
        return split_paths(s.get("a", "")) + split_paths(s.get("b", ""))

    # ---------------------------------------------------------------- run
    def _append(self, msg, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", (tag,) if tag else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self):
        if self.running:
            return
        mode = self.mode.get()
        if mode == S4:
            return self._run_section4()
        sides = {k: split_paths(v.get()) for k, v in self.vars.items()}
        for side, (key, label) in enumerate(zip(("a", "b"), SIDES[mode])):
            what = file_label(label)
            if not sides[key]:
                return messagebox.showwarning(TITLE, f"Choose the {what}.", parent=self)
            if not MULTI.get(mode, (False, False))[side] and len(sides[key]) > 1:
                return messagebox.showwarning(TITLE, f"Choose one file for the {what}.", parent=self)
            for p in sides[key]:
                if not os.path.isfile(p):
                    return messagebox.showwarning(TITLE, f"This file could not be found:\n{p}", parent=self)
                if not p.lower().endswith(EXTS[mode][side]):
                    return messagebox.showwarning(TITLE, f"The {what} should be a {' / '.join(EXTS[mode][side])} "
                                                         f"file:\n{p}", parent=self)
        if set(sides["a"]) & set(sides["b"]):
            return messagebox.showwarning(TITLE, "The same file is chosen in both boxes. Choose two different "
                                                 "files.", parent=self)
        typed = self.out_dir.get().strip().strip('"')
        if typed and not os.path.isdir(typed):           # as on the other tabs: never quietly saved elsewhere
            return messagebox.showwarning(TITLE, f"The output folder does not exist:\n{typed}\n\nChoose a folder "
                                                 "that exists, or leave the box empty for Downloads.", parent=self)
        out_dir = output_folder(self.out_dir.get())
        name = re.sub(r'[<>:"/\\|?*]', "-", self.out_name.get().strip()).strip(" .")
        for key in ("a", "b"):
            self.app.add_recent(f"tt_{key}", *sides[key][:1])
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
        threading.Thread(target=self._work, args=(mode, sides["a"], sides["b"], out_dir, name, self.fmt_var.get(),
                                                  mode == "prints" and self.pax_var.get(),
                                                  mode in ("s4docs", "tprs") and self.hl_var.get()),
                         daemon=True).start()
        self.app.pump.kick()

    def _run_section4(self):
        xml = self.s4_vars["xml"].get().strip().strip('"')
        pdfs = split_paths(self.s4_vars["pdf"].get())
        if not xml:
            return messagebox.showwarning(TITLE, "Choose the Attune XML.", parent=self)
        from rstools import rules
        if not pdfs and not rules.active_set_info():
            return messagebox.showwarning(TITLE, "Choose the Section 4 PDF(s), or add a Section 4 rule set in "
                                                 "Settings > Rules.\n\nThe latest rules can be "
                                                 f"downloaded from Network Rail:\n{rules.RULES_URL}", parent=self)
        for p in [xml] + pdfs:
            if not os.path.isfile(p):
                return messagebox.showwarning(TITLE, f"This file could not be found:\n{p}", parent=self)
        if not xml.lower().endswith(".xml"):
            return messagebox.showwarning(TITLE, f"The Attune XML should be a .xml file:\n{xml}", parent=self)
        bad = [p for p in pdfs if not p.lower().endswith(".pdf")]
        if bad:
            return messagebox.showwarning(TITLE, f"The Section 4 file(s) should be PDFs:\n{bad[0]}", parent=self)
        vpt = self.s4_vars["vpt"].get().strip().strip('"')
        others = split_paths(self.s4_vars["others"].get())
        for p in ([vpt] if vpt else []) + others:
            if not os.path.isfile(p):
                return messagebox.showwarning(TITLE, f"This file could not be found:\n{p}", parent=self)
            if not p.lower().endswith(".vpt") and not (p in others and p.lower().endswith(_PR)):
                return messagebox.showwarning(TITLE, f"The VPT should be a .vpt file:\n{p}" if p == vpt else
                                              f"Other operators' files should be VPTs (.vpt) or Attune F3 "
                                              f"prints (.pdf / .docx):\n{p}", parent=self)
        typed = self.out_dir.get().strip().strip('"')
        if typed and not os.path.isdir(typed):           # as on the other tabs: never quietly saved elsewhere
            return messagebox.showwarning(TITLE, f"The output folder does not exist:\n{typed}\n\nChoose a folder "
                                                 "that exists, or leave the box empty for Downloads.", parent=self)
        out_dir = output_folder(self.out_dir.get())
        name = re.sub(r'[<>:"/\\|?*]', "-", self.out_name.get().strip()).strip(" .")
        self.app.add_recent("s4_xml", xml)
        if pdfs:
            self.app.add_recent("s4_pdf", pdfs[0])
        self._save_settings()
        self.app.save_app_settings()
        self._begin()
        threading.Thread(target=self._work_section4, args=(xml, pdfs, out_dir, name, self.fmt_var.get(), vpt, others),
                         daemon=True).start()
        self.app.pump.kick()

    def _begin(self):
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

    def _work_section4(self, xml, pdfs, out_dir, name, fmt, vpt="", others=()):
        from .section4 import Section4Error, run_check
        try:
            path, res, st, start = run_check(xml, pdfs, out_dir, name, fmt, vpt=vpt, others=others,
                                             progress=lambda f, m: self.q.put(("prog", f, m)),
                                             log=lambda m: self.q.put(("log", m, None)))
            every = sum(1 for c in res.clashes if c.all_lines)
            lines = [f"{plural(len(st.possessions), 'possession row')} read; {res.checked:,} checked against the XML "
                     f"(periods: {', '.join(p.name for p in res.periods) or 'none'})."]
            lines += [f"WARNING: {w}" for w in st.warnings + res.warnings]
            summary = (f"{plural(res.trains, 'train')} {'runs' if res.trains == 1 else 'run'} in a Section 4 "
                       f"possession window: {plural(every, 'clash')} where every line is blocked, "
                       f"{len(res.clashes) - every:,} where only some lines are (check the line used)."
                       if res.clashes else "No train runs in a Section 4 possession window.")
            if res.by_line:
                summary += f" {plural(res.by_line, 'clash')} cleared by the running lines in the VPT."
            if res.exempt or res.skipped:
                summary += (f" {plural(len(res.exempt), 'clash')} cleared by the possession remarks; "
                            f"{plural(len(res.skipped), 'train')} not checked (runs as required or MAINT).")
            self.q.put(("s4done", path, lines, summary, len(st.warnings + res.warnings), start))
        except (Section4Error, TimetableRunError) as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:
            self.q.put(("error", errorlog.describe(exc)))

    def _work(self, mode, first, second, out_dir, name, fmt, passenger_only=False, highlight=False):
        try:
            res = run(mode, first, second, out_dir, name, fmt, progress=lambda f, m: self.q.put(("prog", f, m)),
                      log=lambda m: self.q.put(("log", m, "warn" if m.startswith("WARNING") else None)),
                      passenger_only=passenger_only, highlight_pdfs=highlight)
            self.q.put(("done", res))
        except TimetableRunError as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:                    # parse errors carry a readable message
            known = type(exc).__name__ in ("TimetableError", "PrintError", "TrainListError")
            if known:
                self.q.put(("error", str(exc)))
                return
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
                if item[0] == "prog":
                    self.progress.set(item[1], item[2])
                elif item[0] == "log":
                    self._append(item[1], item[2])
                elif item[0] == "dropped":
                    _k, paths, key, s4 = item
                    (self.place_section4(paths) if s4 and self.mode.get() != "s4docs"
                     else self.place_files(paths, key))
                elif item[0] == "done":
                    res = item[1]
                    self._finish(True)
                    self.progress.finish()
                    self.outputs = [res.path] + list(res.extra)
                    for line in res.lines:
                        self._append(line)
                    summary = (f"{plural(res.differences, 'difference')} found." if res.differences
                               else "No differences found.")
                    self._append(summary, "ok")
                    self._append(f"Saved: {res.path}", "ok")
                    self.open_btn.state(["!disabled"])
                    self.dir_btn.state(["!disabled"])
                    self.app.open_outputs(self.outputs)
                    note = f"\n\n{plural(len(res.warnings), 'warning')} - see the log." if res.warnings else ""
                    from rstools.fsutil import excel_warning
                    long_warn = excel_warning([res.path])
                    if long_warn:
                        self._append("WARNING: " + long_warn, "warn")
                        note += f"\n\n{long_warn}"
                    self.app.notify_done("Timing Tools finished", summary)
                    messagebox.showinfo(TITLE, f"{summary}\n\n{res.path}{note}", parent=self)
                elif item[0] == "s4done":
                    _k, path, lines, summary, nwarn, start = item
                    self._finish(True)
                    self.progress.finish()
                    self.outputs = [path]
                    for line in lines:
                        self._append(line, "warn" if line.startswith("WARNING") else None)
                    self._append(summary, "ok")
                    self._append(f"Saved: {path}", "ok")
                    self.open_btn.state(["!disabled"])
                    self.dir_btn.state(["!disabled"])
                    self.app.open_outputs(self.outputs)
                    self.app.notify_done("Section 4 check finished", summary)
                    messagebox.showinfo(TITLE, f"{summary}\n\n{path}"
                                        + (f"\n\n{plural(nwarn, 'warning')} - see the log." if nwarn else ""),
                                        parent=self)
                    self.app.rules_reminder(start)
                elif item[0] == "stopped":
                    self._finish(False)
                    self.status.configure(text=STOPPED)
                    self._append("Stopped - nothing was saved.", "warn")
                elif item[0] == "error":
                    self._finish(False)
                    self._append("ERROR: " + item[1], "error")
                    self.app.notify_done("Timing Tools failed", item[1].splitlines()[0], False)
                    messagebox.showerror(TITLE, item[1][:1500], parent=self)
        except queue.Empty:
            pass
