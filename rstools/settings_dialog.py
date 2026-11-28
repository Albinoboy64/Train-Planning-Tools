"""Settings: every setting of the app in one window (Settings > Settings..., Ctrl+,), a page each - General,
Updates, Fleet data, Depots, Corridors, Berthing locations, Berthing notes, Rules and File limits. The data lists
are edited here in tables (rstools.table_editor) instead of opening their CSVs in Excel (still possible)."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from rstools.branding import APP_NAME
from rstools.theme import px

TITLE = f"{APP_NAME} - Settings"
PAGES = ("General", "Updates", "Fleet data", "Depots", "Corridors", "Berthing locations", "Berthing notes", "Rules",
         "File limits")
_OPEN: Dict[str, "SettingsWindow"] = {}


def open_settings(app, page: str = "General", **kw) -> "SettingsWindow":
    """The Settings window (one at a time), showing `page`."""
    win = _OPEN.get("win")
    if win is not None:
        try:
            if win.winfo_exists():
                win.deiconify()
                win.lift()
                win.show(page, **kw)
                return win
        except tk.TclError:
            pass
    win = _OPEN["win"] = SettingsWindow(app)
    win.show(page, **kw)
    return win


class SettingsWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Settings")
        self.transient(app)
        palette = getattr(app, "palette", None)
        if palette:
            self.configure(background=palette["bg"])
        self.geometry(f"{px(self, 1000)}x{px(self, 660)}")
        self.minsize(px(self, 640), px(self, 420))
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        side = ttk.Frame(self, padding=(10, 10, 4, 10))
        side.grid(row=0, column=0, sticky="ns")
        self.list = tk.Listbox(side, activestyle="none", exportselection=False, borderwidth=0, highlightthickness=0,
                               width=20, height=len(PAGES))
        if palette:
            self.list.configure(background=palette["panel"], foreground=palette["fg"],
                                selectbackground=palette["select"], selectforeground=palette.get("select_fg",
                                                                                                   palette["fg"]))
        for p in PAGES:
            self.list.insert("end", p)
        self.list.grid(row=0, column=0, sticky="ns")
        self.list.bind("<<ListboxSelect>>", lambda _e: self._picked())
        self.body = ttk.Frame(self, padding=(12, 10, 12, 4))
        self.body.grid(row=0, column=1, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(1, weight=1)
        self.heading = ttk.Label(self.body, text="", style="Head.TLabel")
        self.heading.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.pages: Dict[str, ttk.Frame] = {}
        self.current = ""
        bottom = ttk.Frame(self, padding=(10, 4, 12, 10))
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Button(bottom, text="Open settings folder", command=self._open_folder).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Close", command=self.close).grid(row=0, column=1, sticky="e")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        try:
            from rstools import help_text
            help_text.attach(self)
        except Exception:
            pass

    # ------------------------------------------------------------------ pages
    def show(self, page: str = "General", **kw):
        page = page if page in PAGES else "General"
        self.list.selection_clear(0, "end")
        self.list.selection_set(PAGES.index(page))
        self.list.see(PAGES.index(page))
        self._show(page, **kw)

    def _picked(self):
        sel = self.list.curselection()
        if sel:
            self._show(PAGES[sel[0]])

    def _show(self, page: str, **kw):
        if self.current and self.current in self.pages:
            self.pages[self.current].grid_remove()
        frame = self.pages.get(page)
        if frame is None:
            frame = self.pages[page] = self._make(page)
            frame.grid(row=1, column=0, sticky="nsew")
            try:
                from rstools import help_text
                help_text.attach(frame)
            except Exception:
                pass
        else:
            frame.grid()
        if kw.get("operator") and hasattr(frame, "set_operator"):
            frame.set_operator(kw["operator"])
        self.current = page
        self.heading.configure(text=page)

    def _make(self, page: str) -> ttk.Frame:
        app = self.app
        if page == "General":
            return GeneralPage(self.body, app)
        if page == "Updates":
            return UpdatesPage(self.body, app)
        if page in ("Fleet data", "Depots", "Corridors"):
            return _csv_page(self.body, app, page)
        if page == "Berthing locations":
            return BerthingPage(self.body, app)
        if page == "Berthing notes":
            from rstools.berthing.notes_dialog import NotesPanel
            return NotesPanel(self.body, app)
        if page == "Rules":
            from rstools.rules_dialog import RulesPanel
            return RulesPanel(self.body, app)
        return LimitsPage(self.body, app)

    def _unsaved(self) -> List[str]:
        out = []
        for name, frame in self.pages.items():
            ed = getattr(frame, "editor", frame)
            if getattr(ed, "dirty", False):
                out.append(name)
        return out

    def close(self):
        unsaved = self._unsaved()
        if unsaved:
            ans = messagebox.askyesnocancel(TITLE, "Save the changes on " + ", ".join(unsaved) + " first?",
                                            parent=self)
            if ans is None:
                return
            if ans:
                for name in unsaved:
                    frame = self.pages[name]
                    ed = getattr(frame, "editor", frame)
                    if not ed.save():
                        self.show(name)
                        return
        _OPEN.pop("win", None)
        self.destroy()

    def _open_folder(self):
        from rstools.branding import settings_dir
        self.app.open_outputs([settings_dir()], force=True)


# ---------------------------------------------------------------------------- General
class GeneralPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        from rstools import theme
        r = 0
        ttk.Label(self, text="Theme:").grid(row=r, column=0, sticky="nw", pady=2)
        tf = ttk.Frame(self)
        tf.grid(row=r, column=1, sticky="w")
        for i, (key, label) in enumerate(theme.MODES.items()):
            ttk.Radiobutton(tf, text=label, value=key, variable=app.theme_var, command=app._theme_chosen).grid(
                row=0, column=i, sticky="w", padx=(0, 12))
        r += 1
        ttk.Label(self, text="Text size:").grid(row=r, column=0, sticky="nw", pady=(8, 2))
        sf = ttk.Frame(self)
        sf.grid(row=r, column=1, sticky="w", pady=(8, 0))
        for i, (key, (label, _scale)) in enumerate(theme.TEXT_SIZES.items()):
            ttk.Radiobutton(sf, text=label, value=key, variable=app.size_var,
                            command=lambda: app.set_text_size(app.size_var.get())).grid(row=0, column=i, sticky="w",
                                                                                         padx=(0, 12))
        r += 1
        checks = [("Open the output when a run finishes", app.open_var, app.save_app_settings),
                  ("Notify me when a run finishes in the background", app.notify_var, app._notify_changed),
                  ("Show full paths in recent files", app.full_path_var, app._full_path_changed)]
        for text, var, cmd in checks:
            ttk.Checkbutton(self, text=text, variable=var, command=cmd).grid(row=r, column=0, columnspan=2,
                                                                             sticky="w", pady=(8 if r == 2 else 2, 0))
            r += 1
        ttk.Button(self, text="Clear remembered inputs...", command=app.clear_remembered).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(16, 0))
        r += 1
        ttk.Label(self, text="Empties the files, folders, names, stations and locations filled in from earlier runs. "
                             "Colours, options and saved settings are kept.", style="Small.TLabel",
                  wraplength=520, justify="left").grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.columnconfigure(1, weight=1)


# ---------------------------------------------------------------------------- Updates
class UpdatesPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        from rstools import updater
        self.app = app
        ttk.Checkbutton(self, text="Check for updates when the app starts", variable=app.auto_update_var,
                        command=app._auto_update_changed).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Button(self, text="Check for updates now...", command=app.check_for_updates).grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(self, text="GitHub access token:").grid(row=2, column=0, sticky="w", pady=(16, 0))
        self.token = tk.StringVar(value=updater.unprotect(app.opts.github_token))
        ttk.Entry(self, textvariable=self.token, show="*", width=48).grid(row=2, column=1, sticky="w", padx=4,
                                                                          pady=(16, 0))
        ttk.Button(self, text="Save token", command=self._save).grid(row=2, column=2, pady=(16, 0))
        ttk.Label(self, text=f"Only needed while the GitHub repository is private: a fine-grained token with "
                             f"read-only 'Contents' access to {updater.REPO}. Stored encrypted for your Windows "
                             "login; leave blank and save to remove it.", style="Small.TLabel",
                  wraplength=px(self, 560), justify="left").grid(row=3, column=0, columnspan=3, sticky="w",
                                                                 pady=(4, 0))
        self.status = ttk.Label(self, text="", style="Small.TLabel")
        self.status.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _save(self):
        from rstools import updater
        self.app.opts.github_token = updater.protect(self.token.get().strip())
        self.app.save_app_settings()
        self.status.configure(text="Token saved." if self.token.get().strip() else "Token removed.")


# ---------------------------------------------------------------------------- data lists
def _csv_page(master, app, page: str) -> ttk.Frame:
    from rstools.table_editor import csv_editor
    frame = ttk.Frame(master)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    open_path = (lambda p: app.open_outputs([p], force=True))
    if page == "Fleet data":
        from rstools.statspack import fleet
        text = ("Each unit type: its operator, seats, units and length. Used by the stats pack, unit reports, "
                "capacity reports, berthing charts and station working books.")
        numbers = [c for c in fleet.COLUMNS if c not in ("Class Name", "Operator", "Power Type")]
        ed = csv_editor(frame, fleet.ensure_user_copy, fleet.DEFAULT_CSV, numbers, open_path=open_path)
    elif page == "Depots":
        from rstools.statspack import units
        text = ("The locations that are depots (TIPLOC, the depot each belongs to and its operator), for unit "
                "reports and charts. A blank depot marks a location as not a depot.")
        ed = csv_editor(frame, units.ensure_user_depots, units.DEFAULT_DEPOTS, open_path=open_path)
    else:
        from rstools.statspack import seats
        text = ("The corridors and service groups of capacity reports: the stations on the route, the stations a "
                "train must also call at or pass, and the fleets or headcodes it is limited to.")
        tab = getattr(app, "stats_tab", None)
        ed = csv_editor(frame, seats.ensure_user_groups, seats.DEFAULT_GROUPS, ["Minimum route stations"],
                        widths={"Route stations": 300, "Name": 260}, open_path=open_path,
                        on_saved=(lambda: tab._load_groups()) if tab is not None and hasattr(tab, "_load_groups")
                        else None)
    ttk.Label(frame, text=text, style="Small.TLabel", wraplength=px(frame, 640), justify="left").grid(
        row=0, column=0, sticky="w", pady=(0, 6))
    ed.grid(row=1, column=0, sticky="nsew")
    frame.editor = ed                                   # type: ignore[attr-defined]
    return frame


# ---------------------------------------------------------------------------- berthing locations
class BerthingPage(ttk.Frame):
    """The location set of each operator's berthing chart: its sheets and berths, capacities, TIPLOCs and codes."""

    def __init__(self, master, app):
        super().__init__(master)
        from rstools.table_editor import Column, TableEditor
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Chart for:").grid(row=0, column=0, sticky="w")
        self.op = tk.StringVar(value="SNGX")
        for i, op in enumerate(("SNGX", "TLGN")):
            ttk.Radiobutton(top, text=op, value=op, variable=self.op, command=self._operator).grid(
                row=0, column=i + 1, padx=(8, 4))
        self.info_lbl = ttk.Label(self, text="", style="Small.TLabel", wraplength=px(self, 640), justify="left")
        self.info_lbl.grid(row=1, column=0, sticky="w", pady=(6, 0))
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="w", pady=(6, 6))
        self.make_btn = ttk.Button(bar, text="Make from XML...", command=self._make)
        self.make_btn.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(bar, text="Back to default", command=self._reset).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(bar, text="Open berth list in Excel", command=self._berth_list).grid(row=0, column=2)
        cols = [Column("Sheet", 170), Column("Location", 190), Column("Berth", 160), Column("Capacity", 80),
                Column("TIPLOC", 90), Column("Codes", 100)]
        self._source = ""
        self.editor = TableEditor(self, cols, load=self._rows, save=self._save, default=self._default,
                                  on_saved=self._saved)
        self.editor.grid(row=3, column=0, sticky="nsew")
        self._operator()

    def set_operator(self, op: str):
        if op.upper() in ("SNGX", "TLGN") and op.upper() != self.op.get():
            self.op.set(op.upper())
            self._operator()

    def _rows(self):
        from rstools.berthing import sets
        return sets.rows(self.op.get())

    def _default(self):
        from rstools.berthing import sets
        return sets.rows(self.op.get(), builtin=True)

    def _save(self, rows) -> bool:
        from rstools.berthing import sets
        ok = sets.save_rows(self.op.get(), rows, self._source or "edited in Settings")
        self._source = ""
        return ok

    def _saved(self):
        self._describe()
        if hasattr(self.app, "_berth_operator_changed"):
            self.app._berth_operator_changed()

    def _operator(self):
        if self.editor.dirty and messagebox.askyesno(TITLE, "Save the changes to the other chart's locations first?",
                                                     parent=self):
            other = "TLGN" if self.op.get() == "SNGX" else "SNGX"
            from rstools.berthing import sets
            sets.save_rows(other, self.editor.rows, "edited in Settings")
        self.editor.reload()
        self._describe()

    def _describe(self):
        from rstools.berthing import sets
        op = self.op.get()
        i = sets.info(op)
        if i["saved"]:
            text = (f"Your {op} locations: {i['sheets']} sheet(s), {i['berths']} berth(s), from {i['source']} "
                    f"({i['made']}). Every {op} chart starts from these; 'Choose locations...' on a chart leaves "
                    "some out or adds others.")
        elif op == "SNGX":
            text = (f"The app's built-in SNGX locations: {i['sheets']} sheet(s), {i['berths']} berth(s). Change "
                    "them here and Save to keep your own.")
        else:
            text = ("TLGN has no location set yet, so each TLGN chart takes its locations from its XML. Press "
                    "'Make from XML...' to make the set from a TLGN XML, check it, then Save.")
        self.info_lbl.configure(text=text)

    def _make(self):
        paths = filedialog.askopenfilenames(parent=self, title=f"Attune XML for the {self.op.get()} locations",
                                            filetypes=[("Attune XML", "*.xml"), ("All files", "*.*")])
        if not paths:
            return
        op = self.op.get()
        self.make_btn.state(["disabled"])
        self.info_lbl.configure(text="Reading the XML...")

        box: list = []                       # the helper thread's result, picked up here (Tk is not thread-safe)

        def work():
            try:
                from rstools.berthing import engine
                box.append((engine.make_location_set(list(paths), op), ""))
            except Exception as exc:
                box.append((None, str(exc)))
        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def wait():
            if not self.winfo_exists():
                return
            if box:
                self._made(box[0][0], paths, box[0][1], op)
            else:
                self.after(100, wait)
        self.after(100, wait)

    def _made(self, sheets, paths, error: str, op: str = ""):
        if not self.winfo_exists():
            return
        self.make_btn.state(["!disabled"])
        if op and op != self.op.get():       # another chart type was chosen meanwhile: not its locations
            self._describe()
            return
        if error:
            self._describe()
            messagebox.showwarning(TITLE, error, parent=self)
            return
        from rstools.berthing import auto
        rows = []
        for sh in sheets:
            for b in sh.blocks:
                where = sh.sections[b.section] if len(sh.sections) > 1 and 0 <= b.section < len(sh.sections) else ""
                rows.append({"Sheet": sh.name, "Location": where, "Berth": b.label, "Capacity": b.capacity,
                             "TIPLOC": auto.berth_tiploc(sh, b), "Codes": b.codes})
        self.editor.rows = rows
        self.editor._fill()
        self.editor._set_dirty(True)
        self._source = ", ".join(os.path.basename(p) for p in paths)
        self.info_lbl.configure(text=f"{len(sheets)} location(s) found in {self._source}. Add capacities, rename or "
                                 "remove rows as needed, then press Save.")

    def _reset(self):
        from rstools.berthing import sets
        op = self.op.get()
        if not messagebox.askyesno(TITLE, f"Forget your {op} locations? " + (
                "SNGX charts go back to the app's built-in locations." if op == "SNGX" else
                "TLGN charts take their locations from each XML again."), parent=self):
            return
        sets.reset(op)
        self.editor.reload()
        self._saved()

    def _berth_list(self):
        from rstools.berthing.mapping import ensure_user_copy
        self.app.open_outputs([ensure_user_copy()], force=True)


# ---------------------------------------------------------------------------- file limits
class LimitsPage(ttk.Frame):
    """The size limits of the files the app reads (rstools.limits), changed in limits.json."""

    def __init__(self, master, app):
        super().__init__(master)
        from rstools import limits
        ttk.Label(self, text="The largest files the app reads. They are far above any real planning file; raise one "
                             "only if a genuine file is refused as too large.", style="Small.TLabel",
                  wraplength=px(self, 640), justify="left").grid(row=0, column=0, columnspan=4, sticky="w",
                                                                 pady=(0, 6))
        self.columnconfigure(3, weight=1)               # the note's spare width goes here, not between the columns
        self.vars: Dict[str, tk.StringVar] = {}
        for r, name in enumerate(limits.DEFAULTS, start=1):
            mb = _is_mb(name)
            value = limits.get(name)
            ttk.Label(self, text=_limit_label(name)).grid(row=r, column=0, sticky="w", pady=1)
            v = self.vars[name] = tk.StringVar(value=_show(value, mb))
            ttk.Entry(self, textvariable=v, width=12).grid(row=r, column=1, sticky="w", padx=4, pady=1)
            ttk.Label(self, text="MB" if mb else "", style="Small.TLabel").grid(row=r, column=2, sticky="w")
        bar = ttk.Frame(self)
        bar.grid(row=len(limits.DEFAULTS) + 1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(bar, text="Save", command=self.save).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(bar, text="Back to defaults", command=self._reset).grid(row=0, column=1)
        self.status = ttk.Label(self, text="", style="Small.TLabel")
        self.status.grid(row=len(limits.DEFAULTS) + 2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.dirty = False
        for v in self.vars.values():
            v.trace_add("write", lambda *_a: setattr(self, "dirty", True))

    def save(self) -> bool:
        from rstools import limits
        values = {}
        for name, v in self.vars.items():
            got = parse_limit(name, v.get())
            if got is None:
                messagebox.showwarning(TITLE, f"{_limit_label(name)}: '{v.get()}' is not a positive number.",
                                       parent=self)
                return False
            values[name] = got
        if not save_limits(values):
            messagebox.showwarning(TITLE, "The settings folder could not be written to.", parent=self)
            return False
        limits.reload()
        self.dirty = False
        self.status.configure(text="Saved. The new limits are used from the next file read.")
        return True

    def _reset(self):
        from rstools import limits
        for name, v in self.vars.items():
            v.set(_show(limits.DEFAULTS[name], _is_mb(name)))
        self.dirty = True
        self.status.configure(text="Back to the defaults - press Save to keep them.")


def _is_mb(name: str) -> bool:
    return name.endswith("_BYTES") or name in ("ZIP_PART_LIMIT", "ZIP_TOTAL_LIMIT", "ZIP_RATIO_FROM")


def _show(value: int, mb: bool) -> str:
    if not mb:
        return str(value)
    v = value / (1024 * 1024)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _limit_label(name: str) -> str:
    return {"XML_MAX_BYTES": "Attune XML", "XML_PART_MAX_BYTES": "XML part of an Office file", "VPT_MAX_BYTES": "VPT",
            "PDF_MAX_BYTES": "PDF", "PDF_MAX_PAGES": "PDF pages", "XLS_MAX_BYTES": "Older Excel (.xls) CWN",
            "CSV_MAX_BYTES": "Train list (CSV)", "ZIP_PART_LIMIT": "One part of an Office file, unpacked",
            "ZIP_TOTAL_LIMIT": "Whole Office file, unpacked", "ZIP_RATIO_LIMIT": "Unpacked / packed size of a part",
            "ZIP_RATIO_FROM": "Part size the ratio is checked from", "META_MAX_BYTES": "Comparison data in an output",
            "SETTINGS_CSV_MAX_BYTES": "Settings list (fleet, depots...)", "PROGRESS_MAX_BYTES": "Live View progress",
            "BERTH_NOTES_MAX_BYTES": "Berthing notes", "BERTH_NOTE_CHARS": "Characters in one berthing note",
            "BERTH_SET_MAX_BYTES": "Berthing location set"}.get(name, name)


def parse_limit(name: str, text: str) -> Optional[int]:
    """A limit as typed (MB for sizes) -> the whole number kept in limits.json; None if it is not positive."""
    try:
        v = float(str(text).strip().replace(",", ""))
    except ValueError:
        return None
    if v <= 0:
        return None
    return int(round(v * 1024 * 1024)) if _is_mb(name) else int(round(v))


def save_limits(values: Dict[str, int]) -> bool:
    """limits.json with the limits that differ from the defaults (removed when none do)."""
    from rstools import limits
    from rstools.branding import settings_dir
    from rstools.fsutil import write_json
    path = os.path.join(settings_dir(), limits.FILE_NAME)
    changed = {k: int(v) for k, v in values.items() if k in limits.DEFAULTS and int(v) > 0
               and int(v) != limits.DEFAULTS[k]}
    if not changed:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True
    return write_json(path, changed)

