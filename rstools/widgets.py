"""Small reusable widgets for the Train Planning Tools window."""
from __future__ import annotations

import sys
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional


class ScrollPage(ttk.Frame):
    """A notebook page whose contents scroll when the window is too small to show them all,
    and otherwise stretch to fill it (so logs and lists still grow with the window)."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", self._fit)
        self.body.bind("<Configure>", self._fit)
        pages = self.winfo_toplevel().__dict__.setdefault("_scroll_pages", [])
        if not pages:                       # one wheel handler for every page: it finds the page under the mouse
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.bind_all(seq, lambda e, pages=pages: ScrollPage._route(pages, e), add="+")
        pages.append(self)

    @staticmethod
    def _route(pages, event):
        try:
            widget = event.widget.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError, AttributeError):
            return
        while widget is not None:
            if widget in pages:
                return widget._wheel(event)
            widget = widget.master

    def _fit(self, _e=None):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        need = self.body.winfo_reqheight()
        self.canvas.itemconfigure(self._win, width=width, height=max(height, need))
        self.canvas.configure(scrollregion=(0, 0, width, max(height, need)))
        if need > height + 1:
            self.bar.grid(row=0, column=1, sticky="ns")
        else:
            self.bar.grid_remove()
            self.canvas.yview_moveto(0)

    def _wheel(self, event):
        """Scroll the page under the pointer (not the log or a drop-down list)."""
        if not self.bar.winfo_ismapped() or isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview)):
            return
        if getattr(event, "num", None) in (4, 5):
            step = -1 if event.num == 4 else 1
        else:
            step = -1 if event.delta > 0 else 1
            if sys.platform == "darwin":
                step = -event.delta
        self.canvas.yview_scroll(step * 3, "units")


class Tooltip:
    """Help text shown when the mouse rests on a widget (after a short delay, kept on screen)."""
    DELAY_MS = 450

    def __init__(self, widget, text: str, delay: int = 0):
        self.widget, self.text, self.tip, self._after = widget, text, None, None
        self.delay = delay or self.DELAY_MS
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")       # no pending tip left to fire after the widget goes

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self.show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def show(self, _e=None):
        self._after = None
        if self.tip or not self.text:
            return
        try:
            root = self.widget.winfo_toplevel()
            p = getattr(root, "palette", None) or {"tip": "#FFFFE1", "fg": "#1B1B1B", "border": "#C4C4C4"}
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            try:
                self.tip.wm_attributes("-topmost", True)
            except tk.TclError:
                pass
            from rstools.theme import px
            tk.Label(self.tip, text=self.text, background=p["tip"], foreground=p["fg"], relief="solid", bd=1,
                     wraplength=px(self.widget, 380), justify="left", padx=px(self.widget, 7),
                     pady=px(self.widget, 4)).pack()
            self.tip.update_idletasks()
            w, h = self.tip.winfo_reqwidth(), self.tip.winfo_reqheight()
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            from rstools.theme import screen_area
            left, _top, right, bottom = screen_area(self.widget)        # the display the window is on
            x = max(left, min(x, right - w - 8))
            if y + h > bottom - 8:                  # no room below: show above the widget
                y = self.widget.winfo_rooty() - h - 4
            self.tip.wm_geometry(f"+{x}+{y}")
        except tk.TclError:
            self.tip = None

    def hide(self, _e=None):
        self._cancel()
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


def local_folder_box(entry, var):
    """An output folder box that only takes a folder on this PC: a network or shared drive (chosen, typed or
    from saved settings) is refused, and the box is left blank, which saves to Downloads."""
    from tkinter import messagebox
    from rstools.fsutil import NETWORK_REFUSED, is_network_path
    busy = []

    def check(_e=None):
        if busy or not is_network_path(var.get()):
            return
        busy.append(1)
        try:
            var.set("")
            messagebox.showwarning("Output folder", NETWORK_REFUSED, parent=entry)
        finally:
            busy.clear()

    def written(*_a):                       # chosen with Browse or loaded: checked straight away
        try:
            if entry.focus_get() is not entry:
                entry.after_idle(check)
        except (tk.TclError, KeyError):
            pass
    entry.bind("<FocusOut>", check, add="+")                   # typed: checked when the box is left
    var.trace_add("write", written)
    Tooltip(entry, "Leave blank to save to your Downloads folder. Outputs are saved on this PC only, never on a "
                   "network or shared drive.")
    return entry


class QueuePump:
    """Reads the tabs' worker queues on the window's thread: often while work is going on (or has just been
    started), otherwise about once a second - so an idle window costs next to nothing. Each tab adds its
    queue with add(); kick() after starting a worker thread."""
    FAST_MS, SLOW_MS, LINGER_S = 60, 1000, 2.0

    def __init__(self, root):
        self.root = root
        self.parts: List[tuple] = []           # (queue, handle, busy)
        self._after: Optional[str] = None
        self._fast_until = 0.0
        self._due = 0.0

    def add(self, q, handle: Callable[[], None], busy: Callable[[], bool] = lambda: False):
        self.parts.append((q, handle, busy))
        self.kick()

    def kick(self):
        """Work was just started: look at the queues soon and often for a while."""
        self._fast_until = time.monotonic() + self.LINGER_S
        self._schedule(self.FAST_MS)

    def _schedule(self, ms: int):
        due = time.monotonic() + ms / 1000
        if self._after is not None:
            if self._due <= due:
                return
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
        self._due = due
        try:
            self._after = self.root.after(ms, self._tick)
        except tk.TclError:                    # the window is closing
            self._after = None

    def _tick(self):
        self._after = None
        active = time.monotonic() < self._fast_until
        for q, handle, busy in self.parts:
            had = not q.empty()
            if had:
                try:
                    handle()
                except Exception:              # one tab's failure must not stop the others being read
                    import traceback
                    from rstools import errorlog
                    errorlog.write(traceback.format_exc())
            try:
                active = active or had or busy()
            except Exception:
                pass
        self._schedule(self.FAST_MS if active else self.SLOW_MS)

    def stop(self):
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None


class Progress:
    """A progress bar that shows real progress steadily: during a run it never goes back, it is redrawn only
    when it has moved visibly, and the status text changes only when the message does."""

    def __init__(self, bar: ttk.Progressbar, label=None):
        self.bar, self.label = bar, label
        self.value = 0.0
        self._shown = -1.0
        self._msg: Optional[str] = None

    def begin(self, msg: str = ""):
        self.value = 0.0
        self._msg = None
        self._draw(0.0)
        self.message(msg)

    def set(self, fraction: float, msg: Optional[str] = None):
        f = min(max(float(fraction), self.value), 1.0)
        self.value = f
        if f - self._shown >= 0.004 or (f >= 1.0 > self._shown):
            self._draw(f)
        if msg:
            self.message(msg)

    def finish(self, ok: bool = True):
        if ok:
            self.set(1.0)

    def message(self, msg: str):
        if self.label is not None and msg and msg != self._msg:
            self._msg = msg
            self.label.configure(text=msg)

    def _draw(self, f: float):
        self._shown = f
        self.bar["value"] = f
