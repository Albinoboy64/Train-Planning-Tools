"""A table of rows edited in the app (Settings > Fleet data, Depots, Corridors, Berthing locations), in place of
opening the CSV in Excel: double-click a cell (or select a row and press Enter) to change it, Add / Delete / Move
the rows, Save. 'Open in Excel' is still there for big changes.

The rows are plain text. Before saving, a column that holds numbers is checked, and every value loses the
control characters a file cannot hold; a value is never turned into a formula (the CSVs are read as text)."""
from __future__ import annotations

import csv
import io
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, Sequence

from rstools.theme import px

Rows = List[Dict[str, str]]


@dataclass
class Column:
    name: str
    width: int = 120                    # pixels at normal text size
    number: bool = False                # a whole or decimal number, or blank


# --------------------------------------------------------------------------- the rows, without a window
def clean(value) -> str:
    from rstools.fsutil import clean_cell
    return " ".join(str(clean_cell(str(value if value is not None else ""))).split())


def problems(columns: Sequence[Column], rows: Rows) -> List[str]:
    """What stops the rows being saved: a number column holding something else (row numbers from 1)."""
    out = []
    for i, r in enumerate(rows, start=1):
        for c in columns:
            v = clean(r.get(c.name, ""))
            if c.number and v:
                try:
                    float(v)
                except ValueError:
                    out.append(f"Row {i}, {c.name}: '{v}' is not a number.")
    return out


def to_csv(columns: Sequence[Column], rows: Rows) -> str:
    """The rows as CSV text (every value cleaned; blank rows left out)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([c.name for c in columns])
    for r in rows:
        vals = [clean(r.get(c.name, "")) for c in columns]
        if any(vals):
            w.writerow(vals)
    return buf.getvalue()


def read_csv(path: str) -> Rows:
    """A settings CSV as rows ({} for a file that cannot be read)."""
    from rstools import limits
    try:
        limits.check_size(path, "SETTINGS_CSV_MAX_BYTES", os.path.basename(path))
    except OSError:
        return []
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
        except UnicodeDecodeError:
            continue
        except OSError:
            return []
    return []


def header(path: str) -> List[str]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [h.strip() for h in next(csv.reader(fh), [])]
    except (OSError, UnicodeDecodeError):
        return []


def write_csv(path: str, columns: Sequence[Column], rows: Rows) -> bool:
    """Save rows over the user's CSV (atomically, UTF-8 with a BOM so Excel shows it correctly)."""
    from rstools.fsutil import atomic_path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with atomic_path(path) as tmp, open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(to_csv(columns, rows))
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- the window part
class TableEditor(ttk.Frame):
    """A table with its buttons. load() gives the rows; save(rows) keeps them (True if saved); default() gives the
    built-in rows (for 'Back to built-in'); open_file() opens the file in Excel."""

    def __init__(self, master, columns: Sequence[Column], load: Callable[[], Rows], save: Callable[[Rows], bool],
                 default: Optional[Callable[[], Rows]] = None, open_file: Optional[Callable[[], None]] = None,
                 on_saved: Optional[Callable[[], None]] = None, height: int = 14):
        super().__init__(master)
        self.columns = list(columns)
        self.load, self.save_fn, self.default, self.open_file, self.on_saved = load, save, default, open_file, on_saved
        self.rows: Rows = []
        self.dirty = False
        self.watch_path: Optional[Callable[[], str]] = None     # the file, to re-read only when it changes
        self._edit: Optional[ttk.Entry] = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        names = [c.name for c in self.columns]
        self.tree = ttk.Treeview(self, columns=names, show="headings", height=height, selectmode="browse")
        for c in self.columns:
            self.tree.heading(c.name, text=c.name, anchor="w")
            self.tree.column(c.name, width=px(self, c.width), minwidth=px(self, 40), anchor="w", stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        xs.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.bind("<Double-1>", self._double)
        self.tree.bind("<Return>", lambda _e: self._edit_cell(self._selected(), 0))
        self.tree.bind("<Delete>", lambda _e: self._delete())
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        buttons = [("Add row", self._add), ("Delete row", self._delete), ("Move up", lambda: self._move(-1)),
                   ("Move down", lambda: self._move(1))]
        for i, (text, cmd) in enumerate(buttons):
            ttk.Button(bar, text=text, command=cmd).grid(row=0, column=i, padx=(0, 4))
        bar.columnconfigure(len(buttons), weight=1)
        col = len(buttons) + 1
        if self.default is not None:
            ttk.Button(bar, text="Back to built-in", command=self._reset).grid(row=0, column=col, padx=(0, 4))
            col += 1
        if self.open_file is not None:
            ttk.Button(bar, text="Open in Excel", command=self._open).grid(row=0, column=col, padx=(0, 4))
            col += 1
        self.save_btn = ttk.Button(bar, text="Save", command=self.save)
        self.save_btn.grid(row=0, column=col)
        self.status = ttk.Label(self, text="", style="Small.TLabel")
        self.status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.reload()

    # ---------------------------------------------------------------- rows
    def reload(self):
        self.rows = [dict(r) for r in self.load()]
        self._fill()
        self._set_dirty(False)

    def _fill(self, select: Optional[int] = None):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), values=[r.get(c.name, "") for c in self.columns])
        if select is not None and 0 <= select < len(self.rows):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))

    def _selected(self) -> int:
        sel = self.tree.selection()
        return int(sel[0]) if sel else -1

    def _set_dirty(self, dirty: bool):
        self.dirty = dirty
        self.status.configure(text="Not saved yet - press Save." if dirty else "")

    def _add(self):
        at = self._selected() + 1 if self._selected() >= 0 else len(self.rows)
        new = {c.name: "" for c in self.columns}
        if 0 < at <= len(self.rows):                  # a new berth on the same sheet, etc.: copy the first column
            new[self.columns[0].name] = self.rows[at - 1].get(self.columns[0].name, "")
        self.rows.insert(at, new)
        self._fill(at)
        self._set_dirty(True)
        self.after_idle(lambda: self._edit_cell(at, 1 if len(self.columns) > 1 and new[self.columns[0].name] else 0))

    def _delete(self):
        i = self._selected()
        if i < 0:
            return
        del self.rows[i]
        self._fill(min(i, len(self.rows) - 1))
        self._set_dirty(True)

    def _move(self, step: int):
        i = self._selected()
        j = i + step
        if i < 0 or not 0 <= j < len(self.rows):
            return
        self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
        self._fill(j)
        self._set_dirty(True)

    # ---------------------------------------------------------------- editing a cell
    def _double(self, event):
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if row and col:
            self._edit_cell(int(row), int(col[1:]) - 1)

    def _edit_cell(self, i: int, c: int):
        if i < 0 or not 0 <= c < len(self.columns):
            return
        self._end_edit(True)
        self.tree.see(str(i))
        self.tree.update_idletasks()
        box = self.tree.bbox(str(i), f"#{c + 1}")
        if not box:
            return
        x, y, w, h = box
        var = tk.StringVar(value=self.rows[i].get(self.columns[c].name, ""))
        e = self._edit = ttk.Entry(self.tree, textvariable=var)
        e.place(x=x, y=y, width=w, height=h)
        e.focus_set()
        e.select_range(0, "end")
        e._cell = (i, c, var)                            # type: ignore[attr-defined]
        e.bind("<Return>", lambda _e: self._end_edit(True))
        e.bind("<KP_Enter>", lambda _e: self._end_edit(True))
        e.bind("<Escape>", lambda _e: self._end_edit(False))
        e.bind("<FocusOut>", lambda _e: self._end_edit(True))
        e.bind("<Tab>", lambda _e: self._next(i, c, 1))
        e.bind("<Shift-Tab>", lambda _e: self._next(i, c, -1))
        e.bind("<ISO_Left_Tab>", lambda _e: self._next(i, c, -1))

    def _next(self, i: int, c: int, step: int):
        self._end_edit(True)
        c += step
        if c >= len(self.columns):
            i, c = i + 1, 0
        elif c < 0:
            i, c = i - 1, len(self.columns) - 1
        if 0 <= i < len(self.rows):
            self.tree.selection_set(str(i))
            self._edit_cell(i, c)
        return "break"

    def _end_edit(self, keep: bool):
        e = self._edit
        if e is None:
            return
        self._edit = None
        i, c, var = e._cell                              # type: ignore[attr-defined]
        if keep and 0 <= i < len(self.rows):
            value = clean(var.get())
            name = self.columns[c].name
            if value != self.rows[i].get(name, ""):
                self.rows[i][name] = value
                self.tree.set(str(i), name, value)
                self._set_dirty(True)
        try:
            e.destroy()
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- buttons
    def save(self) -> bool:
        self._end_edit(True)
        bad = problems(self.columns, self.rows)
        if bad:
            messagebox.showwarning("Not saved", "\n".join(bad[:10]) + ("\n..." if len(bad) > 10 else ""), parent=self)
            return False
        rows = [{c.name: clean(r.get(c.name, "")) for c in self.columns} for r in self.rows]
        rows = [r for r in rows if any(r.values())]
        if not self.save_fn(rows):
            messagebox.showwarning("Not saved", "The settings folder could not be written to, so nothing was "
                                                "saved.", parent=self)
            return False
        self.rows = rows
        self._fill()
        self._set_dirty(False)
        self.status.configure(text="Saved.")
        if self.on_saved is not None:
            self.on_saved()
        return True

    def _reset(self):
        if self.default is None:
            return
        if not messagebox.askyesno("Back to built-in", "Replace these rows with the app's built-in list? Your "
                                                       "changes are lost when you press Save.", parent=self):
            return
        self.rows = [dict(r) for r in self.default()]
        self._fill()
        self._set_dirty(True)

    def _open(self):
        if self.dirty and messagebox.askyesno("Open in Excel", "Save your changes first?", parent=self):
            if not self.save():
                return
        if self.open_file is not None:
            self.open_file()
        self.status.configure(text="Opened in Excel. Save and close it there, then come back here: the rows are "
                                   "read again.")
        self._seen = self._stamp()
        if not getattr(self, "_watching", False):
            self._watching = True
            top = self.winfo_toplevel()
            top.bind("<FocusIn>", lambda e: self._reread() if e.widget is top else None, add="+")

    def _stamp(self):
        """The file's modified time and size (None when the editor has no file, or it cannot be read)."""
        path_fn = getattr(self, "watch_path", None)
        if path_fn is None:
            return None
        try:
            st = os.stat(path_fn())
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _reread(self):
        """The window came back (from Excel): the rows are read again, only if the file was changed there."""
        if self.dirty or not self.winfo_exists():
            return
        now = self._stamp()
        if now is not None and now == getattr(self, "_seen", None):
            return
        self._seen = now
        self.reload()


def csv_editor(master, path_fn: Callable[[], str], default_path: str, numbers: Sequence[str] = (),
               widths: Optional[Dict[str, int]] = None, open_path: Optional[Callable[[str], None]] = None,
               on_saved: Optional[Callable[[], None]] = None) -> TableEditor:
    """A TableEditor over one of the app's settings CSVs (the user's copy, made by `path_fn`), its columns those
    of the built-in file."""
    names = header(path_fn()) or header(default_path)
    for n in header(default_path):
        if n not in names:
            names.append(n)
    columns = [Column(n, (widths or {}).get(n, max(80, min(260, 9 * len(n)))), n in numbers) for n in names]
    editor = TableEditor(master, columns, load=lambda: read_csv(path_fn()),
                         save=lambda rows: (os.path.abspath(path_fn()) != os.path.abspath(default_path)
                                            and write_csv(path_fn(), columns, rows)),     # never the built-in file
                         default=lambda: read_csv(default_path),
                         open_file=(lambda: open_path(path_fn())) if open_path else None, on_saved=on_saved)
    editor.watch_path = path_fn             # re-read after Excel only when the file has changed
    return editor
