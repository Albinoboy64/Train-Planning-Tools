"""Train Planning Tools window (tkinter) and its CWN Tools tab."""
from __future__ import annotations

import dataclasses
import datetime
import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
import webbrowser
from typing import Dict
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog

from rstools import theme, updater
from rstools.branding import APP_NAME
from rstools.update_dialog import UpdateDialog
from rstools.widgets import ScrollPage, Tooltip

from . import __version__
from .compare import CATEGORIES
from .days import DAY_LABELS
from .loader import FILE_TYPES, SUPPORTED_EXT, LoadError
from .meta import is_comparison_output, read_meta_file
from .options import Options, PRESET_COLOURS, default_categories, default_name

APP_TITLE = APP_NAME
APP_WIDE = ("last_tab", "theme", "text_size", "recent", "check_updates", "github_token", "notify_done", "saved",
            "live_details_open")
TAB_NAMES = ("CWN Tools", "Stats Pack", "Timetable Comparison", "Live View")
REPORT_FORMATS = {"xlsx": "Excel", "pdf": "PDF", "docx": "Word"}
ASSETS = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      "rstools", "assets")
HAS_OLD = {k: has_old for k, _label, has_old, _desc in CATEGORIES}
ERROR_LOG = os.path.join(os.path.dirname(Options.settings_path()), "error.log")


def _write_error_log(text: str) -> str:
    """Keep the details of an unexpected error for support; returns the log path ('' if unwritable)."""
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        if os.path.exists(ERROR_LOG) and os.path.getsize(ERROR_LOG) > 1024 * 1024:   # keep it small: newest half
            with open(ERROR_LOG, "rb") as fh:
                fh.seek(-512 * 1024, os.SEEK_END)
                tail = fh.read()
            with open(ERROR_LOG, "wb") as fh:
                fh.write(b"(older entries removed)\n" + tail[tail.find(b"\n=====") + 1:])
        with open(ERROR_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.datetime.now():%d/%m/%Y %H:%M:%S}  v{__version__} =====\n{text}\n")
        return ERROR_LOG
    except OSError:
        return ""


OPENABLE = (".xlsx", ".xlsm", ".xls", ".pdf", ".docx", ".csv", ".txt", ".log")


def _open_path(path: str):
    """Open an output (or a folder) as if double-clicked. Only folders and document files: never a program
    or script, whatever a path ends up holding."""
    if not (os.path.isdir(path) or os.path.splitext(path)[1].lower() in OPENABLE):
        messagebox.showerror(APP_TITLE, f"Only folders and documents are opened from the app:\n{path}")
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        messagebox.showerror(APP_TITLE, f"Could not open {path}\n{exc}")


class ColourPicker(ttk.Frame):
    def __init__(self, master, initial: str, **kw):
        super().__init__(master, **kw)
        self.value = initial.upper()[-6:]
        names = list(PRESET_COLOURS) + ["Custom..."]
        self.combo = ttk.Combobox(self, values=names, state="readonly", width=14)
        self.combo.grid(row=0, column=0, padx=(0, 6))
        self.swatch = tk.Label(self, width=4, relief="solid", bd=1)
        self.swatch.grid(row=0, column=1)
        self.combo.bind("<<ComboboxSelected>>", self._chosen)
        self.set(self.value)

    def set(self, hexcol: str):
        self.value = hexcol.upper()[-6:]
        name = next((n for n, v in PRESET_COLOURS.items() if v == self.value), None)
        self.combo.set(name or f"Custom #{self.value}")
        self.swatch.configure(bg="#" + self.value)

    def _chosen(self, _e=None):
        name = self.combo.get()
        if name in PRESET_COLOURS:
            self.set(PRESET_COLOURS[name])
            return
        res = colorchooser.askcolor(color="#" + self.value, title="Choose highlight colour")
        if res and res[1]:
            self.set(res[1].lstrip("#"))
        else:
            self.set(self.value)


class MenuBar(ttk.Frame):
    """A menu bar of themed labels that open drop-down menus (Alt+O / Alt+H, or a click)."""

    def __init__(self, master):
        super().__init__(master, style="Bar.TFrame", padding=(2, 1))
        self._items = []

    def add(self, label: str, menu: tk.Menu):
        item = ttk.Label(self, text=label, style="Bar.TLabel", underline=0, takefocus=False)
        item.pack(side="left")
        item.bind("<Button-1>", lambda _e: self.open(item, menu))
        item.bind("<Enter>", lambda _e: item.configure(style="BarHot.TLabel"))
        item.bind("<Leave>", lambda _e: item.configure(style="Bar.TLabel"))
        self.winfo_toplevel().bind(f"<Alt-{label[0].lower()}>", lambda _e: self.open(item, menu) or "break")
        self._items.append((item, menu))

    @staticmethod
    def open(item, menu: tk.Menu):
        try:
            menu.tk_popup(item.winfo_rootx(), item.winfo_rooty() + item.winfo_height())
        finally:
            menu.grab_release()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  v{__version__}")
        self._set_icon()
        self.opts = Options.load()
        self.q: "queue.Queue" = queue.Queue()
        self.running = False
        self.result = None
        self.prev_info_token = 0
        self._dnd = self._load_dnd()          # before the tabs are built, so both can take drops
        self.open_var = tk.BooleanVar(value=self.opts.open_when_done)
        self.theme_var = tk.StringVar(value=self.opts.theme)
        self.size_var = tk.StringVar(value=self.opts.text_size if self.opts.text_size in theme.TEXT_SIZES
                                     else "normal")
        self._scale = theme.setup_fonts(self, self.size_var.get())
        self.palette = theme.apply(self, self.opts.theme)
        forced = os.environ.get("TPT_COMPACT", "")             # '1' / '0' to force it (testing)
        self.compact = forced == "1" or (forced != "0" and self.winfo_screenheight() < theme.COMPACT_BELOW)
        self._build()
        self._size_columns(self._scale)
        self._build_menu()
        self._enable_drag_and_drop(self.outer)
        self._load_into_widgets()
        if self.compact:                                       # a short screen (e.g. a 1366 x 768 laptop)
            theme.set_compact(self, True)
            self._head.configure(padding=(12, 2, 12, 0))
            self.live_tab.notes.configure(height=3)
        self.minsize(1080, 560 if self.compact else 720)
        self._fit_to_screen()
        pages = (None, self.stats_page, self.tt_page, self.live_page)
        if 0 < self.opts.last_tab < len(pages):
            self.notebook.select(pages[self.opts.last_tab])
        for key in ("<F5>", "<Control-Return>"):
            self.bind(key, self._run_current_tab)
        for i in range(4):                                   # Ctrl+1 / 2 / 3 / 4: switch tab
            self.bind(f"<Control-Key-{i + 1}>", lambda _e, i=i: self.notebook.select(i) or "break")
        for keys, step in ((("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"), 1),
                           (("<Control-minus>", "<Control-KP_Subtract>"), -1), (("<Control-Key-0>",), 0)):
            for key in keys:                                 # Ctrl + / - / 0: text size
                self.bind(key, lambda _e, s=step: self.step_text_size(s) or "break")
        self.bind("<F1>", lambda _e: webbrowser.open(f"https://github.com/{updater.REPO}#readme"))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.apply_theme(self.opts.theme)
        self._poll_id = self.after(100, self._poll)
        self._theme_id = self.after(5000, self._follow_windows_theme)
        self.after(3000, self._startup_update_check)
        self.after(4000, lambda: updater.after_start(                 # tidy up and refresh icons after an update
            os.path.join(os.path.dirname(Options.settings_path()), "installed.txt")))
        from rstools.help_text import attach
        attach(self)                                             # help when the mouse rests on a control
        theme.watch_focus_cues(self)                             # focus outlines only for keyboard use

    def _fit_to_screen(self):
        """Open big enough to show a whole tab without scrolling, but never larger than the screen."""
        self.update_idletasks()
        bodies = [self.outer, self.stats_tab, self.tt_tab]
        width = max(b.winfo_reqwidth() for b in bodies) + 40
        chrome = self.winfo_reqheight() - self.notebook.winfo_reqheight() + 40     # header + tab strip
        height = max(b.winfo_reqheight() for b in bodies) + chrome
        width = min(max(width, 1080), self.winfo_screenwidth() - 40)
        height = min(max(height, 720), self.winfo_screenheight() - 80)
        self.geometry(f"{width}x{height}")

    # ------------------------------------------------------------ settings shared by both tabs
    def apply_theme(self, mode: str):
        self.opts.theme = mode if mode in theme.MODES else "system"
        self.palette = theme.apply(self, self.opts.theme)
        self.theme_var.set(self.opts.theme)
        live = getattr(self, "live_tab", None)
        if live is not None:
            live.retheme(self.palette)

    def set_text_size(self, size: str):
        """Resize all text in the window (and table rows) to one of theme.TEXT_SIZES."""
        size = size if size in theme.TEXT_SIZES else "normal"
        self.size_var.set(size)
        self.opts.text_size = size
        scale = theme.setup_fonts(self, size)
        self.apply_theme(self.opts.theme)
        self._show_logo()
        self._size_columns(scale)
        if self.state() != "zoomed":
            self._fit_to_screen()
        self.save_app_settings()

    def _size_columns(self, scale: float):
        """Two-column tabs keep room for their text at the chosen text size."""
        for frame, widths in ((self.outer, (500, 480)), (self.stats_tab, (520, 470)), (self.tt_tab, (520, 470))):
            for col, w in enumerate(widths):
                frame.columnconfigure(col, minsize=round(w * scale))
        stack = [self]
        while stack:                                         # wrapped text keeps the same number of words a line
            w = stack.pop()
            stack.extend(w.winfo_children())
            if isinstance(w, ttk.Label):
                base = getattr(w, "_base_wrap", None)
                if base is None:
                    try:
                        base = w._base_wrap = int(str(w.cget("wraplength")) or 0)
                    except (tk.TclError, ValueError):
                        base = w._base_wrap = 0
                if base:
                    w.configure(wraplength=round(base * scale))

    def step_text_size(self, step: int):
        sizes = list(theme.TEXT_SIZES)
        i = sizes.index(self.size_var.get()) if self.size_var.get() in sizes else 1
        self.set_text_size("normal" if step == 0 else sizes[max(0, min(len(sizes) - 1, i + step))])

    def _theme_chosen(self):
        self.apply_theme(self.theme_var.get())
        self.save_app_settings()

    # ------------------------------------------------------------ menu bar
    def _build_menu(self):
        """Options / Help bar, drawn with themed widgets (a native Windows menu bar ignores the theme)."""
        bar = MenuBar(self)
        opt = tk.Menu(bar, tearoff=False)
        themes = tk.Menu(opt, tearoff=False)
        for key, label in theme.MODES.items():
            themes.add_radiobutton(label=label, value=key, variable=self.theme_var, command=self._theme_chosen)
        opt.add_cascade(label="Theme", menu=themes)
        sizes = tk.Menu(opt, tearoff=False)
        for key, (label, _scale) in theme.TEXT_SIZES.items():
            sizes.add_radiobutton(label=label, value=key, variable=self.size_var,
                                  command=lambda: self.set_text_size(self.size_var.get()))
        sizes.add_separator()
        sizes.add_command(label="Larger", accelerator="Ctrl++", command=lambda: self.step_text_size(1))
        sizes.add_command(label="Smaller", accelerator="Ctrl+-", command=lambda: self.step_text_size(-1))
        sizes.add_command(label="Normal size", accelerator="Ctrl+0", command=lambda: self.step_text_size(0))
        opt.add_cascade(label="Text size", menu=sizes)
        opt.add_separator()
        opt.add_command(label="Check for updates...", command=self.check_for_updates)
        self.auto_update_var = tk.BooleanVar(value=self.opts.check_updates)
        opt.add_checkbutton(label="Check for updates when the app starts", variable=self.auto_update_var,
                            command=self._auto_update_changed)
        opt.add_command(label="GitHub access token...", command=self._set_token)
        opt.add_separator()
        self.notify_var = tk.BooleanVar(value=self.opts.notify_done)
        opt.add_checkbutton(label="Notify me when a run finishes in the background", variable=self.notify_var,
                            command=self._notify_changed)
        opt.add_separator()
        opt.add_command(label="Edit fleet data...", command=self.stats_tab.edit_fleet)
        opt.add_command(label="Edit depot list (for unit reports)...", command=self.stats_tab.edit_depots)
        opt.add_command(label="Edit corridors (for capacity reports)...",
                        command=self.stats_tab.edit_groups)
        opt.add_command(label="Open settings folder", command=lambda: _open_path(
            os.path.dirname(Options.settings_path())))
        bar.add("Options", opt)
        self.saved_menu = tk.Menu(bar, tearoff=False, postcommand=self._fill_saved_menu)
        self._fill_saved_menu()
        bar.add("Save/Load", self.saved_menu)
        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label="User guide (README on GitHub)", accelerator="F1",
                              command=lambda: webbrowser.open(f"https://github.com/{updater.REPO}#readme"))
        help_menu.add_command(label="Keyboard shortcuts", command=lambda: messagebox.showinfo(
            "Keyboard shortcuts", "F5 or Ctrl+Enter\tRun the current tab\nCtrl+1 / 2 / 3 / 4\tCWN Tools / Stats Pack / "
            "Timetable Comparison / Live View\nF3 / Shift+F3\tLive View: next / previous difference\n"
            "Ctrl++ / Ctrl+- / Ctrl+0\tLarger / smaller / normal text\nAlt+O / Alt+S / Alt+H\tOptions / Save/Load / "
            "Help menu\nF1\t\tUser guide\n\nFiles can also be dragged onto any tab: each goes to the right box.", parent=self))
        help_menu.add_command(label="Third-party software and licences", command=self._licences)
        help_menu.add_command(label=f"About {APP_NAME}", command=self._about)
        bar.add("Help", help_menu)
        bar.pack(fill="x", before=self._head)

    def notify_done(self, title: str, message: str, ok: bool = True):
        """Flash the taskbar and show a corner notice when a run ends while the app is in the background."""
        if self.opts.notify_done:
            from rstools.notify import notify
            notify(self, title, message, ok)

    def _notify_changed(self):
        self.opts.notify_done = self.notify_var.get()
        self.save_app_settings()

    # ------------------------------------------------------------ saved comparisons
    def _tabs(self):
        return (self, self.stats_tab, self.tt_tab, self.live_tab)

    # Saved settings are stored as {key: {"tab": index, "name": name, "state": {...}}}. The key is
    # "<tab>:<name>", so each tab has its own names; entries saved by 3.2-3.6 (keyed by name alone) still load.
    def _saved(self, tab: int) -> list:
        """(key, name) of the settings saved for a tab, by name."""
        out = []
        for key, entry in self.opts.saved.items():
            if isinstance(entry, dict) and entry.get("tab", 0) == tab and isinstance(entry.get("state"), dict):
                out.append((key, entry.get("name") or key))
        return sorted(out, key=lambda kn: kn[1].casefold())

    def _fill_saved_menu(self):
        m = self.saved_menu
        m.delete(0, "end")
        idx = self.notebook.index("current")
        m.add_command(label=f"Save {TAB_NAMES[idx]} settings as...", command=self._save_settings_as)
        here = self._saved(idx)
        if here:
            m.add_separator()
            m.add_command(label=f"Load {TAB_NAMES[idx]} settings:", state="disabled")
            for key, name in here:
                m.add_command(label="    " + name, command=lambda k=key: self._load_saved(k, run=False))
        m.add_separator()
        for tab, tab_name in enumerate(TAB_NAMES):
            items = self._saved(tab)
            sub = tk.Menu(m, tearoff=False)
            for key, name in items:
                one = tk.Menu(sub, tearoff=False)
                one.add_command(label="Load", command=lambda k=key: self._load_saved(k, run=False))
                one.add_command(label="Load and run", command=lambda k=key: self._load_saved(k, run=True))
                one.add_command(label="Replace with the current settings",
                                command=lambda k=key: self._save_settings_as(replace=k))
                one.add_command(label="Rename...", command=lambda k=key: self._rename_saved(k))
                one.add_separator()
                one.add_command(label="Delete", command=lambda k=key: self._delete_saved(k))
                sub.add_cascade(label=name, menu=one)
            if not items:
                sub.add_command(label="(none saved yet)", state="disabled")
            m.add_cascade(label=f"{tab_name} ({len(items)})", menu=sub)
        theme.apply_menu(m, self.palette)

    def _ask_name(self, title: str, prompt: str, initial: str = "") -> str:
        name = simpledialog.askstring(title, prompt, initialvalue=initial, parent=self)
        return " ".join((name or "").split())[:60]

    def _save_settings_as(self, replace: str = ""):
        idx = self.notebook.index("current")
        tab = self._tabs()[idx]
        if replace:
            entry = self.opts.saved.get(replace) or {}
            idx, name = entry.get("tab", idx), entry.get("name") or replace
            tab = self._tabs()[idx]
            if not messagebox.askyesno(APP_TITLE, f"Replace '{name}' with the {TAB_NAMES[idx]} tab's current files "
                                                  "and options?", parent=self):
                return
            self.opts.saved.pop(replace, None)
        else:
            name = self._ask_name(f"Save {TAB_NAMES[idx]} settings", f"Name for these {TAB_NAMES[idx]} settings "
                                  "(the files and options are saved, so they can be loaded or run again in one click):")
            if not name:
                return
            clash = next((k for k, n in self._saved(idx) if n.casefold() == name.casefold()), None)
            if clash:
                if not messagebox.askyesno(APP_TITLE, f"Replace the saved {TAB_NAMES[idx]} settings '{name}'?",
                                           parent=self):
                    return
                self.opts.saved.pop(clash, None)
        self.opts.saved[f"{idx}:{name}"] = {"tab": idx, "name": name, "state": tab.get_state()}
        self.save_app_settings()

    def _rename_saved(self, key: str):
        entry = self.opts.saved.get(key)
        if not entry:
            return
        idx = entry.get("tab", 0)
        new = self._ask_name("Rename saved settings", "New name:", entry.get("name") or key)
        if not new or new == (entry.get("name") or key):
            return
        if any(n.casefold() == new.casefold() for k, n in self._saved(idx) if k != key):
            messagebox.showwarning(APP_TITLE, f"There are already {TAB_NAMES[idx]} settings called '{new}'.",
                                   parent=self)
            return
        self.opts.saved.pop(key)
        self.opts.saved[f"{idx}:{new}"] = dict(entry, name=new)
        self.save_app_settings()

    def _load_saved(self, key: str, run: bool):
        entry = self.opts.saved.get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("state"), dict):
            return
        idx, state, name = entry.get("tab", 0), entry["state"], entry.get("name") or key
        if not isinstance(idx, int) or not 0 <= idx < len(TAB_NAMES):
            return
        tab = self._tabs()[idx]
        if getattr(tab, "running", False):
            messagebox.showwarning(APP_TITLE, f"The {TAB_NAMES[idx]} tab is busy - wait for its run to finish.")
            return
        self.notebook.select(idx)
        try:
            tab.set_state(state)
        except Exception as exc:                     # a damaged entry must not break the app
            messagebox.showerror(APP_TITLE, f"The saved settings '{name}' could not be loaded ({exc}).")
            return
        missing = [p for p in tab.files_in_state(state) if not os.path.exists(p)]
        if missing:
            messagebox.showwarning(APP_TITLE, f"Some files of '{name}' are no longer there, so the settings were "
                                              "loaded but not run:\n\n" + "\n".join(missing[:8]))
            return
        if run:
            if idx == 0 and state.get("days") and state.get("mode") not in ("batch", "reorder"):
                self._run_when_days_known = True          # runs once the CWNs' days have been read
            else:
                self.after(300, tab.run)

    def _delete_saved(self, key: str):
        name = (self.opts.saved.get(key) or {}).get("name") or key
        if messagebox.askyesno(APP_TITLE, f"Delete the saved settings '{name}'? (The files are not touched.)",
                               parent=self):
            self.opts.saved.pop(key, None)
            self.save_app_settings()

    def _auto_update_changed(self):
        self.opts.check_updates = self.auto_update_var.get()
        self.save_app_settings()

    def _token(self) -> str:
        return updater.unprotect(self.opts.github_token)

    def _set_token(self):
        token = simpledialog.askstring(
            "GitHub access token",
            "Only needed while the GitHub repository is private.\n\nCreate a fine-grained token on GitHub "
            "(Settings > Developer settings > Personal access tokens) with read-only 'Contents' access to "
            f"{updater.REPO}, and paste it here. It is stored encrypted for your Windows login.\n\n"
            "Leave blank and press OK to remove a saved token.", show="*", parent=self)
        if token is None:
            return
        self.opts.github_token = updater.protect(token.strip())
        self.save_app_settings()

    def check_for_updates(self, release=None):
        UpdateDialog(self, __version__, self._token(), release)

    def _startup_update_check(self):
        if not self.opts.check_updates:
            return

        def work():
            try:
                rel = updater.latest_release(self._token())
            except Exception:
                return                              # offline / no access: stay quiet at start-up
            if updater.is_newer(rel.version, __version__):
                self.q.put(("update", rel))
        threading.Thread(target=work, daemon=True).start()

    def _about(self):
        messagebox.showinfo(f"About {APP_NAME}",
                            f"{APP_NAME} v{__version__}\n\nCWN Tools, Stats Pack, Timetable Comparison and Live View for GTR "
                            f"Train Planning.\n\nhttps://github.com/{updater.REPO}")

    def _licences(self):
        """The open-source software the app is built with, and its licences (shipped with the app)."""
        try:
            with open(os.path.join(ASSETS, "THIRD_PARTY_NOTICES.txt"), encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = "The licence notices could not be found. See the project page on GitHub."
        win = tk.Toplevel(self)
        win.title("Third-party software and licences")
        win.transient(self)
        box = tk.Text(win, wrap="word", width=100, height=34, relief="flat", padx=10, pady=8,
                      background=self.palette["field"], foreground=self.palette["fg"])
        sb = ttk.Scrollbar(win, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=sb.set)
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        ttk.Button(win, text="Close", command=win.destroy).grid(row=1, column=0, columnspan=2, pady=6)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        win.bind("<Escape>", lambda _e: win.destroy())

    def _follow_windows_theme(self):
        if self.opts.theme == "system" and theme.resolve("system") != self.palette["name"]:
            self.apply_theme("system")
        self._theme_id = self.after(5000, self._follow_windows_theme)

    def recent(self, kind: str) -> list:
        return [p for p in self.opts.recent.get(kind, []) if os.path.exists(p)]

    def add_recent(self, kind: str, *paths: str):
        lst = [p for p in self.opts.recent.get(kind, []) if p not in paths]
        self.opts.recent[kind] = ([os.path.normpath(p) for p in paths if p] + lst)[:8]

    def save_app_settings(self):
        self.opts.open_when_done = self.open_var.get()
        try:
            self.opts.last_tab = self.notebook.index("current")
        except tk.TclError:
            pass
        self.opts.save()

    def open_outputs(self, paths, force: bool = False):
        """'Open when finished' (or an Open button, with force): open the output, or its folder for many files."""
        if not (force or self.open_var.get()) or not paths:
            return
        for p in (paths if len(paths) <= 3 else [os.path.dirname(paths[0])]):
            _open_path(p)

    def file_box(self, master, var: tk.StringVar, kind: str) -> ttk.Combobox:
        """A file box that also lists the recently used files of this kind."""
        box = ttk.Combobox(master, textvariable=var)
        box.configure(postcommand=lambda: box.configure(values=self.recent(kind)))
        return box

    # ------------------------------------------------------------ window
    def _run_current_tab(self, _event=None):
        self._tabs()[self.notebook.index("current")].run()
        return "break"

    def set_busy(self, busy: bool):
        """Busy cursor while either tab is working."""
        busy = busy or self.running or self.stats_tab.running or self.tt_tab.running or self.live_tab.running
        try:
            self.configure(cursor="watch" if busy else "")
        except tk.TclError:
            pass

    def _on_close(self):
        if (self.running or self.stats_tab.running or self.tt_tab.running) and not messagebox.askyesno(
                APP_TITLE, "A run is still in progress and its output will not be saved.\n\nClose anyway?"):
            return
        try:
            self.save_app_settings()
        except Exception:
            pass
        self.after_cancel(self._poll_id)
        self.after_cancel(self._theme_id)
        self.stats_tab.stop()
        self.tt_tab.stop()
        self.live_tab.stop()
        self.destroy()

    def report_callback_exception(self, exc, val, tb):
        where = _write_error_log("".join(traceback.format_exception(exc, val, tb)))
        messagebox.showerror(APP_TITLE, f"Something went wrong: {val}"
                             + (f"\n\nDetails were saved to:\n{where}" if where else ""))

    def _set_icon(self):
        """The window / taskbar / Alt+Tab icon. The .ico (several sizes) is used on Windows; the PNGs are
        always set as well, so the logo still shows if the .ico cannot be loaded (never Tk's feather)."""
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ico = os.path.join(base, "packaging", "TrainPlanningTools.ico")
        try:
            self._icons = [tk.PhotoImage(file=os.path.join(ASSETS, n))
                           for n in ("logo.png", "logo_48.png", "logo_32.png", "logo_16.png")]
            self.iconphoto(True, *self._icons)
        except tk.TclError:
            pass
        if sys.platform.startswith("win") and os.path.exists(ico):
            try:
                self.iconbitmap(default=ico)
            except tk.TclError:
                pass

    def _show_logo(self):
        """The header logo, drawn at a size that suits the text size (never shrunk by dropping pixels)."""
        name = {"small": "logo_32.png", "xlarge": "logo.png"}.get(self.size_var.get(), "logo_48.png")
        if getattr(self, "compact", False) and name != "logo.png":
            name = "logo_32.png"                                  # a short screen: a smaller header
        try:
            self._logo = tk.PhotoImage(file=os.path.join(ASSETS, name))
            self._logo_label.configure(image=self._logo)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ UI
    def _build(self):
        head = self._head = ttk.Frame(self, padding=(12, 6, 12, 0))       # logo, name and version
        head.pack(fill="x")
        head.columnconfigure(2, weight=1)
        self._logo_label = ttk.Label(head)
        self._logo_label.grid(row=0, column=0, padx=(0, 8))
        self._show_logo()
        ttk.Label(head, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(head, text=f"v{__version__}", style="Small.TLabel").grid(row=0, column=2, sticky="sw",
                                                                           padx=(8, 0), pady=(0, 3))
        self.update_note = ttk.Label(head, text="", style="Link.TLabel", cursor="hand2")
        self.update_note.grid(row=0, column=3, sticky="e")
        self.update_note.bind("<Button-1>", lambda _e: self.check_for_updates(self._pending_release))
        self._pending_release = None
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        cwn_page, stats_page = ScrollPage(self.notebook), ScrollPage(self.notebook)
        outer = self.outer = cwn_page.body
        outer.configure(padding=(12, 8, 12, 10))
        self.notebook.add(cwn_page, text="  CWN Tools  ")
        from rstools.statspack.gui_tab import StatsPackTab
        self.stats_tab = StatsPackTab(stats_page.body, self)
        self.stats_tab.pack(fill="both", expand=True)
        self.stats_page = stats_page
        self.notebook.add(stats_page, text="  Stats Pack  ")
        from rstools.timetable.gui_tab import TimetableTab
        tt_page = self.tt_page = ScrollPage(self.notebook)
        self.tt_tab = TimetableTab(tt_page.body, self)
        self.tt_tab.pack(fill="both", expand=True)
        self.notebook.add(tt_page, text="  Timetable Comparison  ")
        from rstools.live.gui_tab import LiveTab
        live_page = self.live_page = ScrollPage(self.notebook)
        self.live_tab = LiveTab(live_page.body, self)
        self.live_tab.pack(fill="both", expand=True)
        self.notebook.add(live_page, text="  Live View  ")
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(outer, text="Carriage Working Notice Comparison", style="Head.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.intro = theme.tip(ttk.Label(outer, text="", style="Small.TLabel"))
        self.intro.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        left = ttk.Frame(outer)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(outer)
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # --- mode
        mf = ttk.LabelFrame(left, text="1. What to do", padding=8)
        mf.grid(row=0, column=0, sticky="ew")
        self.mode = tk.StringVar(value="compare")
        ttk.Radiobutton(mf, text="Compare two CWNs", variable=self.mode, value="compare",
                        command=self._mode_changed).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(mf, text="Add a new round to an earlier comparison CWN",
                        variable=self.mode, value="cumulative",
                        command=self._mode_changed).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(mf, text="Compare two folders of CWNs (batch)", variable=self.mode, value="batch",
                        command=self._mode_changed).grid(row=2, column=0, sticky="w")
        ttk.Separator(mf).grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Radiobutton(mf, text="Put each train's day variants in order (one CWN)", variable=self.mode,
                        value="reorder", command=self._mode_changed).grid(row=4, column=0, sticky="w")
        ttk.Radiobutton(mf, text="Station Working Book (TRACS-RS layout, from an Attune XML)", variable=self.mode,
                        value="station", command=self._mode_changed).grid(row=5, column=0, sticky="w")

        # --- files
        ff = ttk.LabelFrame(left, text="2. Files", padding=8)
        ff.grid(row=1, column=0, sticky="ew", pady=8)
        ff.columnconfigure(1, weight=1)
        self.orig_lbl = ttk.Label(ff, text="Original CWN:")
        self.orig_lbl.grid(row=0, column=0, sticky="w")
        self.orig = tk.StringVar()
        self.orig_entry = self.file_box(ff, self.orig, "cwn")
        self.orig_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(ff, text="Browse...", command=lambda: self._browse(self.orig, True)).grid(row=0, column=2)
        self.upd_lbl = ttk.Label(ff, text="Updated CWN:")
        self.upd_lbl.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.upd = tk.StringVar()
        self.upd_entry = self.file_box(ff, self.upd, "cwn")
        self.upd_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        self.upd_browse = ttk.Button(ff, text="Browse...", command=lambda: self._browse(self.upd, False))
        self.upd_browse.grid(row=1, column=2, pady=(6, 0))
        self.swap_btn = ttk.Button(ff, text="Swap original / updated", command=self._swap)
        self.swap_btn.grid(row=2, column=1, sticky="w", padx=4, pady=(6, 0))
        self.dnd_hint = theme.tip(ttk.Label(ff, text="", style="Small.TLabel", wraplength=430, justify="left"))
        self.dnd_hint.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.prev_info = ttk.Label(ff, text="", style="Small.TLabel", wraplength=430, justify="left")
        self.prev_info.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # --- output
        of = ttk.LabelFrame(left, text="3. Output", padding=8)
        of.grid(row=2, column=0, sticky="ew")
        of.columnconfigure(1, weight=1)
        self.out_type = tk.StringVar(value="full")
        type_lbl = ttk.Label(of, text="Output type:")
        type_lbl.grid(row=0, column=0, sticky="nw")
        tf = ttk.Frame(of)
        tf.grid(row=0, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(tf, text="Full CWN with changes highlighted",
                        variable=self.out_type, value="full").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(tf, text="ACWN (amended trains only)",
                        variable=self.out_type, value="acwn").grid(row=1, column=0, sticky="w")

        self.colour_lbl = ttk.Label(of, text="Highlight colour:")
        self.colour_lbl.grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 6))
        self.colour = ColourPicker(of, self.opts.colour)
        self.colour.grid(row=1, column=1, sticky="w", pady=(6, 0))

        self.tabs_var = tk.BooleanVar(value=True)
        tabs_cb = ttk.Checkbutton(of, text="Highlight tabs that contain changes", variable=self.tabs_var)
        tabs_cb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.report_var = tk.BooleanVar(value=True)
        rep = ttk.Frame(of)
        rep.grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(rep, text="Create change report as", variable=self.report_var).grid(row=0, column=0)
        self.report_fmt = ttk.Combobox(rep, values=list(REPORT_FORMATS.values()), state="readonly", width=8)
        self.report_fmt.grid(row=0, column=1, padx=(4, 0))
        self.report_fmt.set(REPORT_FORMATS["xlsx"])
        self.links_var = tk.BooleanVar(value=False)
        links_cb = ttk.Checkbutton(of, text="Keep links between tabs (makes the CWN much slower to open)",
                                   variable=self.links_var)
        links_cb.grid(row=4, column=0, columnspan=3, sticky="w")
        Tooltip(links_cb, "CWNs contain tens of thousands of clickable headcode links between tabs. "
                           "Excel opens the output far faster without them; the text is kept.")

        ttk.Label(of, text="Save to folder:").grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.out_dir = tk.StringVar()
        ttk.Entry(of, textvariable=self.out_dir).grid(row=5, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Button(of, text="Browse...", command=self._browse_dir).grid(row=5, column=2, pady=(6, 0))
        ttk.Label(of, text="Output name:").grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.out_name = tk.StringVar()
        ttk.Entry(of, textvariable=self.out_name).grid(row=6, column=1, sticky="ew", padx=4, pady=(6, 0))
        self.name_hint = ttk.Label(of, text="", style="Small.TLabel", wraplength=440, justify="left")
        self.name_hint.grid(row=7, column=0, columnspan=3, sticky="w")
        dayf = ttk.Frame(of)
        dayf.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(dayf, text="Days to check:").grid(row=0, column=0, padx=(0, 6))
        self.day_vars = [tk.BooleanVar(value=True) for _d in DAY_LABELS]
        self.day_cbs = []
        for i, lab in enumerate(DAY_LABELS):
            cb = ttk.Checkbutton(dayf, text=lab, variable=self.day_vars[i], state="disabled")
            cb.grid(row=0, column=i + 1, padx=(0, 4))
            self.day_cbs.append(cb)
        self.all_days_btn = ttk.Button(dayf, text="All", width=5, state="disabled", command=self._all_days)
        self.all_days_btn.grid(row=0, column=len(DAY_LABELS) + 1, padx=(4, 0))
        self.day_note = ttk.Label(of, text="", style="Small.TLabel", wraplength=440, justify="left")
        self.day_note.grid(row=9, column=0, columnspan=3, sticky="w")
        # reorder mode: how the variants of each train are ordered (shown instead of the comparison options)
        self.order_frame = orf = ttk.Frame(of)
        orf.grid(row=0, column=0, rowspan=5, columnspan=3, sticky="nw")
        ttk.Label(orf, text="Order of each train's day variants:").grid(row=0, column=0, sticky="w")
        self.variant_order = tk.StringVar(value="day")
        ttk.Radiobutton(orf, text="By day - MO first, then TO, WO, ThO, FO (then SO, SuO)",
                        variable=self.variant_order, value="day").grid(row=1, column=0, sticky="w", padx=(12, 0))
        ttk.Radiobutton(orf, text="By departure time - earliest first, then by day",
                        variable=self.variant_order, value="time").grid(row=2, column=0, sticky="w", padx=(12, 0))
        ttk.Label(orf, text="Only the variants of the same train change places, within the rows they already "
                            "use. Nothing is changed or removed, and the original file is not touched.",
                  style="Small.TLabel", wraplength=440, justify="left").grid(row=3, column=0, sticky="w",
                                                                              pady=(4, 0))
        self.order_frame.grid_remove()
        self.variant_order.trace_add("write", lambda *_a: self._update_name_hint())
        self._build_station_book(of)
        self._compare_only = [type_lbl, tf, self.colour_lbl, self.colour, tabs_cb, rep, links_cb, dayf,
                              self.day_note]
        self.cwn_days: Dict[str, tuple] = {}            # path -> (mtime, days, assumed)
        self._pending_days = None                        # days to tick once known (a saved comparison)
        self._run_when_days_known = False
        self._last_mode = "compare"
        self.available_days: set = set()
        self._days_token = 0
        self._days_after = None
        self.orig.trace_add("write", lambda *_a: self._read_book_xml())
        for var in (self.orig, self.upd):
            var.trace_add("write", lambda *_a: self._update_name_hint())
            var.trace_add("write", lambda *_a: self._schedule_days())
            var.trace_add("write", lambda *_a: self._show_pairs())
        self._update_name_hint()
        self._schedule_days()

        # --- categories
        cf = self.cats_frame = ttk.LabelFrame(right, text="4. Changes to include", padding=8)
        cf.grid(row=0, column=0, sticky="nsew")
        heads = [("Change type", "Hover over a change type for what it covers."),
                 ("Show in\nCWN", "Highlight this type of change in the output CWN. For cancelled trains: "
                                  "re-insert them struck through; untick to remove them entirely."),
                 ("Show previous\nvalue / note", "Show the old value struck through above the new one, and add "
                                                 "notes (e.g. what a train used to form). Untick for highlight only."),
                 ("Include in\nreport", "Untick to leave this type of change out of the change report.")]
        for i, (h, help_text) in enumerate(heads):
            lab = ttk.Label(cf, text=h, font="AppBold", justify="center")
            lab.grid(row=0, column=i, padx=4, sticky="w" if i == 0 else "")
            Tooltip(lab, help_text)
        self.cat_vars = {}
        for r, (key, label, has_old, desc) in enumerate(CATEGORIES, start=1):
            lab = ttk.Label(cf, text=label)
            lab.grid(row=r, column=0, sticky="w", padx=4, pady=1)
            Tooltip(lab, desc)
            vs = {}
            for ci, what in enumerate(("cwn", "show_old", "report"), start=1):
                v = tk.BooleanVar(value=True)
                cb = ttk.Checkbutton(cf, variable=v)
                cb.grid(row=r, column=ci)
                if what == "show_old" and not has_old:
                    cb.state(["disabled"])
                    v.set(False)
                vs[what] = v
            self.cat_vars[key] = vs
        ttk.Label(cf, text="Hover over a heading or change type for details.", style="Small.TLabel").grid(
            row=len(CATEGORIES) + 1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.loose_var = tk.BooleanVar(value=True)
        loose = ttk.Checkbutton(cf, text="Ignore differences only in spacing or punctuation",
                                variable=self.loose_var)
        loose.grid(row=len(CATEGORIES) + 2, column=0, columnspan=4, sticky="w", pady=(4, 0))
        Tooltip(loose, "Destinations, routing and notes that differ only in spaces or punctuation "
                        "(e.g. '(via  Redhill.)' and '(via Redhill)') are not reported. Capital letters "
                        "are always ignored; times, platforms, headcodes and units are always compared "
                        "exactly.")
        bf = ttk.Frame(cf)
        bf.grid(row=len(CATEGORIES) + 3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(bf, text="Reset to defaults", command=self._reset_cats).grid(row=0, column=0)
        ttk.Button(bf, text="Highlight only (no old values)", command=self._highlight_only).grid(
            row=0, column=1, padx=6)

        # --- run + log
        rf = self.run_frame = ttk.LabelFrame(right, text="5. Run", padding=8)
        rf.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(2, weight=1, minsize=90)        # the log stays visible at the smallest size
        top = ttk.Frame(rf)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.run_btn = ttk.Button(top, text="Run comparison", style="Run.TButton", command=self._run)
        self.run_btn.grid(row=0, column=0)
        self.prog = ttk.Progressbar(top, mode="determinate", maximum=1.0)
        self.prog.grid(row=0, column=1, sticky="ew", padx=8)
        self.status = ttk.Label(rf, text="Ready - press F5 or Ctrl+Enter to run", style="Small.TLabel")
        self.status.grid(row=1, column=0, sticky="w", pady=(4, 2))
        logf = ttk.Frame(rf)
        logf.grid(row=2, column=0, sticky="nsew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.log = tk.Text(logf, height=8, wrap="word", font="TkFixedFont", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        ob = ttk.Frame(rf)
        ob.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.open_cwn = ttk.Button(ob, text="Open output CWN", state="disabled",
                                   command=lambda: _open_path(self.result["cwn"]))
        self.open_cwn.grid(row=0, column=0)
        self.open_rep = ttk.Button(ob, text="Open report", state="disabled",
                                   command=lambda: _open_path(self.result["report"]))
        self.open_rep.grid(row=0, column=1, padx=6)
        self.open_dir = ttk.Button(ob, text="Open folder", state="disabled",
                                   command=lambda: _open_path(os.path.dirname(self.result["cwn"])))
        self.open_dir.grid(row=0, column=2)
        ttk.Checkbutton(ob, text="Open when finished", variable=self.open_var).grid(row=0, column=3, padx=(12, 0))

    # ------------------------------------------------------------ helpers
    def _load_into_widgets(self):
        o = self.opts
        self.mode.set(o.mode if o.mode in ("compare", "cumulative", "batch", "reorder", "station") else "compare")
        for k, var in self.book_vars.items():
            var.set(getattr(o, f"book_{k}", "") or "")
        for dt, v in self.book_day_vars.items():
            v.set(dt in (o.book_days or []))
        self.variant_order.set(o.variant_order if o.variant_order in ("day", "time") else "day")
        self.out_type.set(o.output_type)
        self.colour.set(o.colour)
        self.tabs_var.set(o.highlight_tabs)
        self.report_var.set(o.make_report)
        self.links_var.set(o.keep_links)
        self.report_fmt.set(REPORT_FORMATS.get(o.report_format, REPORT_FORMATS["xlsx"]))
        self.loose_var.set(o.ignore_spacing)
        self.out_dir.set(o.output_dir)
        for k, vs in self.cat_vars.items():
            for what, v in vs.items():
                if what != "show_old" or HAS_OLD[k]:
                    v.set(o.cat(k, what))
        self._mode_changed()

    def _collect(self) -> Options:
        o = Options()
        o.mode = self.mode.get()
        o.variant_order = self.variant_order.get()
        o.original = self.orig.get().strip().strip('"')
        o.updated = self.upd.get().strip().strip('"')
        o.output_type = self.out_type.get()
        o.colour = self.colour.value
        o.highlight_tabs = self.tabs_var.get()
        o.make_report = self.report_var.get()
        o.keep_links = self.links_var.get()
        o.report_format = next(k for k, v in REPORT_FORMATS.items() if v == self.report_fmt.get())
        o.ignore_spacing = self.loose_var.get()
        o.output_dir = self.out_dir.get().strip().strip('"')
        o.output_name = self.out_name.get().strip()
        o.days = self.chosen_days()
        o.categories = {k: {w: bool(v.get()) for w, v in vs.items()} for k, vs in self.cat_vars.items()}
        for k in APP_WIDE:                                      # app-wide settings carried over
            setattr(o, k, getattr(self.opts, k))
        for k, var in self.book_vars.items():
            setattr(o, f"book_{k}", var.get().strip())
        o.book_days = [dt for dt, v in self.book_day_vars.items() if v.get()]
        o.open_when_done = self.open_var.get()
        return o

    def _build_station_book(self, of):
        """Station Working Book options (shown instead of the comparison options)."""
        sb = self.book_frame = ttk.Frame(of)
        sb.grid(row=0, column=0, rowspan=5, columnspan=3, sticky="new")
        sb.columnconfigure(1, weight=1)
        self.book_vars = {k: tk.StringVar() for k in ("station", "platforms", "list", "operator", "timetable",
                                                      "services", "label")}
        rows = (("station", "Station:"), ("platforms", "Platforms (optional):"), ("list", "Several stations:"),
                ("operator", "Operator:"), ("timetable", "Timetable:"), ("services", "Services:"),
                ("label", "Sheet name:"))
        for r, (key, text) in enumerate(rows):
            ttk.Label(sb, text=text).grid(row=r, column=0, sticky="w", pady=1)
            if key == "station":
                self.book_station_box = w = ttk.Combobox(sb, textvariable=self.book_vars[key])
                w.bind("<KeyRelease>", self._filter_book_stations)
                ttk.Button(sb, text="Add to list", command=self._add_book_station).grid(row=r, column=2,
                                                                                        padx=(4, 0), pady=1)
            else:
                w = ttk.Entry(sb, textvariable=self.book_vars[key])
                if key == "list":
                    ttk.Button(sb, text="Clear", command=lambda: self.book_vars["list"].set("")).grid(
                        row=r, column=2, sticky="ew", padx=(4, 0), pady=1)
            w.grid(row=r, column=1, sticky="ew", padx=(4, 0), pady=1)
        df = ttk.Frame(sb)
        df.grid(row=len(rows), column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(df, text="Sheets:").grid(row=0, column=0, padx=(0, 6))
        self.book_day_vars = {}
        for i, dt in enumerate(("SX", "SO", "Su")):
            v = self.book_day_vars[dt] = tk.BooleanVar(value=True)
            ttk.Checkbutton(df, text=dt, variable=v).grid(row=0, column=i + 1, padx=(0, 8))
        self.book_note = ttk.Label(sb, text="", style="Small.TLabel", wraplength=440, justify="left")
        self.book_note.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._book_stations: list = []
        self._book_token = 0
        for v in self.book_vars.values():
            v.trace_add("write", lambda *_a: self._update_name_hint())
        sb.grid_remove()

    def _add_book_station(self):
        """Add the chosen station (and any platforms) to the list of books to make in one run."""
        station = self.book_vars["station"].get().strip()
        if not station:
            return
        plats = self.book_vars["platforms"].get().strip()
        entry = station + (f" [{plats}]" if plats else "")
        current = [e.strip() for e in self.book_vars["list"].get().split(";") if e.strip()]
        if entry not in current:
            current.append(entry)
        self.book_vars["list"].set("; ".join(current))
        self.book_vars["station"].set("")
        self.book_vars["platforms"].set("")

    def _filter_book_stations(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        typed = self.book_station_box.get().strip().casefold()
        self.book_station_box.configure(values=[s for s in self._book_stations if typed in s.casefold()]
                                        if typed else self._book_stations)

    def _read_book_xml(self):
        """List the XML's stations (and its timetable name) in the background, for the station box."""
        path = self.orig.get().strip().strip('"')
        self._book_token += 1
        token = self._book_token
        if self.mode.get() != "station" or not path.lower().endswith(".xml") or not os.path.isfile(path):
            return
        self.book_note.configure(text="Reading the XML...")

        def work():
            try:
                from rstools.stationbook import read_plan, timetable_name
                from rstools.statspack.seats import network_stations
                from rstools.statspack.engine import cached
                from rstools.statspack.attune import parse_attune_xml
                plan = read_plan(path)
                stations = network_stations(cached(parse_attune_xml, path))
                days = sorted(plan.diagram_days)
                self.q.put(("bookxml", token, stations, timetable_name(plan), days, ""))
            except Exception as exc:
                self.q.put(("bookxml", token, [], "", [], str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _book_xml_read(self, token, stations, timetable, days, error):
        if token != self._book_token:
            return
        if error:
            self.book_note.configure(text=f"The XML could not be read: {error}")
            return
        self._book_stations = stations
        self.book_station_box.configure(values=stations)
        if timetable and not self.book_vars["timetable"].get().strip():
            self.book_vars["timetable"].set(timetable)
        from rstools.stationbook import DAY_NAMES
        missing = [DAY_NAMES[d] for d in range(7) if d not in days]
        self.book_note.configure(text=f"{len(stations)} stations in the XML. " + (
            "It has unit diagrams for every day." if not missing else
            "It has no unit diagrams for " + ", ".join(missing) + ", so stock and inward workings will be "
            "missing on those days - export the XML with every day's unit diagrams."))

    def _update_name_hint(self):
        if self.mode.get() == "station":
            v = {k: x.get().strip() for k, x in self.book_vars.items()}
            if ";" in v["list"] or (v["list"] and v["station"]):
                self.name_hint.configure(text="Several stations: one book each, named after its station (the name "
                                              "and sheet name boxes are not used). Leave the folder blank to save "
                                              "next to the XML.")
                return
            name = (f"{v['operator'] + ' ' if v['operator'] else ''}{v['timetable'] + ' ' if v['timetable'] else ''}"
                    f"Station Working Book - {v['station'] or v['list'] or 'station'}")
            self.name_hint.configure(text=f"Leave the name blank for '{name}'. Leave the folder blank to save next "
                                          "to the XML.")
            return
        if self.mode.get() == "reorder":
            p = self.orig.get().strip().strip('"')
            stem = os.path.splitext(os.path.basename(p))[0] if p else "CWN name"
            what = "variants by time" if self.variant_order.get() == "time" else "variants in day order"
            self.name_hint.configure(text=f"Leave the name blank for '{stem} ({what})'. Leave the folder blank "
                                          "to save next to the CWN.")
            return
        if self.mode.get() == "batch":
            self.name_hint.configure(text="Each pair's output is named after its two CWNs (the name box is not "
                                          "used). Leave the folder blank to save each next to its updated CWN.")
            return
        name = default_name(self.orig.get().strip().strip('"'), self.upd.get().strip().strip('"'))
        self.name_hint.configure(text=f"Leave the name blank for '{name}'. Leave the folder blank to save "
                                      "next to the updated CWN.")

    def _reset_cats(self):
        d = default_categories()
        for k, vs in self.cat_vars.items():
            for w, v in vs.items():
                v.set(d[k][w])

    def _highlight_only(self):
        for vs in self.cat_vars.values():
            vs["show_old"].set(False)

    def _mode_changed(self):
        mode = self.mode.get()
        batch = mode == "batch"
        if (mode != self._last_mode) and (batch or self._last_mode == "batch"):
            self.orig.set("")                       # files and folders do not mix
            self.upd.set("")
        self._last_mode = mode
        station = mode == "station"
        reorder = mode == "reorder"
        single = reorder or station                  # one input file, no comparison options
        self.orig_lbl.configure(text="Earlier comparison CWN:" if mode == "cumulative" else
                                "Original CWN folder:" if batch else "CWN:" if reorder else
                                "Attune XML:" if station else "Original CWN:")
        for w in (self.upd_lbl, self.upd_entry, self.upd_browse):
            (w.grid_remove if single else w.grid)()
        for w in self._compare_only:
            (w.grid_remove if single else w.grid)()
        (self.order_frame.grid if reorder else self.order_frame.grid_remove)()
        (self.book_frame.grid if station else self.book_frame.grid_remove)()
        (self.cats_frame.grid_remove if single else self.cats_frame.grid)()
        self.run_btn.configure(text="Put variants in order" if reorder else "Make station working book" if station
                               else "Run comparison")
        self.open_cwn.configure(text="Open tidied CWN" if reorder else "Open station working book" if station
                                else "Open output CWN")
        (self.open_rep.grid_remove if single else self.open_rep.grid)()
        self.run_frame.configure(text="4. Run" if single else "5. Run")
        self.intro.configure(text="Saves a tidier copy of one multi-day CWN, with each train's day variants listed "
                                  "in order. Nothing in the CWN is changed or removed." if reorder else
                             "Makes a Station Working Book in the TRACS-RS layout from an Attune XML: every train "
                             "leaving the station, with its inward working, stock, platform and calling points."
                             if station else
                             "Compares trains (not Excel rows) between an original and an updated CWN, and produces "
                             "a highlighted CWN plus a change report.")
        if station:
            self._read_book_xml()
        self._show_dnd_hint()
        self.upd_lbl.configure(text="Updated CWN folder:" if batch else "Updated CWN:")
        self.colour_lbl.configure(text="Colour for new amendments:" if mode == "cumulative" else "Highlight colour:")
        if mode == "cumulative":
            self.swap_btn.grid_remove()
            self._read_prev_info()
        elif single:
            self.swap_btn.grid_remove()
            self.prev_info.configure(text="")
        else:
            self.swap_btn.grid()
            self.prev_info.configure(text="")
        if batch:
            self._show_pairs()
        self._update_name_hint()
        self._schedule_days()

    # ------------------------------------------------------- drag & drop
    def _show_dnd_hint(self):
        if not getattr(self, "_dnd_on", False):
            return
        self.dnd_hint.configure(text="Tip: drag and drop the Attune XML onto the box above, or anywhere on this tab."
                                if self.mode.get() == "station" else
                                "Tip: drag and drop the CWN onto the box above, or anywhere on this tab."
                                if self.mode.get() == "reorder" else
                                "Tip: drag and drop two CWNs (or two folders of CWNs) onto the boxes above, "
                                "or anywhere on this tab.")

    def _load_dnd(self) -> str:
        """Load tkdnd (no admin rights needed); '' if drag and drop is unavailable."""
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES
            TkinterDnD._require(self)
            return DND_FILES
        except Exception:   # drag and drop unavailable - the Browse buttons still work
            return ""

    def _enable_drag_and_drop(self, outer):
        """Drop CWN files onto a file box, or anywhere on the CWN Tools tab."""
        if not self._dnd:
            return

        def register(widget, target=None):
            if isinstance(widget, tk.Text):
                return
            try:
                widget.drop_target_register(self._dnd)
                widget.dnd_bind("<<Drop>>", lambda e, t=target: self._on_drop(e, t))
            except (tk.TclError, AttributeError):
                return
            for child in widget.winfo_children():
                if child not in (self.orig_entry, self.upd_entry):
                    register(child)
        register(outer)
        register(self.orig_entry, self.orig)
        register(self.upd_entry, self.upd)
        self._dnd_on = True
        self._show_dnd_hint()
        self.stats_tab.enable_drag_and_drop(self._dnd)
        self.tt_tab.enable_drag_and_drop(self._dnd)
        self.live_tab.enable_drag_and_drop(self._dnd)

    def _on_drop(self, event, target):
        paths = [os.path.normpath(p) for p in self.tk.splitlist(event.data)]
        folders = [p for p in paths if os.path.isdir(p)]
        if folders:                                   # folders: compare two folders of CWNs
            self.mode.set("batch")
            self._mode_changed()
            if target is not None and len(folders) == 1:
                target.set(folders[0])
            elif len(folders) >= 2:
                self.orig.set(folders[0])
                self.upd.set(folders[1])
            else:
                (self.upd if self.orig.get().strip() else self.orig).set(folders[0])
            return event.action
        xmls = [p for p in paths if os.path.isfile(p) and p.lower().endswith(".xml")]
        if xmls:                                      # an Attune XML: the station working book
            if self.mode.get() != "station":
                self.mode.set("station")
                self._mode_changed()
            self.orig.set(xmls[0])
            return event.action
        files = [p for p in paths if os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED_EXT]
        if files and self.mode.get() == "station":
            self.mode.set("compare")
            self._mode_changed()
        if files and self.mode.get() == "batch":
            self.mode.set("compare")
            self._mode_changed()
        if not files:
            messagebox.showwarning(APP_TITLE, "Please drop Excel CWN files (.xlsx, .xlsm, .xls, .xlsb).")
            return event.action
        if self.mode.get() == "reorder":
            self.orig.set(files[0])
        elif target is not None and len(files) == 1:
            target.set(files[0])
        elif len(files) >= 2:
            first, second = self._order_dropped(files[:2])
            self.orig.set(first)
            self.upd.set(second)
        elif not self.orig.get().strip():
            self.orig.set(files[0])
        else:
            self.upd.set(files[0])
        if self.mode.get() == "cumulative":
            self._read_prev_info()
        return event.action

    def _order_dropped(self, files):
        """Two files dropped together: the previous comparison (cumulative mode) or the
        older file (compare mode) becomes the first file."""
        if self.mode.get() == "cumulative":
            gen = [f for f in files if is_comparison_output(f)]
            if len(gen) == 1:
                return gen[0], next(f for f in files if f != gen[0])
        return tuple(sorted(files, key=os.path.getmtime))

    def _browse(self, var, first):
        init = os.path.dirname(var.get()) if var.get() else (os.path.dirname(self.opts.updated) or None)
        if self.mode.get() == "batch":
            p = filedialog.askdirectory(title="Choose the folder of original CWNs" if first else
                                        "Choose the folder of updated CWNs", initialdir=var.get() or init)
            if p:
                var.set(os.path.normpath(p))
            return
        if self.mode.get() == "station":
            p = filedialog.askopenfilename(title="Choose the Attune XML", initialdir=init,
                                           filetypes=[("Attune diagram XML", "*.xml"), ("All files", "*.*")])
            if p:
                var.set(os.path.normpath(p))
            return
        title = ("Choose an earlier comparison CWN made by this app" if first and self.mode.get() == "cumulative"
                 else "Choose the multi-day CWN" if self.mode.get() == "reorder"
                 else "Choose the original CWN" if first else "Choose the updated CWN")
        p = filedialog.askopenfilename(title=title, filetypes=FILE_TYPES, initialdir=init)
        if p:
            var.set(os.path.normpath(p))
            if first and self.mode.get() == "cumulative":
                self._read_prev_info()

    def _browse_dir(self):
        p = filedialog.askdirectory(title="Choose output folder")
        if p:
            self.out_dir.set(os.path.normpath(p))

    def _swap(self):
        a, b = self.orig.get(), self.upd.get()
        self.orig.set(b)
        self.upd.set(a)

    def run(self):
        """Run the CWN Tools tab (the same call as the other tabs' run)."""
        self._run()

    # ------------------------------------------------------------ day variants in order (one CWN)
    def _start(self):
        """Common start of a run: buttons, log and progress reset."""
        self.running = True
        self.result = None
        for b in (self.open_cwn, self.open_rep, self.open_dir):
            b.state(["disabled"])
        self.run_btn.state(["disabled"])
        self.set_busy(True)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.prog["value"] = 0

    def _run_station_book(self, o: Options):
        if not o.original.lower().endswith(".xml") or not os.path.isfile(o.original):
            messagebox.showwarning(APP_TITLE, "Please choose the Attune XML (.xml).")
            return
        from rstools.stationbook import parse_station_list
        entries = parse_station_list(o.book_list)
        if o.book_station and (o.book_station, o.book_platforms) not in entries and entries:
            entries.append((o.book_station, o.book_platforms))      # chosen but not yet added to the list
        if not entries and not o.book_station:
            messagebox.showwarning(APP_TITLE, "Please choose the station (or add several to the list).")
            return
        if not o.book_days:
            messagebox.showwarning(APP_TITLE, "Tick at least one sheet (SX, SO or Su).")
            return
        if o.output_dir and not os.path.isdir(o.output_dir):
            messagebox.showwarning(APP_TITLE, f"Output folder does not exist:\n{o.output_dir}")
            return
        saved = dataclasses.replace(o, output_name="", days=[])
        saved.save()
        self.opts = saved
        self._start()
        self.status.configure(text="Making the station working book...")
        self.prog.configure(mode="indeterminate")
        self.prog.start(15)

        def work():
            from rstools.stationbook import StationBookError, make_book, make_books
            try:
                if len(entries) > 1:
                    results = make_books(o.original, entries, o.output_dir, o.book_operator, o.book_timetable,
                                         o.book_services, o.book_days, log=lambda m: self.q.put(("log", m)))
                    self.q.put(("books_done", results))
                    return
                if entries:
                    o.book_station, o.book_platforms = entries[0]
                path, warnings, summary = make_book(
                    o.original, o.book_station, o.output_dir, o.output_name, o.book_operator, o.book_timetable,
                    o.book_services, o.book_label, o.book_platforms, o.book_days,
                    log=lambda m: self.q.put(("log", m)))
                self.q.put(("book_done", path, warnings, summary))
            except StationBookError as exc:
                self.q.put(("error", str(exc)))
            except Exception as exc:
                where = _write_error_log(traceback.format_exc())
                self.q.put(("error", f"Unexpected error: {exc}"
                                     + (f"\n\nDetails were saved to:\n{where}" if where else "")))
        threading.Thread(target=work, daemon=True).start()

    def _run_reorder(self, o: Options):
        if not o.original:
            messagebox.showwarning(APP_TITLE, "Please choose the CWN first.")
            return
        if not os.path.isfile(o.original):
            messagebox.showwarning(APP_TITLE, f"File not found:\n{o.original}")
            return
        if o.output_dir and not os.path.isdir(o.output_dir):
            messagebox.showwarning(APP_TITLE, f"Output folder does not exist:\n{o.output_dir}")
            return
        self.add_recent("cwn", o.original)
        saved = dataclasses.replace(o, output_name="", days=[])
        saved.save()
        self.opts = saved
        self._start()
        self.status.configure(text="Putting day variants in order...")
        self.prog.configure(mode="indeterminate")
        self.prog.start(15)

        def work():
            from .reorder import ReorderError, reorder_cwn
            try:
                res = reorder_cwn(o.original, o.output_dir, o.output_name, o.variant_order == "time",
                                  log=lambda m: self.q.put(("log", m)))
                self.q.put(("reorder_done", res))
            except (ReorderError, LoadError) as exc:
                self.q.put(("error", str(exc)))
            except Exception as exc:
                where = _write_error_log(traceback.format_exc())
                self.q.put(("error", f"Unexpected error: {exc}"
                                     + (f"\n\nDetails were saved to:\n{where}" if where else "")))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ batch (two folders)
    def _show_pairs(self):
        if self.mode.get() != "batch":
            return
        a, b = self.orig.get().strip().strip('"'), self.upd.get().strip().strip('"')
        if not (os.path.isdir(a) and os.path.isdir(b)):
            self.prev_info.configure(text="Choose the two folders. Each updated CWN is paired with the original "
                                          "of the same (or most similar) name.")
            return
        from .batch import pair_files
        pairs, left, right = pair_files(a, b)
        text = f"{len(pairs)} pair(s) found"
        if pairs:
            text += ": " + "; ".join(f"{os.path.basename(o)} > {os.path.basename(u)}" for o, u in pairs[:4])
            text += " ..." if len(pairs) > 4 else ""
        if left or right:
            text += f". Not paired: {len(left)} original(s), {len(right)} updated."
        self.prev_info.configure(text=text)

    def _run_batch(self, o: Options):
        from .batch import pair_files, workers_for
        if not (os.path.isdir(o.original) and os.path.isdir(o.updated)):
            messagebox.showwarning(APP_TITLE, "Please choose the folder of original CWNs and the folder of "
                                              "updated CWNs.")
            return
        if os.path.normcase(os.path.abspath(o.original)) == os.path.normcase(os.path.abspath(o.updated)):
            messagebox.showwarning(APP_TITLE, "The two folders are the same folder.")
            return
        if o.output_dir and not os.path.isdir(o.output_dir):
            messagebox.showwarning(APP_TITLE, f"Output folder does not exist:\n{o.output_dir}")
            return
        pairs, left, right = pair_files(o.original, o.updated)
        if not pairs:
            messagebox.showwarning(APP_TITLE, "No CWNs could be paired between the two folders. Pairs need the "
                                              "same or a very similar file name.")
            return
        lines = [f"{os.path.basename(a)}  >  {os.path.basename(b)}" for a, b in pairs[:20]]
        more = f"\n... and {len(pairs) - 20} more" if len(pairs) > 20 else ""
        skipped = (f"\n\nNot paired (left out): {', '.join(os.path.basename(x) for x in (left + right)[:8])}"
                   + (" ..." if len(left) + len(right) > 8 else "")) if left or right else ""
        if not messagebox.askyesno(APP_TITLE, f"Compare these {len(pairs)} pair(s)?\n\n" + "\n".join(lines) + more
                                   + skipped + f"\n\n{workers_for(pairs)} will be compared at a time.", parent=self):
            return
        saved = dataclasses.replace(o, output_name="", days=[])
        saved.save()
        self.opts = saved
        self.running = True
        self.result = None
        for b in (self.open_cwn, self.open_rep, self.open_dir):
            b.state(["disabled"])
        self.run_btn.state(["disabled"])
        self.set_busy(True)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.prog["value"] = 0
        self._append_log(f"Comparing {len(pairs)} pair(s), {workers_for(pairs)} at a time")
        self._batch_started = datetime.datetime.now()

        def work():
            from .batch import run_batch
            try:
                results = run_batch(pairs, o, lambda n, total, a, b, res, err: self.q.put(
                    ("batch_one", n, total, a, b, res, err)))
                self.q.put(("batch_done", results))
            except Exception as exc:
                where = _write_error_log(traceback.format_exc())
                self.q.put(("error", f"Unexpected error: {exc}" + (f"\n\nDetails were saved to:\n{where}"
                                                                    if where else "")))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ saved comparisons (this tab)
    def get_state(self) -> dict:
        o = self._collect()
        state = {k: v for k, v in dataclasses.asdict(o).items() if k not in APP_WIDE and k != "open_when_done"}
        state["days"] = self.chosen_days()
        return state

    def set_state(self, s: dict):
        defaults = Options()
        o = Options()
        for k, v in s.items():
            if k not in APP_WIDE and hasattr(o, k) and isinstance(v, type(getattr(defaults, k))):
                setattr(o, k, v)
        keep = self.opts
        self.opts = dataclasses.replace(o, **{k: getattr(keep, k) for k in APP_WIDE})
        self._load_into_widgets()
        self.orig.set(o.original)
        self.upd.set(o.updated)
        self.out_name.set(o.output_name)
        self._pending_days = set(o.days) if o.days else None
        self.opts = keep

    @staticmethod
    def files_in_state(s: dict) -> list:
        if s.get("mode") in ("reorder", "station"):
            return [s["original"]] if s.get("original") else []
        return [p for p in (s.get("original", ""), s.get("updated", "")) if p]

    # ------------------------------------------------------------ days of the week
    def _schedule_days(self):
        if self._days_after:
            self.after_cancel(self._days_after)
        self._days_after = self.after(500, self._read_days)

    def _read_days(self):
        """Find which days the chosen CWNs cover (in a helper process, so the window stays responsive)."""
        self._days_after = None
        paths = [v.get().strip().strip('"') for v in (self.orig, self.upd)]
        paths = [p for p in paths if p and os.path.isfile(p)]
        self._days_token += 1
        token = self._days_token
        if self.mode.get() == "batch":
            self._show_days(set(), "Every day is checked when comparing folders of CWNs.")
            return
        if self.mode.get() in ("reorder", "station"):
            return
        if not paths:
            self._show_days(set(), "Choose the CWNs to pick which days to check (all days by default).")
            return
        self._show_days(set(), "Reading which days the CWNs cover...")

        def one(path):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                return None
            hit = self.cwn_days.get(path)
            if hit and hit[0] == mtime:
                return hit
            from .days import read_days
            try:
                if os.path.getsize(path) < 3 * 1024 * 1024:          # small: quicker than a helper process
                    days, assumed = read_days(path)
                    return (mtime, days, assumed)
                from concurrent.futures import ProcessPoolExecutor
                from multiprocessing import get_context
                with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as ex:
                    days, assumed = ex.submit(read_days, path).result()
            except Exception:
                try:
                    days, assumed = read_days(path)          # helper process unavailable: read here
                except Exception:
                    return None
            return (mtime, days, assumed)

        def work():
            found = {}
            for p in paths:
                try:
                    found[p] = one(p)
                except Exception:
                    found[p] = None
            self.q.put(("days", token, found))
        threading.Thread(target=work, daemon=True).start()

    def _days_read(self, token, found):
        if token != self._days_token:
            return
        days, assumed, unread = set(), False, []
        for path, hit in found.items():
            if hit is None:
                unread.append(os.path.basename(path))
                continue
            self.cwn_days[path] = hit
            days |= set(hit[1])
            assumed = assumed or hit[2]
        if not days:
            self._show_days(set(), "The CWNs' days could not be read - every day will be checked."
                            if unread else "Choose the CWNs to pick which days to check.")
            return
        from .days import label
        note = f"The CWNs cover {label(days)}"
        note += (" (judged from the DAYS codes - the CWNs do not say)." if assumed else ".")
        note += " Untick days to check and output only the trains running on the ticked days."
        if unread:
            note += f" Not read: {', '.join(unread)}."
        self._show_days(days, note)

    def _show_days(self, days: set, note: str):
        self.available_days = set(days)
        pending = self._pending_days if days else None
        for i, (cb, var) in enumerate(zip(self.day_cbs, self.day_vars)):
            cb.state(["!disabled"] if i in days else ["disabled"])
            var.set((i in pending) if pending else (i in days or not days))
        self.all_days_btn.state(["!disabled"] if days else ["disabled"])
        self.day_note.configure(text=note)
        if days:
            self._pending_days = None
            if self._run_when_days_known:
                self._run_when_days_known = False
                self.after(100, self._run)

    def _all_days(self):
        for i, var in enumerate(self.day_vars):
            var.set(i in self.available_days)

    def chosen_days(self) -> list:
        """Ticked days, or [] when every available day is ticked (no filter)."""
        if not self.available_days:
            return []
        ticked = {i for i, v in enumerate(self.day_vars) if v.get()} & self.available_days
        return [] if ticked == self.available_days else sorted(ticked)

    def _read_prev_info(self):
        path = self.orig.get().strip().strip('"')
        if not path or not os.path.exists(path):
            self.prev_info.configure(text="Select a comparison CWN previously generated by this app.")
            return
        self.prev_info_token += 1
        token = self.prev_info_token
        self.prev_info.configure(text="Reading previous comparison...")

        def work():
            try:
                meta = read_meta_file(path)
                if not meta:
                    msg = ("This file was not made by this app's CWN Tools tab - choose a previous "
                           "comparison output.")
                    cols = []
                else:
                    rs = meta.get("rounds", [])
                    cols = [r["colour"] for r in rs]
                    msg = "Previous rounds: " + "; ".join(
                        f"Round {r['round']} ({self._colour_name(r['colour'])}, {r.get('updated', '')})" for r in rs)
                self.q.put(("previnfo", token, msg, cols))
            except Exception as exc:
                self.q.put(("previnfo", token, f"Could not read file: {exc}", []))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _colour_name(c):
        c = c.upper()[-6:]
        return next((n for n, v in PRESET_COLOURS.items() if v == c), "#" + c)

    def _append_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------------------------------------------------------------- run
    def _run(self):
        if self.running:
            return
        o = self._collect()
        if o.mode == "batch":
            return self._run_batch(o)
        if o.mode == "reorder":
            return self._run_reorder(o)
        if o.mode == "station":
            return self._run_station_book(o)
        if not o.original or not o.updated:
            messagebox.showwarning(APP_TITLE, "Please select both files first.")
            return
        for p in (o.original, o.updated):
            if not os.path.exists(p):
                messagebox.showwarning(APP_TITLE, f"File not found:\n{p}")
                return
        if o.output_dir and not os.path.isdir(o.output_dir):
            messagebox.showwarning(APP_TITLE, f"Output folder does not exist:\n{o.output_dir}")
            return
        if self.available_days and not any(v.get() for i, v in enumerate(self.day_vars) if i in self.available_days):
            messagebox.showwarning(APP_TITLE, "Tick at least one day to check.")
            return
        if not any(o.cat(k, "cwn") or o.cat(k, "report") for k, *_ in CATEGORIES):
            messagebox.showwarning(APP_TITLE, "All change types are switched off.")
            return
        self.add_recent("cwn", o.original, o.updated)
        saved = dataclasses.replace(o, output_name="", days=[])      # days are chosen afresh each time
        saved.save()
        self.opts = saved
        self._start()

        def work():
            from .engine import RunError, run         # loaded on first use: the window opens faster
            try:
                res = run(o, progress=lambda f, m: self.q.put(("prog", f, m)),
                          log=lambda m: self.q.put(("log", m)))
                self.q.put(("done", res))
            except (RunError, LoadError) as exc:
                self.q.put(("error", str(exc)))
            except Exception as exc:
                where = _write_error_log(traceback.format_exc())
                self.q.put(("error", f"Unexpected error: {exc}"
                                     + (f"\n\nDetails were saved to:\n{where}" if where else "")))
        threading.Thread(target=work, daemon=True).start()

    def _stop_spin(self):
        if str(self.prog.cget("mode")) == "indeterminate":
            self.prog.stop()
            self.prog.configure(mode="determinate")
        self.prog["value"] = 0

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "prog":
                    self.prog["value"] = item[1]
                    self.status.configure(text=item[2])
                elif kind == "log":
                    self._append_log(item[1])
                elif kind == "days":
                    self._days_read(item[1], item[2])
                elif kind == "previnfo":
                    if item[1] == self.prev_info_token:
                        self.prev_info.configure(text=item[2])
                        used = {c.upper()[-6:] for c in item[3]}
                        if used and self.colour.value in used:
                            for v in PRESET_COLOURS.values():
                                if v not in used:
                                    self.colour.set(v)
                                    break
                elif kind == "update":
                    self._pending_release = item[1]
                    self.update_note.configure(text=f"Update available: v{item[1].version} - click to install")
                elif kind == "done":
                    self.running = False
                    self.set_busy(False)
                    self.run_btn.state(["!disabled"])
                    self.result = item[1]
                    self.status.configure(text="Finished")
                    self.open_cwn.state(["!disabled"])
                    self.open_dir.state(["!disabled"])
                    if self.result.get("report"):
                        self.open_rep.state(["!disabled"])
                    r = self.result
                    self.notify_done("CWN comparison finished", f"{r['changes']} change(s) found.")
                    self.open_outputs([r["cwn"]])
                    from rstools.fsutil import excel_warning
                    warn = excel_warning([r["cwn"], r.get("report")])
                    if warn:
                        self._append_log("WARNING: " + warn)
                    (messagebox.showwarning if warn else messagebox.showinfo)(
                        APP_TITLE, f"Comparison complete.\n\n{r['changes']} change(s) found"
                        + (f", {r['carried']} earlier change(s) carried forward" if r.get('carried') else "")
                        + f".\n\nCWN: {r['cwn']}" + (f"\nReport: {r['report']}" if r.get("report") else "")
                        + (f"\n\n{warn}" if warn else ""))
                elif kind == "bookxml":
                    self._book_xml_read(*item[1:])
                elif kind == "book_done":
                    self._stop_spin()
                    self.running = False
                    self.set_busy(False)
                    self.run_btn.state(["!disabled"])
                    _k, path, warnings, summary = item
                    self.prog["value"] = 1
                    self.status.configure(text="Finished")
                    self.result = {"cwn": path}
                    self.open_cwn.state(["!disabled"])
                    self.open_dir.state(["!disabled"])
                    for w in warnings:
                        self._append_log("WARNING: " + w)
                    self._append_log(summary)
                    self.notify_done("Station working book ready", summary)
                    self.open_outputs([path])
                    (messagebox.showwarning if warnings else messagebox.showinfo)(
                        APP_TITLE, f"{summary}\n\nSaved: {path}" + "".join(f"\n\n{w}" for w in warnings[:4]))
                elif kind == "books_done":
                    self._stop_spin()
                    self.running = False
                    self.set_busy(False)
                    self.run_btn.state(["!disabled"])
                    results = item[1]
                    made = [r for r in results if r[1]]
                    failed = [r for r in results if r[4]]
                    self.prog["value"] = 1
                    self.status.configure(text="Finished")
                    if made:
                        self.result = {"cwn": made[0][1]}
                        self.open_cwn.state(["!disabled"])
                        self.open_dir.state(["!disabled"])
                    for station, _p, warns, summary, err in results:
                        self._append_log(f"{station}: {summary or 'ERROR ' + err}")
                        for w in warns:
                            self._append_log(f"  WARNING: {w}")
                    text = f"{len(made)} station working book(s) made."
                    self.notify_done("Station working books ready", text)
                    self.open_outputs([r[1] for r in made])
                    (messagebox.showwarning if failed else messagebox.showinfo)(
                        APP_TITLE, text + (f"\n\nSaved in: {os.path.dirname(made[0][1])}" if made else "")
                        + "".join(f"\n\n{st}: {err}" for st, _p, _w, _s, err in failed[:6]))
                elif kind == "reorder_done":
                    self._stop_spin()
                    self.running = False
                    self.set_busy(False)
                    self.run_btn.state(["!disabled"])
                    n, tabs, path = item[1]["trains"], item[1]["tabs"], item[1]["path"]
                    self.prog["value"] = 1
                    self.status.configure(text="Finished")
                    text = (f"{n} train(s) on {tabs} tab(s) had their day variants put in order." if n else
                            "Every train's day variants are already in order, so no copy was saved.")
                    self.notify_done("Day variants put in order", text)
                    notes = list(item[1]["warnings"])
                    if path:
                        self.result = {"cwn": path}
                        self.open_cwn.state(["!disabled"])
                        self.open_dir.state(["!disabled"])
                        self._append_log(text)
                        self.open_outputs([path])
                        from rstools.fsutil import excel_warning
                        warn = excel_warning([path])
                        notes += [warn] if warn else []
                        text += f"\n\nSaved: {path}"
                    (messagebox.showwarning if notes else messagebox.showinfo)(
                        APP_TITLE, text + "".join(f"\n\n{w}" for w in notes[:5]))
                elif kind == "batch_one":
                    _k, n, total, a, b, res, err = item
                    self.prog["value"] = n / total
                    self.status.configure(text=f"Compared {n} of {total}")
                    if res:
                        self._append_log(f"{os.path.basename(b)}: {res['changes']} change(s) -> {res['cwn']}")
                    else:
                        self._append_log(f"ERROR {os.path.basename(b)}: {err}")
                elif kind == "batch_done":
                    self.running = False
                    self.set_busy(False)
                    self.run_btn.state(["!disabled"])
                    results = [r for r in item[1] if r]
                    failed = len(item[1]) - len(results)
                    took = (datetime.datetime.now() - self._batch_started).total_seconds()
                    self.status.configure(text=f"Finished in {took:.0f} s")
                    self.result = {"cwn": results[0]["cwn"]} if results else None
                    if results:
                        self.open_dir.state(["!disabled"])
                    from rstools.fsutil import excel_warning
                    warn = excel_warning([r["cwn"] for r in results])
                    summary = (f"{len(results)} comparison(s) made, {sum(r['changes'] for r in results)} change(s) "
                               f"in all." + (f" {failed} could not be compared - see the log." if failed else "")
                               + (f"\n\n{warn}" if warn else ""))
                    self._append_log(summary)
                    self.notify_done("Batch comparison finished", summary, not failed)
                    if results:
                        self.open_outputs([os.path.dirname(results[0]["cwn"])])
                    (messagebox.showwarning if failed or warn else messagebox.showinfo)(APP_TITLE, summary)
                elif kind == "error":
                    self._stop_spin()
                    self.running = False
                    self.set_busy(False)
                    self.run_btn.state(["!disabled"])
                    self.status.configure(text="Failed")
                    self._append_log("ERROR: " + item[1])
                    self.notify_done("CWN comparison failed", item[1].splitlines()[0], False)
                    messagebox.showerror(APP_TITLE, item[1][:1500])
        except queue.Empty:
            pass
        finally:
            self._poll_id = self.after(100, self._poll)     # keep polling even if handling an item failed


def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = App()
    app.mainloop()
