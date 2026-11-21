"""Suggestions under a text box: typing in a station (or group) box lists the matching names just below it.

Matches starting with the typed text come first, then names with a word starting with it, then names
containing it anywhere. Down / Up move through the list, Enter or Tab (or a click) takes the highlighted
name, Escape closes the list. Anything can still be typed into the box, so a name that isn't listed is
accepted as typed."""
from __future__ import annotations

import re
import tkinter as tk
from typing import Callable, List, Optional, Sequence

MAX_ROWS = 10
_NAV = {"Up", "Down", "Return", "KP_Enter", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
        "Alt_L", "Alt_R", "Left", "Right", "Home", "End"}


def matches(typed: str, names: Sequence[str], limit: int = 200) -> List[str]:
    """Names matching the typed text, best first (starts with, then a word starts with, then contains)."""
    t = " ".join(typed.split()).casefold()
    if not t:
        return list(names)[:limit]
    first, word, anywhere = [], [], []
    for n in names:
        low = n.casefold()
        if low.startswith(t):
            first.append(n)
        elif any(w.startswith(t) for w in re.split(r"[\s\-/(),.&']+", low) if w):
            word.append(n)
        elif t in low:
            anywhere.append(n)
    return (first + word + anywhere)[:limit]


class Suggest:
    """Attach a suggestion list to an Entry or editable Combobox. `names` returns the names to suggest
    (called each time, so the list follows the files chosen); `on_pick` runs after a name is taken."""

    def __init__(self, entry: tk.Widget, names: Callable[[], Sequence[str]],
                 on_pick: Optional[Callable[[str], None]] = None):
        self.entry, self.names, self.on_pick = entry, names, on_pick
        self.popup: Optional[tk.Toplevel] = None
        self.box: Optional[tk.Listbox] = None
        self._hide_job = None
        entry.bind("<KeyRelease>", self._typed, add="+")
        entry.bind("<Down>", self._down)
        entry.bind("<Up>", self._up)
        entry.bind("<Return>", self._enter, add="+")
        entry.bind("<KP_Enter>", self._enter, add="+")
        entry.bind("<Tab>", self._tab, add="+")
        entry.bind("<Escape>", self._escape, add="+")
        entry.bind("<FocusOut>", lambda _e: self._later_hide(), add="+")
        entry.bind("<Destroy>", lambda _e: self.hide(), add="+")
        entry.bind("<Configure>", lambda _e: self._place() if self.shown else None, add="+")

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

    def show(self, items: Sequence[str]):
        if not items:
            return self.hide()
        if self.popup is None:
            self._make()
        from rstools import theme
        p = theme.CURRENT or theme.PALETTES["light"]          # the theme in use now (it can be changed)
        self.box.configure(background=p["field"], foreground=p["fg"], selectbackground=p["select"],
                           selectforeground=p.get("select_fg", p["fg"]))
        self.box.delete(0, "end")
        for n in items:
            self.box.insert("end", n)
        self.box.configure(height=min(len(items), MAX_ROWS))
        self._place()
        self.popup.deiconify()
        self.popup.lift()

    def _place(self):
        e = self.entry
        top = e.winfo_toplevel()
        from rstools.theme import screen_area
        room = min(top.winfo_rootx() + top.winfo_width(), screen_area(e)[2]) - e.winfo_rootx() - 4
        width = max(min(e.winfo_width(), room), 160)          # within the window, not off its edge
        self.popup.geometry(f"{width}x{self.box.winfo_reqheight()}+{e.winfo_rootx()}+"
                            f"{e.winfo_rooty() + e.winfo_height()}")

    def hide(self):
        if self.popup is not None:
            try:
                self.popup.withdraw()
            except tk.TclError:
                self.popup = None

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
        if event.keysym in _NAV:
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
        cur = self.box.curselection()
        n = self.box.size()
        i = (cur[0] + step) % n if cur else (0 if step > 0 else n - 1)
        self.box.selection_clear(0, "end")
        self.box.selection_set(i)
        self.box.see(i)
        return "break"

    def _down(self, _e):
        return self._move(1)

    def _up(self, _e):
        return self._move(-1) if self.shown else None

    def _take(self, name: str):
        self.entry.delete(0, "end")
        self.entry.insert(0, name)
        self.entry.icursor("end")
        self.hide()
        if self.on_pick:
            self.on_pick(name)

    def _enter(self, _e):
        if self.shown and self.box.curselection():
            self._take(self.box.get(self.box.curselection()[0]))
            return "break"
        self.hide()
        return None

    def _tab(self, _e):
        if self.shown and self.box.curselection():
            self._take(self.box.get(self.box.curselection()[0]))
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

    def _clicked(self, event):
        if self._hide_job is not None:
            self.entry.after_cancel(self._hide_job)
            self._hide_job = None
        i = self.box.nearest(event.y)
        if i >= 0:
            self._take(self.box.get(i))
        self.entry.focus_set()
