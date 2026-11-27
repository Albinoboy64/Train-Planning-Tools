"""Live View in its own window: the Live View is moved out of the main window into a window of its own (to put it
on another monitor or full screen) and back again, keeping everything in it - the comparison, the selection, the
ticks and a run in progress - because the same widgets move (Tk's 'wm manage' turns the frame holding the Live View
into a window, and 'wm forget' puts it back).

The window's size and place are kept in the settings ('WxH+X+Y'); a place that is no longer on any screen (a
monitor was unplugged) is not used, and the window opens on the main screen instead."""
from __future__ import annotations

import re
import sys
from typing import Callable, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:                     # the geometry helpers below are used (and tested) without a window system
    tk = ttk = None  # type: ignore[assignment]

from rstools.branding import APP_NAME  # noqa: E402

TITLE = f"{APP_NAME} - Live View"
MIN_VISIBLE = (160, 60)                # px of the window that must be on a screen for a saved place to be used
DEFAULT_SIZE = (1200, 760)
GEOMETRY = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")     # as 'wm geometry' gives it: '1200x800+-1920+0'


def parse_geometry(text: str) -> Optional[Tuple[int, int, int, int]]:
    """(width, height, x, y) of a 'WxH+X+Y' geometry (X / Y are negative, '+-1920', on a monitor left of / above
    the main one), or None."""
    m = GEOMETRY.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))


def fit_geometry(saved: str, desktop: Tuple[int, int, int, int], screen: Tuple[int, int]) -> str:
    """The geometry to open the window at: `saved` when enough of it is on the desktop (x, y, width, height of
    every monitor together), otherwise a default size centred on the main screen (width, height)."""
    g = parse_geometry(saved)
    dx, dy, dw, dh = desktop
    if g:
        w, h, x, y = g
        seen_w = min(x + w, dx + dw) - max(x, dx)
        seen_h = min(y + h, dy + dh) - max(y, dy)
        if w >= 200 and h >= 150 and seen_w >= MIN_VISIBLE[0] and seen_h >= MIN_VISIBLE[1] and y >= dy:
            return f"{w}x{h}+{x}+{y}"
    sw, sh = screen
    w, h = min(DEFAULT_SIZE[0], sw - 40), min(DEFAULT_SIZE[1], sh - 80)
    return f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}"


def desktop_area(widget) -> Tuple[int, int, int, int]:
    """(x, y, width, height) of all the monitors together (Windows' virtual screen), or the main screen."""
    if sys.platform == "win32":
        try:
            import ctypes
            m = ctypes.windll.user32.GetSystemMetrics
            area = (m(76), m(77), m(78), m(79))      # SM_X/YVIRTUALSCREEN, SM_CX/CYVIRTUALSCREEN
            if area[2] > 0 and area[3] > 0:
                return area
        except Exception:
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


class LiveWindow:
    """Moves the Live View's output (`holder`, the tk.Frame with the train list and details, in the Live View tab
    `tab`) into its own window and back. The task, files and options stay in the main window, and a comparison
    started there shows in the window. While the output is out, the tab shows a note with a button to bring it back."""

    def __init__(self, app, holder: tk.Frame, tab):
        self.app, self.holder, self.tab = app, holder, tab
        self.out = False
        self.fullscreen = False
        self._seen = None
        self.on_top = tk.BooleanVar(value=bool(getattr(app.opts, "live_window_on_top", False)))
        self.note = ttk.Frame(tab, padding=24)
        ttk.Label(self.note, text="The results are in their own window.", font="AppBold").grid(row=0, column=0,
                                                                                               sticky="w")
        ttk.Button(self.note, text="Show the window", command=self.show).grid(row=2, column=0, sticky="w",
                                                                              pady=(8, 0))
        ttk.Button(self.note, text="Bring back", command=self.bring_back).grid(row=2, column=1, sticky="w",
                                                                              padx=(8, 0), pady=(8, 0))

    # ------------------------------------------------------------------ moving
    def toggle(self):
        self.bring_back() if self.out else self.pop_out()

    def pop_out(self) -> bool:
        if self.out:
            self.show()
            return True
        self.tab.output_place(False)
        try:
            self.holder.tk.call("wm", "manage", self.holder)
        except tk.TclError:                    # a system that cannot make a frame a window: leave it in the tab
            self.tab.output_place(True)
            return False
        self.out = True
        w = str(self.holder)
        self.holder.tk.call("wm", "title", w, TITLE)
        self.holder.tk.call("wm", "minsize", w, 640, 420)
        self.holder.tk.call("wm", "geometry", w, fit_geometry(getattr(self.app.opts, "live_window", ""),
                                                              desktop_area(self.holder),
                                                              (self.holder.winfo_screenwidth(),
                                                               self.holder.winfo_screenheight())))
        self.holder.tk.call("wm", "protocol", w, "WM_DELETE_WINDOW", self.holder.register(self.bring_back))
        self._apply_on_top()
        keys: List[Tuple[str, Callable[[], object]]] = [
            ("<F11>", self.toggle_fullscreen), ("<Escape>", self._escape), ("<F5>", self._run),
            ("<Control-Return>", self._run), ("<Control-Shift-P>", self.bring_back),
            ("<Control-Shift-p>", self.bring_back)]
        for seq, fn in keys:
            self.holder.bind(seq, self._key(fn))
        self.holder.bind("<Configure>", self._configured, add="+")
        self.note.grid(row=3, column=0, sticky="nsew")
        self.tab.window_changed(True)
        self.show()
        return True

    def bring_back(self):
        if not self.out:
            return
        self._save_place()
        if self.fullscreen:
            self.toggle_fullscreen()
        w = str(self.holder)
        try:
            self.holder.tk.call("wm", "attributes", w, "-topmost", 0)
        except tk.TclError:
            pass
        self.holder.tk.call("wm", "forget", self.holder)
        for seq in ("<F11>", "<Escape>", "<F5>", "<Control-Return>", "<Control-Shift-P>", "<Control-Shift-p>",
                    "<Configure>"):
            self.holder.unbind(seq)
        self.out = False
        self.note.grid_remove()
        self.tab.output_place(True)
        self.tab.set_display_ratio(1.0)
        self.tab.window_changed(False)
        try:
            self.app.notebook.select(self.app.live_page)
        except (AttributeError, tk.TclError):
            pass

    def _configured(self, event):
        """The window moved or resized: if it is now on a display with other scaling, the list and details are
        sized for it (Tk has one scaling for the app, set for the main window's display)."""
        if event.widget is not self.holder:
            return
        if self._seen:
            self.holder.after_cancel(self._seen)
        self._seen = self.holder.after(200, self._rescale_for_display)

    def _rescale_for_display(self):
        self._seen = None
        if not self.out:
            return
        try:
            from rstools import theme
            dpi, main = theme.window_dpi(self.holder), max(getattr(self.app, "dpi", 0) or 0, 1)
            self.tab.set_display_ratio(dpi / main)
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _key(fn: Callable[[], object]) -> Callable[[object], str]:
        def handler(_event) -> str:
            fn()
            return "break"
        return handler

    def show(self):
        if self.out:
            w = str(self.holder)
            self.holder.tk.call("wm", "deiconify", w)
            self.holder.tk.call("raise", w)
            self.holder.focus_set()

    # ------------------------------------------------------------------ window options
    def toggle_fullscreen(self):
        if not self.out:
            return
        self.fullscreen = not self.fullscreen
        try:
            self.holder.tk.call("wm", "attributes", str(self.holder), "-fullscreen", int(self.fullscreen))
        except tk.TclError:
            self.fullscreen = False
        self.tab.window_changed(True)

    def set_on_top(self, value: Optional[bool] = None):
        if value is not None:
            self.on_top.set(bool(value))
        self.app.opts.live_window_on_top = bool(self.on_top.get())
        self._apply_on_top()

    def _apply_on_top(self):
        if self.out:
            try:
                self.holder.tk.call("wm", "attributes", str(self.holder), "-topmost", int(bool(self.on_top.get())))
            except tk.TclError:
                pass

    def _escape(self):
        if self.fullscreen:
            self.toggle_fullscreen()

    def _run(self):
        self.tab.run()

    def _save_place(self):
        if self.out and not self.fullscreen:
            try:
                geom = str(self.holder.tk.call("wm", "geometry", str(self.holder)))
            except tk.TclError:
                return
            if parse_geometry(geom):
                self.app.opts.live_window = geom
