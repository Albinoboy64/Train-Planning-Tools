"""Small reusable widgets for the Train Planning Tools window."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk


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
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.bind_all("<Button-4>", self._wheel, add="+")
        self.bind_all("<Button-5>", self._wheel, add="+")

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
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError):
            return
        while widget is not None and widget is not self:
            widget = widget.master
        if widget is None:
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

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip, self._after = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.DELAY_MS, self.show)

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
            tk.Label(self.tip, text=self.text, background=p["tip"], foreground=p["fg"], relief="solid", bd=1,
                     wraplength=380, justify="left", padx=7, pady=4).pack()
            self.tip.update_idletasks()
            w, h = self.tip.winfo_reqwidth(), self.tip.winfo_reqheight()
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            sw, sh = self.widget.winfo_screenwidth(), self.widget.winfo_screenheight()
            x = max(0, min(x, sw - w - 8))
            if y + h > sh - 40:                     # no room below: show above the widget
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


def tip(widget, text: str):
    """Attach help text to a widget; returns the widget (so it can wrap a .grid() chain's widget)."""
    Tooltip(widget, text)
    return widget
