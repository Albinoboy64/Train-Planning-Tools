"""Data > Rules and reference data: the Network Rail rules built into the app, the Section 4 rule sets added
(add, remove, choose the one in use) and where to download the latest rules."""
from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk

from rstools import rules
from rstools.branding import APP_NAME
from rstools.theme import px

TITLE = f"{APP_NAME} - Rules and reference data"


def _d(text: str) -> str:
    d = rules.parse_date(text)
    return f"{d:%d/%m/%Y}" if d else "-"


class RulesDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Rules and reference data")
        self.transient(app)
        palette = getattr(app, "palette", None)
        if palette:
            self.configure(background=palette["bg"])
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        pad = dict(padx=12, pady=(10, 0))
        intro = ttk.Label(self, wraplength=px(self, 760), justify="left", text=(
            "The Network Rail rules the app uses. The Section 4 check uses the rule set in use whenever no PDFs are "
            "chosen: the built-in one, unless you add newer Section 4 PDFs as a rule set (or choose another)."))
        intro.grid(row=0, column=0, sticky="w", **pad)
        bf = ttk.LabelFrame(self, text="Built into the app", padding=8)
        bf.grid(row=1, column=0, sticky="ew", **pad)
        bf.columnconfigure(0, weight=1)
        today = date.today()
        for i, b in enumerate(rules.BUILT_IN):
            until = rules.parse_date(b["to"])
            stale = until is not None and today > until
            ttk.Label(bf, text=f"{b['name']} - {b['use']}. {b['covers']}; {_d(b['from'])} to {_d(b['to'])}."
                               + (" Out of date: a newer app version will carry the new rules." if stale else ""),
                      wraplength=px(self, 740), justify="left").grid(row=i, column=0, sticky="w")
        s4 = next((s for s in rules.list_sets() if s.get("built_in")), None)
        if s4 is not None:
            until = rules.parse_date(s4.get("to", ""))
            stale = until is not None and today > until
            ttk.Label(bf, text=f"{rules.BUILT_IN_S4.replace(' (built in)', '')} Section 4 (Standard Possession "
                               f"Opportunities) - the Section 4 check. {s4.get('possessions', 0):,} possession rows "
                               f"from {len(s4.get('files', []))} route PDFs; {_d(s4.get('from', ''))} to "
                               f"{_d(s4.get('to', ''))}." + (" Out of date: add the new Section 4 PDFs below." if stale
                                                              else ""),
                      wraplength=px(self, 740), justify="left").grid(row=len(rules.BUILT_IN), column=0, sticky="w")
        from rstools.berthing.layout import default_info
        lay = default_info()
        if lay is not None:
            ttk.Label(bf, text=f"Berthing chart layout - used for a new berthing chart when no chart is chosen to take "
                               f"the layout from: {lay['sheets']} sheets, from {lay['source']}.",
                      wraplength=px(self, 740), justify="left").grid(row=len(rules.BUILT_IN) + 1, column=0, sticky="w")
        sf = ttk.LabelFrame(self, text="Section 4 rule sets", padding=8)
        sf.grid(row=2, column=0, sticky="nsew", **pad)
        sf.columnconfigure(0, weight=1)
        sf.rowconfigure(0, weight=1)
        cols = ("use", "name", "periods", "rows", "files", "added")
        self.tree = ttk.Treeview(sf, columns=cols, show="headings", height=6, selectmode="browse")
        for c, text, w in (("use", "In use", 60), ("name", "Name", 200), ("periods", "Covers", 170),
                           ("rows", "Possessions", 90), ("files", "From", 300), ("added", "Added", 130)):
            self.tree.heading(c, text=text, anchor="w")
            self.tree.column(c, width=px(self, w), anchor="w", stretch=c in ("name", "files"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(sf, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        btns = ttk.Frame(sf)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.add_btn = ttk.Button(btns, text="Add Section 4 rule set...", command=self._add)
        self.add_btn.grid(row=0, column=0)
        self.use_btn = ttk.Button(btns, text="Use this set", command=self._use)
        self.use_btn.grid(row=0, column=1, padx=6)
        self.del_btn = ttk.Button(btns, text="Remove", command=self._remove)
        self.del_btn.grid(row=0, column=2)
        self.status = ttk.Label(sf, text="", style="Small.TLabel", wraplength=px(self, 740), justify="left")
        self.status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        lf = ttk.Frame(self)
        lf.grid(row=3, column=0, sticky="ew", padx=12, pady=(10, 0))
        ttk.Label(lf, text="Latest rules (Timetable Planning Rules, Engineering Access Statement):").grid(
            row=0, column=0, sticky="w")
        link = ttk.Label(lf, text=rules.RULES_URL, style="Link.TLabel", cursor="hand2")
        link.grid(row=1, column=0, sticky="w")
        link.bind("<Button-1>", lambda _e: webbrowser.open(rules.RULES_URL))
        ttk.Button(self, text="Close", command=self.destroy).grid(row=4, column=0, pady=10)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._buttons())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._fill()

    def _fill(self, select: str = ""):
        self.tree.delete(*self.tree.get_children())
        for s in rules.list_sets():
            self.tree.insert("", "end", iid=s["name"], values=(
                "Yes" if s["active"] else "", s["name"], f"{_d(s.get('from', ''))} to {_d(s.get('to', ''))}",
                s.get("possessions", ""), ", ".join(s.get("files", [])),
                "Built in" if s.get("built_in") else (s.get("added", "") or "").replace("T", " ")))
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
        if not self.tree.get_children():
            self.status.configure(text="No Section 4 rule set has been added. Download the Section 4 PDFs for your "
                                       "routes from the link below, then press 'Add Section 4 rule set...'.")
        self._buttons()

    def _buttons(self):
        sel = self.tree.selection()
        builtin = bool(sel) and sel[0] == rules.BUILT_IN_S4
        self.use_btn.state(["!disabled"] if sel else ["disabled"])
        self.del_btn.state(["!disabled"] if sel and not builtin else ["disabled"])     # built in: cannot be removed

    def _add(self):
        pdfs = filedialog.askopenfilenames(parent=self, title="Section 4 PDF(s) - one per route",
                                           filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
        if not pdfs:
            return
        name = simpledialog.askstring("Rule set name", "Name for this rule set (e.g. EAS 2028 v1):", parent=self,
                                      initialvalue=os.path.splitext(os.path.basename(pdfs[0]))[0][:40])
        if not name or not name.strip():
            return
        if name.strip() in {s["name"] for s in rules.list_sets()} and not messagebox.askyesno(
                TITLE, f"Replace the rule set '{name.strip()}'?", parent=self):
            return
        self.add_btn.state(["disabled"])
        self.status.configure(text="Reading the Section 4 PDF(s)...")

        def work():
            try:
                info = rules.add_section4_set(name.strip(), [os.path.normpath(p) for p in pdfs])
                self.after(0, lambda: self._added(info, ""))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._added(None, e))
        threading.Thread(target=work, daemon=True).start()

    def _added(self, info, error):
        if not self.winfo_exists():
            return
        self.add_btn.state(["!disabled"])
        if error:
            self.status.configure(text="")
            messagebox.showerror(TITLE, error, parent=self)
            return
        self.status.configure(text=f"Added '{info['name']}': {info['possessions']} possession rows in "
                                   f"{info['sections']} sections, now the rule set in use.")
        self._fill(info["name"])
        self._refresh_tabs()

    def _use(self):
        sel = self.tree.selection()
        if sel:
            rules.use_set(sel[0])
            self._fill(sel[0])
            self.status.configure(text=f"'{sel[0]}' is now the Section 4 rule set in use.")
            self._refresh_tabs()

    def _remove(self):
        sel = self.tree.selection()
        if not sel or sel[0] == rules.BUILT_IN_S4:          # the built-in set cannot be removed
            return
        if messagebox.askyesno(TITLE, f"Remove the rule set '{sel[0]}'? The PDFs it was read from are not "
                                      "touched.", parent=self):
            rules.remove_set(sel[0])
            self._fill()
            self._refresh_tabs()

    def _refresh_tabs(self):
        tab = getattr(self.app, "tt_tab", None)
        if tab is not None and hasattr(tab, "show_rule_set"):
            tab.show_rule_set()
        if hasattr(self.app, "refresh_rules_note"):
            self.app.refresh_rules_note()        # the header's 'Rules: ...' line
