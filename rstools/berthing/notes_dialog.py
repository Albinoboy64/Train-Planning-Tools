"""Data > Berthing chart notes: change, add or remove the notes of each berthing chart location, for the current
timetable and the next five. The notes are kept and applied by rstools.berthing.notes; this is only the window."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from rstools.branding import APP_NAME
from rstools.theme import px

from . import notes
from .layout import load_default

TITLE = f"{APP_NAME} - Berthing chart notes"
SEP = "  –  "                  # 'Brighton  -  Sdg 3' in the location list


class NotesDialog(tk.Toplevel):
    def __init__(self, app):
        layout = load_default()                         # BerthingError if the built-in layout is missing
        super().__init__(app)
        self.app = app
        self.title("Berthing chart notes")
        self.transient(app)
        palette = getattr(app, "palette", None)
        if palette:
            self.configure(background=palette["bg"])
        self.data = notes.load()
        self.timetables = notes.upcoming_timetables()
        self.berths = {f"{sh.name}{SEP}{b.label}": (k, b) for k, sh, b in notes.berths(layout)}
        self.names: List[str] = list(self.berths)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)
        pad = dict(padx=(12, 4), pady=(8, 0))
        ttk.Label(self, wraplength=px(self, 620), justify="left", text=(
            "The notes shown for each location on berthing charts made for a timetable. A location you have not "
            "changed keeps the notes of the built-in chart layout. Changes are used for every chart made for that "
            "timetable, and can be turned off on the main screen ('Show location notes on the chart').")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 0))
        ttk.Label(self, text="Timetable:").grid(row=1, column=0, sticky="w", **pad)
        self.tt_var = tk.StringVar(value=notes.timetable_label(self.timetables[0]))
        tt = ttk.Combobox(self, textvariable=self.tt_var, state="readonly", width=12,
                          values=[notes.timetable_label(t) for t in self.timetables])
        tt.grid(row=1, column=1, sticky="w", padx=4, pady=(8, 0))
        tt.bind("<<ComboboxSelected>>", lambda _e: self._show())
        ttk.Label(self, text="Location:").grid(row=2, column=0, sticky="w", **pad)
        self.loc_var = tk.StringVar(value=self.names[0] if self.names else "")
        loc = self.loc_box = ttk.Combobox(self, textvariable=self.loc_var, values=self.names, height=20)
        loc.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(4, 12), pady=(8, 0))
        from rstools.autocomplete import Suggest
        Suggest(loc, lambda: self.names, on_pick=lambda _n: self._show())
        loc.bind("<<ComboboxSelected>>", lambda _e: self._show())
        ttk.Label(self, text="Beside the name (if no capacity):").grid(row=3, column=0, sticky="w", **pad)
        self.side_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.side_var).grid(row=3, column=1, columnspan=2, sticky="ew", padx=(4, 12),
                                                          pady=(8, 0))
        nf = ttk.LabelFrame(self, text=f"Notes - one per line ('A{notes.SPLIT}B' for the two columns; a long note "
                                       "goes across the day columns)", padding=6)
        nf.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=12, pady=(8, 0))
        nf.columnconfigure(0, weight=1)
        nf.rowconfigure(0, weight=1)
        self.text = tk.Text(nf, height=8, width=70, wrap="word", undo=True)
        if palette:
            self.text.configure(background=palette["field"], foreground=palette["fg"],
                                insertbackground=palette["fg"])
        self.text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(nf, orient="vertical", command=self.text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=sb.set)
        self.state_lbl = ttk.Label(self, text="", style="Small.TLabel", wraplength=px(self, 620), justify="left")
        self.state_lbl.grid(row=5, column=0, columnspan=3, sticky="w", padx=12, pady=(6, 0))
        bf = ttk.Frame(self)
        bf.grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        for i, (text, cmd) in enumerate((("Save", self._save), ("Remove notes", self._remove),
                                         ("Back to built-in", self._reset),
                                         ("Copy from previous timetable", self._copy))):
            ttk.Button(bf, text=text, command=cmd).grid(row=0, column=i, padx=(0, 6))
        ttk.Button(bf, text="Close", command=self.destroy).grid(row=0, column=9, sticky="e")
        bf.columnconfigure(8, weight=1)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._show()
        self.grab_set()

    # ------------------------------------------------------------------ state
    def _tt(self) -> str:
        label = self.tt_var.get()
        return next((t for t in self.timetables if notes.timetable_label(t) == label), self.timetables[0])

    def _berth(self) -> Optional[tuple]:
        return self.berths.get(self.loc_var.get().strip())

    def _saved(self, tt: str) -> Dict[str, dict]:
        return self.data.setdefault(tt, {})

    def _show(self):
        """Fill the boxes with the chosen location's notes for the chosen timetable."""
        berth = self._berth()
        self.text.delete("1.0", "end")
        self.side_var.set("")
        if berth is None:
            self.state_lbl.configure(text="Choose a location from the list.")
            return
        k, blk = berth
        tt = self._tt()
        e = self._saved(tt).get(k)
        shown = e if e is not None else notes.entry_of(blk)
        self.side_var.set(shown["label_note"])
        self.text.insert("1.0", "\n".join(shown["notes"]))
        changed = len(self._saved(tt))
        label = notes.timetable_label(tt)
        if e is None:
            state = "The built-in layout's notes (not changed for this timetable)."
        elif e.get("removed"):
            state = f"Notes removed for {label}."
        else:
            state = f"Changed for {label}."
        self.state_lbl.configure(text=f"{state} {changed} location(s) changed for {label}.")

    def _store(self, e: Optional[dict]):
        berth = self._berth()
        if berth is None:
            messagebox.showwarning(TITLE, "Choose a location from the list.", parent=self)
            return
        saved = self._saved(self._tt())
        if e is None:
            saved.pop(berth[0], None)
        else:
            saved[berth[0]] = e
        if not notes.save(self.data):
            messagebox.showwarning(TITLE, "The notes could not be saved: the settings folder cannot be written.",
                                   parent=self)
        self._show()

    def _save(self):
        lines = [x for x in self.text.get("1.0", "end").splitlines() if x.strip()]
        self._store(notes.entry(self.side_var.get(), lines))

    def _remove(self):
        self._store(notes.entry(removed=True))

    def _reset(self):
        self._store(None)

    def _copy(self):
        """The previous timetable's notes for this location (changed or built-in) into the boxes, to edit."""
        berth = self._berth()
        i = self.timetables.index(self._tt())
        if berth is None or i == 0:
            messagebox.showinfo(TITLE, "There is no earlier timetable in the list to copy from." if berth else
                                "Choose a location from the list.", parent=self)
            return
        e = self._saved(self.timetables[i - 1]).get(berth[0]) or notes.entry_of(berth[1])
        self.side_var.set(e["label_note"])
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(e["notes"]))
        self.state_lbl.configure(text=f"Copied from {notes.timetable_label(self.timetables[i - 1])} - press Save "
                                      "to keep it.")
