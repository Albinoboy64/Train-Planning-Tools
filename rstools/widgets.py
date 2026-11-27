"""Small reusable widgets for the Train Planning Tools window."""
from __future__ import annotations

import sys
import time
from functools import partial
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
                # the wheel over a drop-down scrolls the page: Tk's own binding would change the choice (and
                # with it the task, clearing the files chosen) as the pointer passes over it
                self.bind_class("TCombobox", seq, lambda e, pages=pages: (ScrollPage._route(pages, e), "break")[1])
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


_OPEN_POPUPS: set = set()          # drop-down lists open now (suggestion lists, combobox popdowns)
_SHOWN_TIPS: list = []             # tooltips on screen now


def popup_opened(popup) -> None:
    """A drop-down list has opened: hide every tip, and show none while it is open (a tip would cover it)."""
    _OPEN_POPUPS.add(str(popup))
    for tip in list(_SHOWN_TIPS):
        tip.hide()


def popup_closed(popup) -> None:
    _OPEN_POPUPS.discard(str(popup))


def popup_open() -> bool:
    return bool(_OPEN_POPUPS)


def guard_popdown(combo) -> None:
    """Tell the tooltips when a combobox's own drop-down list opens and closes (see popup_opened)."""
    if getattr(combo, "_popdown_guarded", False):
        return
    try:
        path = combo.tk.call("ttk::combobox::PopdownWindow", combo)
        opened = combo.register(lambda: popup_opened(path))
        closed = combo.register(lambda: popup_closed(path))
        combo.tk.call("bind", path, "<Map>", opened)
        combo.tk.call("bind", path, "<Unmap>", closed)
        combo.tk.call("bind", path, "<Destroy>", closed)
        combo._popdown_guarded = True
    except tk.TclError:
        pass


class Tooltip:
    """Help text shown when the mouse rests on a widget (after a short delay, kept on screen). No tip is shown
    while a drop-down list is open, so it never covers the list."""
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
        if self.tip or not self.text or popup_open():
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
            _SHOWN_TIPS.append(self)
        except tk.TclError:
            self.tip = None

    def hide(self, _e=None):
        self._cancel()
        if self in _SHOWN_TIPS:
            _SHOWN_TIPS.remove(self)
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
            messagebox.showwarning(f"{_app_name()} - Output folder", NETWORK_REFUSED, parent=entry)
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

    def start(self, target: Callable, *args):
        """Run `target(*args)` on a helper thread; the queues are read often until it has finished, so what it
        sends shows at once (not up to a second later)."""
        import threading
        t = threading.Thread(target=target, args=args, daemon=True)
        self._threads = [x for x in getattr(self, "_threads", []) if x.is_alive()] + [t]
        t.start()
        self.kick()

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
        self._schedule(self.FAST_MS)           # before the handlers: one may open a message box (a nested event
        active = time.monotonic() < self._fast_until    # loop), and the other tabs must still be read meanwhile
        threads = getattr(self, "_threads", None)
        if threads:
            self._threads = [t for t in threads if t.is_alive()]
            active = active or bool(self._threads)            # a helper thread may still send something
        handling = self.__dict__.setdefault("_handling", set())
        for q, handle, busy in self.parts:
            had = not q.empty()
            if had and id(q) not in handling:  # a tab whose handler is showing a message box waits for it
                handling.add(id(q))
                try:
                    handle()
                except Exception:              # one tab's failure must not stop the others being read
                    import traceback
                    from rstools import errorlog
                    errorlog.write(traceback.format_exc())
                finally:
                    handling.discard(id(q))
            try:
                active = active or had or busy()
            except Exception:
                pass
        if not active and self._after is not None:     # nothing going on: look again less often
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self._after is None:
            self._schedule(self.SLOW_MS)

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
        self.started = time.monotonic()
        self.value = 0.0
        self._shown = -1.0
        self._msg: Optional[str] = None

    def begin(self, msg: str = ""):
        self.started = time.monotonic()
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

    def took(self) -> str:
        """'Finished in 3.2 s' (or '2 min 5 s'): how long the run took since begin()."""
        return "Finished in " + duration(time.monotonic() - self.started)

    def message(self, msg: str):
        if self.label is not None and msg and msg != self._msg:
            self._msg = msg
            self.label.configure(text=msg)

    def _draw(self, f: float):
        self._shown = f
        self.bar["value"] = f


def duration(seconds: float) -> str:
    """3.2 s, 45 s, 2 min 5 s."""
    if seconds < 10:
        return f"{seconds:.1f} s"
    if seconds < 60:
        return f"{seconds:.0f} s"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m} min {s} s"


LOG_HINT = "What the run does is shown here."


def log_box(parent, **grid) -> tk.Text:
    """The run log of a tab, gridded with `grid`: coloured by the theme (theme.style_text), a scroll bar only
    when the text is longer than the box, and a short hint while it is empty."""
    f = ttk.Frame(parent)
    f.grid(**grid)
    f.columnconfigure(0, weight=1)
    f.rowconfigure(0, weight=1)
    text = tk.Text(f, height=4, wrap="word", font="TkFixedFont", state="disabled", relief="flat", borderwidth=1,
                   highlightthickness=1)
    text.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(f, orient="vertical", command=text.yview)
    sb.grid(row=0, column=1, sticky="ns")

    def scrolled(lo, hi):
        (sb.grid_remove if float(lo) <= 0.0 and float(hi) >= 1.0 else sb.grid)()
        sb.set(lo, hi)
    text.configure(yscrollcommand=scrolled)
    text.configure(state="normal")
    text.insert("end", LOG_HINT, "hint")
    text.configure(state="disabled")
    return text


def debounce(widget, name: str, ms: int, fn: Callable[[], None]):
    """Run fn() once, `ms` after the last of a burst of calls (e.g. each key typed in a box)."""
    jobs = widget.__dict__.setdefault("_debounce_jobs", {})
    if jobs.get(name):
        try:
            widget.after_cancel(jobs[name])
        except tk.TclError:
            pass

    def run():
        jobs[name] = None
        fn()
    jobs[name] = widget.after(ms, run)


DAY_PICKS = (("All", lambda d: True), ("Weekdays", lambda d: d < 5), ("Weekend", lambda d: d >= 5),
             ("None", lambda d: False))


def day_buttons(parent, pick: Callable[[Callable[[int], bool]], None], **grid) -> List[ttk.Button]:
    """The All / Weekdays / Weekend / None buttons next to day tick boxes, in a frame gridded with `grid`;
    each calls `pick(test)` with a test of a day number (0 = Monday)."""
    f = ttk.Frame(parent)
    f.grid(**grid)
    out = []
    for i, (text, test) in enumerate(DAY_PICKS):
        b = ttk.Button(f, text=text, width=len(text) + 2, command=partial(pick, test))
        b.grid(row=0, column=i, padx=(0, 4))
        out.append(b)
    return out


READY = "Ready - press F5 to run"
STOPPED = "Stopped - nothing was saved"
FAILED = "Failed - see the message"


def _app_name() -> str:
    from .branding import APP_NAME
    return APP_NAME


class TaskBox(ttk.Combobox):
    """A read-only drop-down of tasks in groups: a heading line (`-- Group --`) for each group, its tasks indented
    below. Choosing a heading chooses that group's first task. The tasks are identified by their mode key, so
    saved settings do not depend on the wording or order of the list.

        box = TaskBox(parent, [("CWNs", [("compare", "Compare two CWNs"), ...]), ...])
        box.picked()    # the mode just chosen (a heading counts as its group's first task), else None
        box.show(mode)  # select that task's line
    """
    INDENT = "   "

    def __init__(self, master, groups, **kw):
        self.groups = [(g, list(tasks)) for g, tasks in groups]
        self.lines: list = []                  # (text, mode or None for a heading, first mode of its group)
        for group, tasks in self.groups:
            if group:
                self.lines.append((f"── {group} ──", None, tasks[0][0]))
            for mode, label in tasks:
                self.lines.append((self.INDENT * bool(group) + label, mode, mode))
        kw.setdefault("state", "readonly")
        super().__init__(master, values=[t for t, _m, _f in self.lines], **kw)

    @property
    def tasks(self) -> list:
        """Every (mode, label), in list order."""
        return [(m, lab) for _g, tasks in self.groups for m, lab in tasks]

    def label_of(self, mode: str) -> str:
        return next((t for t, m, _f in self.lines if m == mode), "")

    def picked(self):
        """The mode of the line chosen (the group's first task for a heading), else None."""
        i = self.current()
        if not 0 <= i < len(self.lines):
            return None
        return self.lines[i][2]

    def show(self, mode: str):
        text = self.label_of(mode)
        if text and self.get() != text:
            self.set(text)


class Placeholder:
    """Greyed text inside an empty entry box (e.g. the name an output gets when the box is left blank); it goes as
    soon as anything is typed. configure(text=...) changes it, so it can stand in for a hint label."""

    def __init__(self, entry, text: str = ""):
        self.entry, self.text = entry, text
        self.label = tk.Label(entry, text="", anchor="w", borderwidth=0, padx=0, pady=0, cursor="xterm")
        self.label.bind("<Button-1>", lambda _e: self.entry.focus_set())
        var = entry.cget("textvariable")
        if var:
            entry.tk.call("trace", "add", "variable", var, "write", entry.register(lambda *_a: self._update()))
        entry.bind("<FocusIn>", lambda _e: self._update(), add="+")
        entry.bind("<FocusOut>", lambda _e: self._update(), add="+")
        entry.bind("<Configure>", lambda _e: self._update(), add="+")
        self._update()

    def configure(self, text: str = "", **_kw):
        self.text = text
        self._update()

    config = configure

    def cget(self, key: str):
        return self.text if key == "text" else ""

    def _update(self):
        try:
            show = bool(self.text) and not self.entry.get()
            if not show:
                self.label.place_forget()
                return
            from rstools import theme
            p = theme.CURRENT or theme.PALETTES["light"]
            self.label.configure(text=self.text, background=p["field"], foreground=p.get("muted", "#777777"),
                                 font=self.entry.cget("font") or "TkDefaultFont")
            self.label.place(x=4, rely=0.5, anchor="w", relwidth=1.0, width=-8)
        except tk.TclError:
            pass
