"""Berthing charts > Choose locations...: tick the locations on the chart. The layout's sheets can be unticked to
leave them off; the places units berth overnight in the XML can be ticked to add them (for TLGN, whose chart is
laid out from the XML, they are all on it unless unticked); and any location can be typed in by name or TIPLOC."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional, Sequence, Tuple

from rstools.branding import APP_NAME
from rstools.theme import px

from . import auto


class LocationsDialog(tk.Toplevel):
    """`find()` reads the XML(s) for the places units berth (None when no XML is chosen yet). `result` is
    (leave out, add) after OK, else None."""

    def __init__(self, app, operator: str, rows: List[auto.Choice],
                 find: Optional[Callable[[], Sequence[auto.Place]]] = None):
        super().__init__(app)
        self.app, self.operator, self.rows, self.find = app, operator, rows, find
        self.result: Optional[Tuple[List[str], List[str]]] = None
        self.vars: List[tk.BooleanVar] = []
        self.title(f"Locations on the {operator} berthing chart")
        self.transient(app)
        palette = getattr(app, "palette", None)
        if palette:
            self.configure(background=palette["bg"])
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        intro = ("Untick a location to leave it off the chart. Find berthing locations lists where units berth "
                 "overnight in the XML; tick one to add it. A location added gets a sheet with a berth for each "
                 "platform or siding road the XML uses there.") if operator == "SNGX" else (
                "The TLGN chart has a sheet for every place TLGN units berth overnight in the XML, except depots. "
                "Find berthing locations lists them: untick one to leave it off, or tick a depot to add it.")
        ttk.Label(self, text=intro, wraplength=px(self, 520), justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6))
        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        bg = palette["bg"] if palette else None
        self.canvas = tk.Canvas(frame, highlightthickness=0, width=px(self, 520), height=px(self, 320),
                                **({"background": bg} if bg else {}))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.inner = ttk.Frame(self.canvas, padding=6)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        tools = ttk.Frame(self, padding=(12, 6, 12, 0))
        tools.grid(row=2, column=0, columnspan=2, sticky="ew")
        tools.columnconfigure(1, weight=1)
        self.find_btn = ttk.Button(tools, text="Find berthing locations in the XML", command=self._find,
                                   state="normal" if find else "disabled")
        self.find_btn.grid(row=0, column=0, columnspan=2, sticky="w")
        self.status = ttk.Label(tools, text="" if find else "Choose the Attune XML first to list where units berth.",
                                style="Small.TLabel")
        self.status.grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(tools, text="Add a location (name or TIPLOC):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.typed = tk.StringVar()
        entry = ttk.Entry(tools, textvariable=self.typed)
        entry.grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        entry.bind("<Return>", lambda _e: self._add())
        ttk.Button(tools, text="Add", command=self._add).grid(row=1, column=2, sticky="w", pady=(6, 0))
        bar = ttk.Frame(self, padding=(12, 10, 12, 10))
        bar.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Button(bar, text="Back to default", command=self._reset).grid(row=0, column=0)
        bar.columnconfigure(1, weight=1)
        ttk.Button(bar, text="OK", command=self._ok).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(bar, text="Cancel", command=self.destroy).grid(row=0, column=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._draw()

    def _bold(self):
        from tkinter import font
        if not hasattr(self, "_bold_font"):
            self._bold_font = font.nametofont("TkDefaultFont").copy()
            self._bold_font.configure(weight="bold")
        return self._bold_font

    def _draw(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.vars = []
        if not self.rows:
            ttk.Label(self.inner, text="No locations yet: find them in the XML or type one below.").grid(
                row=0, column=0, sticky="w")
        on = [r for r in self.rows if r.default]
        off = [r for r in self.rows if not r.default]
        line = 0
        for head, group in (("On the chart by default", on), ("Not on the chart unless ticked", off)):
            if not group:
                continue
            ttk.Label(self.inner, text=head, font=self._bold()).grid(row=line, column=0, sticky="w",
                                                                       pady=(6 if line else 0, 2))
            line += 1
            for r in group:
                var = tk.BooleanVar(value=r.ticked)
                var.trace_add("write", lambda *_a, row=r, v=var: setattr(row, "ticked", bool(v.get())))
                ttk.Checkbutton(self.inner, text=r.text, variable=var).grid(row=line, column=0, sticky="w", padx=(8, 0))
                self.vars.append(var)
                line += 1

    def _find(self):
        if self.find is None:
            return
        self.find_btn.configure(state="disabled")
        self.status.configure(text="Reading the XML...")
        out: dict = {}

        def work():
            try:
                out["found"] = self.find()
            except Exception as exc:          # a message in the window, not a traceback
                out["error"] = str(exc)

        def wait():
            if t.is_alive():
                self.after(150, wait)
                return
            self.find_btn.configure(state="normal")
            if "error" in out:
                self.status.configure(text="")
                messagebox.showwarning(APP_NAME, out["error"], parent=self)
                return
            found = out.get("found") or []
            self.rows = auto.merge_places(self.rows, found, self.operator)
            self.status.configure(text=f"{len(found)} berthing location{'s' if len(found) != 1 else ''} found.")
            self._draw()
            if self.operator == "SNGX":                 # the new ones are at the end of the list
                self.update_idletasks()
                self.canvas.yview_moveto(1.0)
        t = threading.Thread(target=work, daemon=True)
        t.start()
        wait()

    def _add(self):
        text = " ".join(self.typed.get().split())
        if not text:
            return
        if not any(auto.norm(r.key) == auto.norm(text) for r in self.rows):
            self.rows.append(auto.Choice(text, f"{text} (added)", False, True))
        else:
            for r in self.rows:
                if auto.norm(r.key) == auto.norm(text):
                    r.ticked = True
        self.typed.set("")
        self._draw()

    def _reset(self):
        self.rows = [r for r in self.rows if r.default or not r.text.endswith("(added)")]
        for r in self.rows:
            r.ticked = r.default
        self._draw()

    def _ok(self):
        self.result = auto.chosen(self.rows)
        self.destroy()
