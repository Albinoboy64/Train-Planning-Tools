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

from rstools import errorlog, theme
from rstools.branding import APP_NAME, settings_dir
from rstools.naming import file_label
from rstools.fsutil import write_json

from .engine import MODES, TimetableRunError, default_name, run

TITLE = f"{APP_NAME} - Timing Tools"
MODE_TEXT = {
    "timetables": ("GTR timetable against the Network Rail timetable", "Compare timetables"),
    "print_tt": ("Train prints against a timetable (Attune Single Train Report)", "Check timetable"),
    "list_tt": ("Attune train list against a timetable", "Check timetable"),
    "prints": ("Two sets of train prints (PDF or Word)", "Compare train prints"),
    "lists": ("Two Attune train list exports (Excel)", "Compare train lists"),
}
SIDES = {
    "timetables": ("GTR timetable:", "Network Rail timetable:"),
    "print_tt": ("Train print(s) - reference:", "Timetable to check:"),
    "list_tt": ("Attune train list - reference:", "Timetable to check:"),
    "prints": ("Original train print(s):", "Updated train print(s):"),
    "lists": ("Original Attune train list:", "Updated Attune train list:"),
}
_XL, _PR, _LI = (".xlsx", ".xlsm"), (".pdf", ".docx", ".docm"), (".xlsx", ".xlsm", ".csv")
_FT = {_XL: [("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")],
       _PR: [("Train prints", "*.pdf *.docx"), ("PDF", "*.pdf"), ("Word", "*.docx"), ("All files", "*.*")],
       _LI: [("Excel workbook or CSV", "*.xlsx *.xlsm *.csv"), ("All files", "*.*")]}
EXTS = {"timetables": (_XL, _XL), "print_tt": (_PR, _XL), "list_tt": (_LI, _XL), "prints": (_PR, _PR),
        "lists": (_LI, _LI)}                       # accepted file types for the first and second box
MULTI = {"print_tt": (True, False), "prints": (True, True)}     # boxes that take several files
NOTES = {
    "timetables": ("Network Rail is the reference: every NR time at a GTR location is checked. Saved in the "
                   "Consolidated TT Comparison template, named after the NR timetable."),
    "print_tt": ("The Single Train Report prints are the reference: each train's public times are checked against "
                 "the timetable (GTR or Network Rail layout), in the same template. Passes, working-only stops and "
                 "empty stock are not compared."),
    "list_tt": ("The train list is the reference. A list only has each train's origin and destination times, so "
                "only those are checked (use train prints to check every stop). Empty stock is left out."),
    "prints": ("Each train is compared location by location (times, platform, line, activities), with its "
               "heading details."),
    "lists": ("Trains are paired by UID and days (or headcode, days and departure time; a retimed train still pairs "
              "when it is the only one left with its headcode, days and origin), and every column is compared."),
}
SEP = " ; "
S4 = "section4"                 # Utilities: the Section 4 possession check
S4_NOTE = ("Lists every train that runs through a section during one of its Section 4 possessions. The XML has no "
           "running lines, so where only some lines are blocked the report says to check the line used.")


def is_section4(path: str) -> bool:
    """A Section 4 (Engineering Access Statement) PDF, judged from its first page."""
    if not path.lower().endswith(".pdf"):
        return False
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        try:
            text = pdf[0].get_textpage().get_text_range() if len(pdf) else ""
        finally:
            pdf.close()
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
    import xml.etree.ElementTree as ET
    from rstools.fsutil import check_zip
    with zipfile.ZipFile(path) as z:
        check_zip(z, "xl/workbook.xml")     # refuse a 'zip bomb' before unpacking
        root = ET.fromstring(z.read("xl/workbook.xml"))
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
        self.q: "queue.Queue" = queue.Queue()
        self.running = False
        self.outputs = []
        self._started = 0.0
        self._dnd = ""
        self._last_dir = ""
        self._build()
        self._load_settings()
        self._mode_changed()
        self._poll_id = self.after(150, self._poll)

    # ------------------------------------------------------------------ UI
    def _build(self):
        self.columnconfigure(0, weight=1, minsize=520)
        self.columnconfigure(1, weight=1, minsize=470)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="Timing Tools", style="Head.TLabel").grid(row=0, column=0, columnspan=2,
                                                                              sticky="w")
        theme.tip(ttk.Label(self, text="Checks a timetable against the Network Rail timetable, Attune train prints or "
                                       "a train list, compares train prints or train lists, and checks the timetable "
                                       "against Section 4 possessions.", style="Small.TLabel", wraplength=1000,
                            justify="left")).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        left, right = ttk.Frame(self), ttk.Frame(self)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=2, column=1, sticky="nsew")
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        mf = self.cmp_frame = ttk.LabelFrame(left, text="1. Timetable comparison", padding=8)
        mf.grid(row=0, column=0, sticky="ew")
        mf.columnconfigure(1, weight=1)
        self.mode = tk.StringVar(value="timetables")
        mrow = ttk.Frame(mf)
        mrow.grid(row=0, column=0, columnspan=4, sticky="w")
        for i, (key, (text, _btn)) in enumerate(MODE_TEXT.items()):
            ttk.Radiobutton(mrow, text=text, variable=self.mode, value=key, command=self._mode_changed).grid(
                row=i, column=0, sticky="w")
        ff = mf
        self.vars = {"a": tk.StringVar(), "b": tk.StringVar()}
        self.rows, self.clear_btns = {}, {}
        for r, key in enumerate(self.vars, start=1):
            side = r - 1
            lab = ttk.Label(ff, text="")
            box = self.app.file_box(ff, self.vars[key], f"tt_{key}")
            box.configure(postcommand=lambda b=box, side=side, k=key: b.configure(values=[    # this type's files only
                p for p in self.app.recent(f"tt_{k}") if p.lower().endswith(EXTS[self._cmp_mode()][side])]))
            box.bind("<FocusIn>", lambda _e: self._pick_section("compare"), add="+")
            btn = ttk.Button(ff, text="Browse...", command=lambda k=key: self._browse(k))
            pad = (6, 2) if r == 1 else 2
            lab.grid(row=r, column=0, sticky="w", pady=pad)
            box.grid(row=r, column=1, sticky="ew", padx=4, pady=pad)
            btn.grid(row=r, column=2, pady=pad)
            self.rows[key] = (lab, box, btn)
            clear = ttk.Button(ff, text="Clear", width=6, command=lambda k=key: self.vars[k].set(""))
            clear.grid(row=r, column=3, padx=(4, 0), pady=pad)
            self.clear_btns[key] = clear
            self.vars[key].trace_add("write", lambda *_a: self._update_name_hint())
        ttk.Button(ff, text="Swap files", command=self._swap).grid(row=3, column=2, pady=(2, 0))
        self.note = ttk.Label(ff, text="", style="Small.TLabel", wraplength=480, justify="left")
        self.note.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.dnd_hint = theme.tip(ttk.Label(ff, text="", style="Small.TLabel", wraplength=480, justify="left"))
        self.dnd_hint.grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))

        # --- utilities: the Section 4 possession check (Attune XML + Network Rail's Section 4 PDFs)
        uf = self.util_frame = ttk.LabelFrame(left, text="Utilities", padding=8)
        uf.grid(row=1, column=0, sticky="ew", pady=8)
        uf.columnconfigure(1, weight=1)
        ttk.Radiobutton(uf, text="Section 4 check: trains in Network Rail's standard possession times",
                        variable=self.mode, value=S4, command=self._mode_changed).grid(row=0, column=0,
                                                                                   columnspan=4, sticky="w")
        self.s4_vars = {"xml": tk.StringVar(), "pdf": tk.StringVar()}
        self.s4_boxes = {}
        for r, (key, text) in enumerate((("xml", "Attune XML:"), ("pdf", "Section 4 PDF(s):")), start=1):
            ttk.Label(uf, text=text).grid(row=r, column=0, sticky="w", pady=(6, 0) if r == 1 else 2)
            box = self.app.file_box(uf, self.s4_vars[key], f"s4_{key}")
            box.grid(row=r, column=1, sticky="ew", padx=4, pady=(6, 0) if r == 1 else 2)
            box.bind("<FocusIn>", lambda _e: self._pick_section("util"), add="+")
            self.s4_boxes[key] = box
            ttk.Button(uf, text="Browse..." if key == "xml" else "Add...",
                       command=lambda k=key: self._browse_s4(k)).grid(row=r, column=2,
                                                                     pady=(6, 0) if r == 1 else 2)
            if key == "pdf":
                ttk.Button(uf, text="Clear", width=6, command=lambda: self.s4_vars["pdf"].set("")).grid(
                    row=r, column=3, padx=(4, 0), pady=2)
            self.s4_vars[key].trace_add("write", lambda *_a: self._update_name_hint())
        self.s4_set = ttk.Label(uf, text="", style="Small.TLabel", wraplength=480, justify="left")
        self.s4_set.grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.s4_note = ttk.Label(uf, text=S4_NOTE, style="Small.TLabel", wraplength=480, justify="left")
        self.s4_note.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.s4_hint = theme.tip(ttk.Label(uf, text="", style="Small.TLabel", wraplength=480, justify="left"))
        self.s4_hint.grid(row=6, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.s4_vars["pdf"].trace_add("write", lambda *_a: self.show_rule_set())
        self.show_rule_set()
        self._last_cmp = "timetables"

        of = ttk.LabelFrame(left, text="2. Output", padding=8)
        of.grid(row=2, column=0, sticky="ew")
        of.columnconfigure(1, weight=1)
        ttk.Label(of, text="Save to folder:").grid(row=0, column=0, sticky="w")
        self.out_dir = tk.StringVar()
        ttk.Entry(of, textvariable=self.out_dir).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(of, text="Browse...", command=self._browse_dir).grid(row=0, column=2)
        ttk.Label(of, text="Output name:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.out_name = tk.StringVar()
        ttk.Entry(of, textvariable=self.out_name).grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        self.name_hint = ttk.Label(of, text="", style="Small.TLabel", wraplength=480, justify="left")
        self.name_hint.grid(row=2, column=0, columnspan=3, sticky="w")
        fmtf = ttk.Frame(of)
        fmtf.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(fmtf, text="Save as:").grid(row=0, column=0, padx=(0, 6))
        self.fmt_var = tk.StringVar(value="xlsx")
        for i, (key, text) in enumerate((("xlsx", "Excel (default)"), ("pdf", "PDF"), ("docx", "Word"))):
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
        self.status = ttk.Label(rf, text="Ready - press F5 or Ctrl+Enter to run", style="Small.TLabel")
        self.status.grid(row=1, column=0, sticky="w", pady=(4, 2))
        logf = ttk.Frame(rf)
        logf.grid(row=2, column=0, sticky="nsew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.log = tk.Text(logf, height=14, wrap="word", font="TkFixedFont", state="disabled", relief="flat",
                           borderwidth=1, highlightthickness=1, highlightcolor="#B0B0B0",
                           highlightbackground="#C8C8C8")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("warn", foreground="#9C5700")
        self.log.tag_configure("error", foreground="#C00000")
        self.log.tag_configure("ok", foreground="#006100")
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
        self.dnd_hint.configure(text="Tip: drag and drop the files onto this box or anywhere on the tab - the "
                                     "comparison and boxes are picked from the files.")
        self.s4_hint.configure(text="Tip: drag and drop the Attune XML and the Section 4 PDF(s) onto this box.")

    def _add_drop_target(self, widget, util=False):
        if not self._dnd or isinstance(widget, tk.Text):
            return
        util = util or widget is self.util_frame
        key = next((k for k, (_l, box, _b) in self.rows.items() if box is widget), None)
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
        # Section 4 PDFs only when every file is one: stop reading at the first that is not
        if util or xmls or (paths and all(is_section4(p) for p in paths)):
            self.place_section4(paths)
        else:
            self.place_files(paths, key)
        return event.action

    def place_section4(self, paths):
        """The Attune XML and Section 4 PDFs into the Section 4 check's boxes."""
        xmls = [p for p in paths if p.lower().endswith(".xml")]
        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        if not xmls and not pdfs:
            messagebox.showwarning(TITLE, "Drop the Attune XML (.xml) and Network Rail's Section 4 PDF(s).")
            return
        self._set_mode(S4)
        if xmls:
            self.s4_vars["xml"].set(xmls[0])
        if pdfs:
            self.s4_vars["pdf"].set(self._join(self.s4_vars["pdf"].get(), pdfs))

    def place_files(self, paths, key=None):
        """Put dropped files in the right boxes, switching the comparison type when the files say so."""
        prints = [p for p in paths if p.lower().endswith(_PR)]
        sheets = [p for p in paths if p.lower().endswith(_LI)]
        if not prints and not sheets:
            messagebox.showwarning(TITLE, "Drop Excel timetables or train lists (.xlsx), or train prints (.pdf / "
                                          ".docx).")
            return
        self._pick_section("compare")
        mode = self.mode.get()
        if key:                                         # dropped on a box that takes these files: they go there
            side = 0 if key == "a" else 1
            fits = [p for p in paths if p.lower().endswith(EXTS[mode][side])]
            if fits and len(fits) == len(paths):
                many = MULTI.get(mode, (False, False))[side]
                self.vars[key].set(self._join(self.vars[key].get(), fits) if many else fits[0])
                if not many and len(fits) > 1:
                    self.status.configure(text="That box takes one file - the first was used.")
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
                    f"({info['possessions']} possession rows). Change it in Options > Rules and reference data.")
        else:
            text = ("No Section 4 rule set has been added: choose the PDFs, or add them once as a rule set in "
                    "Options > Rules and reference data.")
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
        for frame, on in ((self.cmp_frame, not util), (self.util_frame, util)):
            frame.configure(style="TLabelframe" if on else "Off.TLabelframe")
        if not util:
            self._last_cmp = mode
        cmp = self._cmp_mode()                       # the comparison section keeps its own choice
        for side, (key, text) in enumerate(zip(("a", "b"), SIDES[cmp])):
            self.rows[key][0].configure(text=text)
            many = MULTI.get(cmp, (False, False))[side]
            self.rows[key][2].configure(text="Add..." if many else "Browse...")   # several prints: each adds
            (self.clear_btns[key].grid if many else self.clear_btns[key].grid_remove)()
            current = self.vars[key].get()
            if current and not all(p.lower().endswith(EXTS[cmp][side]) for p in split_paths(current)):
                self.vars[key].set("")
        self.note.configure(text=NOTES[cmp])
        self.run_btn.configure(text="Check Section 4" if util else MODE_TEXT[cmp][1])
        if not self.running:
            self.prog["value"] = 0
            self.status.configure(text="Ready - press F5 or Ctrl+Enter to run")
        self._update_name_hint()

    def _update_name_hint(self):
        mode = self.mode.get()
        if mode == S4:
            xml = self.s4_vars["xml"].get().strip()
            stem = os.path.splitext(os.path.basename(xml))[0] if xml else "XML name"
            self.name_hint.configure(text=f"Default name: 'Section 4 check - {stem}'. Leave the box blank to use it.")
            return
        if mode == "timetables":
            hint = "Default name: '[NR timetable] Consolidated TT Comparison' (e.g. K_D26 Consolidated TT Comparison)"
        elif mode in ("print_tt", "list_tt"):
            hint = "Default name: '[reference] vs [timetable] Consolidated TT Comparison'"
        else:
            name = default_name(mode, split_paths(self.vars["a"].get()), split_paths(self.vars["b"].get()))
            hint = f"Default name: {name}" if name else "Default name: today's date and 'original vs updated'"
        self.name_hint.configure(text=hint + ". Leave the box blank to use it.")

    def _browse(self, key):
        self._pick_section("compare")
        mode = self.mode.get()
        start = os.path.dirname(split_paths(self.vars[key].get())[0]) if self.vars[key].get().strip() else \
            self._last_dir
        side = 0 if key == "a" else 1
        kw = dict(parent=self, title=SIDES[mode][side].rstrip(":"), filetypes=_FT[EXTS[mode][side]],
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
            chosen = filedialog.askopenfilename(parent=self, title="Attune XML", initialdir=start,
                                                filetypes=[("Attune diagram XML", "*.xml"), ("All files", "*.*")])
            if chosen:
                self.s4_vars["xml"].set(os.path.normpath(chosen))
                self._last_dir = os.path.dirname(chosen)
        else:
            chosen = filedialog.askopenfilenames(parent=self, title="Section 4 PDF(s)", initialdir=start,
                                                 filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
            if chosen:
                self.s4_vars["pdf"].set(self._join(self.s4_vars["pdf"].get(), (os.path.normpath(p) for p in chosen)))
                self._last_dir = os.path.dirname(chosen[0])
        self._set_mode(S4)

    def _browse_dir(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.out_dir.get() or self._last_dir or None)
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

    def _save_settings(self):
        s = {"mode": self.mode.get(), "fmt": self.fmt_var.get(), "output_dir": self.out_dir.get().strip(),
             "last_dir": self._last_dir}
        write_json(_settings_path(), s)

    # ------------------------------------------------------------ saved comparisons
    def get_state(self) -> dict:
        return {"mode": self.mode.get(), "a": self.vars["a"].get(), "b": self.vars["b"].get(),
                "s4_xml": self.s4_vars["xml"].get(), "s4_pdf": self.s4_vars["pdf"].get(),
                "fmt": self.fmt_var.get(), "output_dir": self.out_dir.get(), "output_name": self.out_name.get()}

    def set_state(self, s: dict):
        if s.get("mode") in MODES or s.get("mode") == S4:
            self._set_mode(s["mode"])
        for key in ("a", "b"):
            self.vars[key].set(s.get(key, "") if isinstance(s.get(key), str) else "")
        for key in ("xml", "pdf"):
            v = s.get(f"s4_{key}", "")
            self.s4_vars[key].set(v if isinstance(v, str) else "")
        if s.get("fmt") in ("xlsx", "pdf", "docx"):
            self.fmt_var.set(s["fmt"])
        self.out_dir.set(s.get("output_dir", "") if isinstance(s.get("output_dir"), str) else "")
        self.out_name.set(s.get("output_name", "") if isinstance(s.get("output_name"), str) else "")

    @staticmethod
    def files_in_state(s: dict) -> list:
        if s.get("mode") == S4:
            return split_paths(s.get("s4_xml", "")) + split_paths(s.get("s4_pdf", ""))
        return split_paths(s.get("a", "")) + split_paths(s.get("b", ""))

    # ---------------------------------------------------------------- run
    def _append(self, msg, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", (tag,) if tag else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def stop(self):
        self.after_cancel(self._poll_id)

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
                return messagebox.showwarning(TITLE, f"Choose the {what} file.")
            if not MULTI.get(mode, (False, False))[side] and len(sides[key]) > 1:
                return messagebox.showwarning(TITLE, f"Choose one file for the {what}.")
            for p in sides[key]:
                if not os.path.isfile(p):
                    return messagebox.showwarning(TITLE, f"This file could not be found:\n{p}")
                if not p.lower().endswith(EXTS[mode][side]):
                    return messagebox.showwarning(TITLE, f"The {what} should be a {' / '.join(EXTS[mode][side])} "
                                                         f"file:\n{p}")
        if set(sides["a"]) & set(sides["b"]):
            return messagebox.showwarning(TITLE, "The same file is chosen on both sides.")
        out_dir = self.out_dir.get().strip().strip('"') or os.path.dirname(sides["b"][0])
        if not os.path.isdir(out_dir):
            return messagebox.showwarning(TITLE, f"The output folder does not exist:\n{out_dir}")
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
        self.prog["value"] = 0
        self._started = time.monotonic()
        self.app.set_busy(True)
        threading.Thread(target=self._work, args=(mode, sides["a"], sides["b"], out_dir, name, self.fmt_var.get()),
                         daemon=True).start()

    def _run_section4(self):
        xml = self.s4_vars["xml"].get().strip().strip('"')
        pdfs = split_paths(self.s4_vars["pdf"].get())
        if not xml:
            return messagebox.showwarning(TITLE, "Choose the Attune XML.")
        from rstools import rules
        if not pdfs and not rules.active_set_info():
            return messagebox.showwarning(TITLE, "Choose the Section 4 PDF(s), or add a Section 4 rule set in "
                                                 "Options > Rules and reference data.\n\nThe latest rules can be "
                                                 f"downloaded from Network Rail:\n{rules.RULES_URL}")
        for p in [xml] + pdfs:
            if not os.path.isfile(p):
                return messagebox.showwarning(TITLE, f"This file could not be found:\n{p}")
        if not xml.lower().endswith(".xml"):
            return messagebox.showwarning(TITLE, f"The Attune XML should be a .xml file:\n{xml}")
        bad = [p for p in pdfs if not p.lower().endswith(".pdf")]
        if bad:
            return messagebox.showwarning(TITLE, f"The Section 4 file(s) should be PDFs:\n{bad[0]}")
        out_dir = self.out_dir.get().strip().strip('"') or os.path.dirname(xml)
        if not os.path.isdir(out_dir):
            return messagebox.showwarning(TITLE, f"The output folder does not exist:\n{out_dir}")
        name = re.sub(r'[<>:"/\\|?*]', "-", self.out_name.get().strip()).strip(" .")
        self.app.add_recent("s4_xml", xml)
        if pdfs:
            self.app.add_recent("s4_pdf", pdfs[0])
        self._save_settings()
        self.app.save_app_settings()
        self._begin()
        threading.Thread(target=self._work_section4, args=(xml, pdfs, out_dir, name, self.fmt_var.get()),
                         daemon=True).start()

    def _begin(self):
        self.running = True
        self.outputs = []
        for b in (self.open_btn, self.dir_btn, self.run_btn):
            b.state(["disabled"])
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.prog["value"] = 0
        self._started = time.monotonic()
        self.app.set_busy(True)

    def _work_section4(self, xml, pdfs, out_dir, name, fmt):
        from .section4 import Section4Error, run_check
        try:
            path, res, st, start = run_check(xml, pdfs, out_dir, name, fmt,
                                      progress=lambda f, m: self.q.put(("prog", f, m)),
                                      log=lambda m: self.q.put(("log", m, None)))
            every = sum(1 for c in res.clashes if c.possession.every_line)
            lines = [f"{len(st.possessions)} possession row(s) read; {res.checked} checked against the XML "
                     f"(periods: {', '.join(p.name for p in res.periods) or 'none'})."]
            lines += [f"WARNING: {w}" for w in st.warnings + res.warnings]
            summary = (f"{res.trains} train(s) run in a Section 4 possession window: {every} clash(es) where every "
                       f"line is blocked, {len(res.clashes) - every} where only some lines are (check the line "
                       "used)." if res.clashes else "No train runs in a Section 4 possession window.")
            self.q.put(("s4done", path, lines, summary, len(st.warnings + res.warnings), start))
        except (Section4Error, TimetableRunError) as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:
            self.q.put(("error", errorlog.describe(exc)))

    def _work(self, mode, first, second, out_dir, name, fmt):
        try:
            res = run(mode, first, second, out_dir, name, fmt, progress=lambda f, m: self.q.put(("prog", f, m)),
                      log=lambda m: self.q.put(("log", m, "warn" if m.startswith("WARNING") else None)))
            self.q.put(("done", res))
        except TimetableRunError as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:                    # parse errors carry a readable message
            known = type(exc).__name__ in ("TimetableError", "PrintError", "TrainListError")
            if known:
                self.q.put(("error", str(exc)))
                return
            self.q.put(("error", errorlog.describe(exc)))

    def _finish(self, ok: bool):
        self.running = False
        self.app.set_busy(False)
        self.run_btn.state(["!disabled"])
        self.status.configure(text=(f"Finished in {time.monotonic() - self._started:.1f} s" if ok else "Failed"))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "prog":
                    self.prog["value"] = item[1]
                    self.status.configure(text=item[2])
                elif item[0] == "log":
                    self._append(item[1], item[2])
                elif item[0] == "done":
                    res = item[1]
                    self._finish(True)
                    self.prog["value"] = 1.0
                    self.outputs = [res.path]
                    for line in res.lines:
                        self._append(line)
                    summary = (f"{res.differences} difference(s) found." if res.differences
                               else "No differences found.")
                    self._append(summary, "ok")
                    self._append(f"Saved: {res.path}", "ok")
                    self.open_btn.state(["!disabled"])
                    self.dir_btn.state(["!disabled"])
                    self.app.open_outputs(self.outputs)
                    note = f"\n\n{len(res.warnings)} warning(s) - see the log." if res.warnings else ""
                    from rstools.fsutil import excel_warning
                    long_warn = excel_warning([res.path])
                    if long_warn:
                        self._append("WARNING: " + long_warn, "warn")
                        note += f"\n\n{long_warn}"
                    self.app.notify_done("Timing Tools finished", summary)
                    messagebox.showinfo(TITLE, f"{summary}\n\n{res.path}{note}")
                elif item[0] == "s4done":
                    _k, path, lines, summary, nwarn, start = item
                    self._finish(True)
                    self.prog["value"] = 1.0
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
                                        + (f"\n\n{nwarn} warning(s) - see the log." if nwarn else ""))
                    self.app.rules_reminder(start)
                elif item[0] == "error":
                    self._finish(False)
                    self._append("ERROR: " + item[1], "error")
                    self.app.notify_done("Timing Tools failed", item[1].splitlines()[0], False)
                    messagebox.showerror(TITLE, item[1][:1500])
        except queue.Empty:
            pass
        finally:
            self._poll_id = self.after(150, self._poll)
