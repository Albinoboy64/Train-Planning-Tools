"""Suggestions under a text box: typing in a station (or group) box lists the matching names just below it.

Matches starting with the typed text come first, then names with a word starting with it, then names
containing it anywhere. Down / Up move through the list, Enter or Tab (or a click) takes the highlighted
name, Escape closes the list. Anything can still be typed into the box, so a name that isn't listed is
accepted as typed."""
from __future__ import annotations

import ntpath
import re
import tkinter as tk
import weakref
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from rstools.naming import shorten_path

MAX_ROWS = 10
_NAV = {"Up", "Down", "Return", "KP_Enter", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
        "Alt_L", "Alt_R", "Left", "Right", "Home", "End"}


MISSING = " (moved, renamed or deleted)"

_LIVE: "weakref.WeakSet" = weakref.WeakSet()       # every suggestion list made, so all can be closed at once


def close_all():
    """Close every suggestion list that is open (the task or tab changed, the window moved): a list is a
    window of its own, always on top, so it would otherwise stay where it was over whatever is shown now."""
    for s in list(_LIVE):
        try:
            if s.shown:
                s.hide()
        except tk.TclError:
            pass


class Choice(str):
    """A suggestion that is shown differently from the text it puts in the box: a recent file is listed by its
    name (`label`) but its full path goes in the box; `missing` files are shown in red and cannot be taken."""
    label: str
    missing: bool

    def __new__(cls, value: str, label: str = "", missing: bool = False):
        obj = super().__new__(cls, value)
        obj.label = label or value
        obj.missing = missing
        return obj

    def __reduce__(self):
        return (Choice, (str(self), self.label, self.missing))


def _label(n: str) -> str:
    return getattr(n, "label", n)


def recent_choices(paths: Iterable[str], full: bool, exists: Callable[[str], bool]) -> List[Choice]:
    """Recent files as suggestions: the file name only (unless `full`), with its folder added where two files
    share a name, and ' (moved, renamed or deleted)' after a file that is no longer there."""
    paths = list(paths)
    names: Dict[str, int] = {}
    for p in paths:
        key = ntpath.basename(p).casefold()
        names[key] = names.get(key, 0) + 1
    out = []
    for p in paths:
        base = ntpath.basename(p) or p
        if full:
            label = p
        elif names[base.casefold()] > 1:
            label = f"{base}  -  {ntpath.basename(ntpath.dirname(p)) or ntpath.dirname(p)}"
        else:
            label = base
        missing = not exists(p)
        out.append(Choice(p, label + (MISSING if missing else ""), missing))
    return out


def matches(typed: str, names: Sequence[str], limit: int = 200) -> List[str]:
    """Names matching the typed text, best first (starts with, then a word starts with, then contains). A Choice
    matches on what it shows as well as its text (a recent file's name or its full path)."""
    t = " ".join(typed.split()).casefold()
    if not t:
        return list(names)[:limit]
    ranked: Tuple[List[str], List[str], List[str]] = ([], [], [])
    for n in names:
        texts = {n.casefold(), _label(n).casefold()}
        if any(x.startswith(t) for x in texts):
            ranked[0].append(n)
        elif any(w.startswith(t) for x in texts for w in re.split(r"[\s\-/\\(),.&'_]+", x) if w):
            ranked[1].append(n)
        elif any(t in x for x in texts):
            ranked[2].append(n)
    return (ranked[0] + ranked[1] + ranked[2])[:limit]


class Suggest:
    """Attach a suggestion list to an Entry or editable Combobox. `names` returns the names to suggest
    (called each time, so the list follows the files chosen); `on_pick` runs after a name is taken.
    paths: the names are file paths; the list is made wide enough to show them whole (within the screen,
    shortening the folders of any that still don't fit), and a Combobox's drop-down arrow opens it."""

    def __init__(self, entry: Any, names: Callable[[], Sequence[str]],
                 on_pick: Optional[Callable[[str], None]] = None, paths: bool = False):
        self.entry, self.names, self.on_pick, self.paths = entry, names, on_pick, paths
        self.popup: Optional[tk.Toplevel] = None
        self.box: Optional[tk.Listbox] = None
        self.items: List[str] = []                     # the names listed (the rows may show them shortened)
        self._path_tip: Optional[Tuple[tk.Toplevel, tk.Label]] = None
        self._hide_job = None
        entry.bind("<ButtonPress-1>", self._pressed, add="+")
        entry.bind("<KeyRelease>", self._typed, add="+")
        entry.bind("<ButtonRelease-1>", self._clicked_box, add="+")
        entry.bind("<Down>", self._down)
        entry.bind("<Up>", self._up)
        entry.bind("<Return>", self._enter, add="+")
        entry.bind("<KP_Enter>", self._enter, add="+")
        entry.bind("<Tab>", self._tab, add="+")
        entry.bind("<Escape>", self._escape, add="+")
        entry.bind("<FocusOut>", lambda _e: self._later_hide(), add="+")
        entry.bind("<Destroy>", lambda _e: self._gone(), add="+")
        entry.bind("<Configure>", lambda _e: self._place() if self.shown else None, add="+")
        entry.bind("<Unmap>", lambda _e: self.hide() if self.shown else None, add="+")     # its row was hidden
        _LIVE.add(self)

    def _on_arrow(self, e) -> bool:
        try:
            return e is not None and "downarrow" in str(self.entry.identify(e.x, e.y))
        except (tk.TclError, AttributeError):
            return False

    def _pressed(self, e):
        """The drop-down arrow opens (or closes) the list of everything it can suggest."""
        if not self._on_arrow(e):
            return None
        try:
            if str(self.entry.cget("state")) == "disabled":
                return "break"
        except tk.TclError:
            return "break"
        if self.shown:
            self.hide()
        else:
            self.entry.focus_set()
            self.show(list(self.names())[:MAX_ROWS * 20])
        return "break"                             # not the Combobox's own (empty) list

    def _clicked_box(self, e=None):
        """A click in the empty box lists everything it can suggest."""
        if self._on_arrow(e):
            return
        try:
            if not self.entry.get().strip() and str(self.entry.cget("state")) != "disabled":
                self.show(list(self.names())[:MAX_ROWS * 20])
        except tk.TclError:
            pass

    @property
    def shown(self) -> bool:
        return self.popup is not None and self.popup.winfo_ismapped()

    # ------------------------------------------------------------------ list
    def _make(self):
        self.popup = tk.Toplevel(self.entry)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        try:
            self.popup.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.box = tk.Listbox(self.popup, activestyle="none", exportselection=False, takefocus=0,
                              borderwidth=1, relief="solid", highlightthickness=0)
        self.box.pack(fill="both", expand=True)
        self.box.bind("<ButtonRelease-1>", self._clicked)
        self.box.bind("<Motion>", self._hover)
        self.box.bind("<Leave>", lambda _e: self._hide_path())

    def show(self, items: Sequence[str]):
        if not items:
            return self.hide()
        if self.popup is None or self.box is None:
            self._make()
        popup, box = self.popup, self.box
        if popup is None or box is None:
            return
        from rstools import theme
        p = theme.CURRENT or theme.PALETTES["light"]          # the theme in use now (it can be changed)
        box.configure(background=p["field"], foreground=p["fg"], selectbackground=p["select"],
                      selectforeground=p.get("select_fg", p["fg"]))
        self.items = list(items)
        width = self._list_width(items)
        box.delete(0, "end")
        for i, n in enumerate(items):
            box.insert("end", self._row(n, width))
            if getattr(n, "missing", False):
                box.itemconfig(i, foreground=p["error"], selectforeground=p["error"])
        box.configure(height=min(len(items), MAX_ROWS))
        self._place(width)
        popup.deiconify()
        popup.lift()
        from rstools import widgets
        widgets.popup_opened(self.popup)

    def _text_width(self, text: str) -> int:
        from tkinter import font
        try:
            return font.Font(font=self.box.cget("font") if self.box is not None else None).measure(text)
        except (tk.TclError, AttributeError):
            return 7 * len(text)

    def _list_width(self, items: Sequence[str]) -> int:
        """The list's width: the box's (within the window); for paths, as wide as the longest path needs,
        up to the width of the screen."""
        e = self.entry
        top = e.winfo_toplevel()
        from rstools.theme import screen_area
        area = screen_area(e)
        room = min(top.winfo_rootx() + top.winfo_width(), area[2]) - e.winfo_rootx() - 4
        width = max(min(e.winfo_width(), room), 160)          # within the window, not off its edge
        if self.paths and items:
            need = max(self._text_width(_label(n)) for n in items) + 24     # the border, padding and a scroll bar
            width = max(width, min(need, area[2] - area[0] - 8))
        return width

    def _row(self, name: str, width: int) -> str:
        """What a row shows: a recent file's name (a Choice's label), or a whole path, its folders shortened
        where it does not fit."""
        shown = _label(name)
        if not self.paths or shown != str(name):
            return shown
        return shorten_path(shown, lambda t: self._text_width(t) + 24 <= width)

    def _place(self, width: Optional[int] = None):
        e = self.entry
        if self.box is None or self.popup is None:
            return
        from rstools.theme import screen_area
        area = screen_area(e)
        if width is None:
            width = self._list_width(self.items)
        x = max(min(e.winfo_rootx(), area[2] - width - 4), area[0])   # moved left if it would go off screen
        self.box.update_idletasks()                          # the height for the rows just put in
        height = self.box.winfo_reqheight()
        y = e.winfo_rooty() + e.winfo_height()
        if y + height > area[3] and e.winfo_rooty() - height >= area[1]:
            y = e.winfo_rooty() - height                     # no room below the box: open above it
        self.popup.geometry(f"{width}x{height}+{x}+{y}")

    def hide(self):
        self._hide_path()
        if self.popup is not None:
            from rstools import widgets
            widgets.popup_closed(self.popup)
            try:
                self.popup.withdraw()
            except tk.TclError:
                self.popup = None

    def _show_path(self, i: int):
        """A row showing a shortened name: its full text beside the list (never over its rows)."""
        n = self.items[i] if 0 <= i < len(self.items) else ""
        if not n or _label(n) == n or self.popup is None or self.box is None:
            return self._hide_path()
        from rstools import theme
        p = theme.CURRENT or theme.PALETTES["light"]
        if self._path_tip is None:
            tip = tk.Toplevel(self.popup)
            tip.withdraw()
            tip.overrideredirect(True)
            try:
                tip.attributes("-topmost", True)
            except tk.TclError:
                pass
            label = tk.Label(tip, justify="left", borderwidth=1, relief="solid", padx=4, pady=1)
            label.pack()
            self._path_tip = (tip, label)
        tip, label = self._path_tip
        label.configure(text=str(n) + (MISSING if getattr(n, "missing", False) else ""), background=p["tip"],
                        foreground=p["error"] if getattr(n, "missing", False) else p["fg"])
        tip.update_idletasks()
        bbox = self.box.bbox(i)
        y = self.popup.winfo_rooty() + (bbox[1] if bbox else 0)
        x = self.popup.winfo_rootx() + self.popup.winfo_width() + 2
        area = theme.screen_area(self.entry)
        if x + tip.winfo_reqwidth() > area[2]:            # no room on the right: on the left of the list
            x = max(area[0], self.popup.winfo_rootx() - tip.winfo_reqwidth() - 2)
        tip.geometry(f"+{x}+{y}")
        tip.deiconify()
        tip.lift()

    def _hide_path(self):
        if self._path_tip is not None:
            try:
                self._path_tip[0].withdraw()
            except tk.TclError:
                self._path_tip = None

    def _gone(self):
        """The box is being closed: stop a pending hide check, then hide the list."""
        if self._hide_job is not None:
            try:
                self.entry.after_cancel(self._hide_job)
            except tk.TclError:
                pass
            self._hide_job = None
        self.hide()

    def _later_hide(self):
        # a click in the list moves the focus first; give the click time to land, and keep the list open
        # while the focus is still in the box or the list
        def check():
            self._hide_job = None
            try:
                focus = self.entry.focus_get()
            except (KeyError, tk.TclError):         # focus in a window tkinter doesn't know (a dialog)
                focus = None
            if focus not in (self.entry, self.box, self.popup):
                self.hide()
        if self._hide_job is None:
            self._hide_job = self.entry.after(200, check)

    # ------------------------------------------------------------------ events
    def _typed(self, event):
        if event.keysym in _NAV or (getattr(event, "state", 0) or 0) & 0x4:   # Ctrl+1..4 etc.: a shortcut
            return
        text = self.entry.get()
        items = matches(text, self.names())
        if not text.strip() or (len(items) == 1 and items[0] == text):
            return self.hide()
        self.show(items)

    def _move(self, step: int):
        if not self.shown:
            self.show(matches(self.entry.get(), self.names()) or list(self.names())[:200])
            return "break"
        box = self.box
        n = box.size() if box is not None else 0
        if box is None or not n:
            return "break"
        cur = box.curselection()
        i = (cur[0] + step) % n if cur else (0 if step > 0 else n - 1)
        box.selection_clear(0, "end")
        box.selection_set(i)
        box.see(i)
        self._show_path(i)
        return "break"

    def _down(self, _e):
        return self._move(1)

    def _up(self, _e):
        return self._move(-1) if self.shown else None

    def _pick(self, i: int) -> Optional[str]:
        """What row i puts in the box (None for a file that is no longer there)."""
        n = self._item(i)
        if not n or getattr(n, "missing", False):
            try:
                self.entry.bell()
            except tk.TclError:
                pass
            return None
        return str(n)

    def _take(self, name: Optional[str]):
        if name is None:
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, name)
        self.entry.icursor("end")
        self.hide()
        if self.on_pick:
            self.on_pick(name)

    def _item(self, i: int) -> str:
        if 0 <= i < len(self.items) or self.box is None:
            return self.items[i] if 0 <= i < len(self.items) else ""
        return self.box.get(i)

    def _enter(self, _e):
        if self.shown and self.box.curselection():
            self._take(self._pick(self.box.curselection()[0]))
            return "break"
        self.hide()
        return None

    def _tab(self, _e):
        if self.shown and self.box.curselection():
            self._take(self._pick(self.box.curselection()[0]))
        self.hide()

    def _escape(self, _e):
        if self.shown:
            self.hide()
            return "break"
        return None

    def _hover(self, event):
        i = self.box.nearest(event.y)
        self.box.selection_clear(0, "end")
        self.box.selection_set(i)
        self._show_path(i)

    def _clicked(self, event):
        if self._hide_job is not None:
            self.entry.after_cancel(self._hide_job)
            self._hide_job = None
        i = self.box.nearest(event.y)
        if i >= 0:
            name = self._pick(i)
            if name is None:
                return                              # a file no longer there: the list stays open
            self._take(name)
        self.entry.focus_set()
