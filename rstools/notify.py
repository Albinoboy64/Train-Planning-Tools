"""Tell the user a run has finished when the app is in the background: the taskbar button flashes and a
small notice appears in the bottom-right corner of the screen (click it to bring the app to the front).
Nothing is shown while the app is in front - the usual message box is enough then."""
from __future__ import annotations

import sys
import tkinter as tk

SHOW_MS = 9000


def app_in_front(root: tk.Tk) -> bool:
    try:
        return root.focus_displayof() is not None and root.state() != "iconic"
    except (tk.TclError, KeyError):
        return False


def flash_taskbar(root: tk.Tk):
    """Flash the app's taskbar button until it is brought to the front (Windows)."""
    if not sys.platform.startswith("win"):
        try:
            root.bell()
        except tk.TclError:
            pass
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FlashInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        info = FlashInfo(ctypes.sizeof(FlashInfo), hwnd, 0x3 | 0xC, 0, 0)   # FLASHW_ALL | FLASHW_TIMERNOFG
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def notify(root: tk.Tk, title: str, message: str, ok: bool = True):
    """Flash the taskbar and show a corner notice, if the app is not in front."""
    if app_in_front(root):
        return
    flash_taskbar(root)
    try:
        p = getattr(root, "palette", None) or {"panel": "#FDFDFD", "fg": "#1B1B1B", "border": "#C4C4C4",
                                               "ok": "#0B6A0B", "error": "#C00000", "muted": "#5A5A5A"}
        win = tk.Toplevel(root)
        win.wm_overrideredirect(True)
        try:
            win.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(win, background=p["panel"], highlightthickness=1, highlightbackground=p["border"],
                         padx=14, pady=10, cursor="hand2")
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=("✔ " if ok else "✖ ") + title, background=p["panel"],
                 foreground=p["ok"] if ok else p["error"], font="AppNotice", anchor="w").pack(fill="x")
        tk.Label(frame, text=message, background=p["panel"], foreground=p["fg"], wraplength=320, justify="left",
                 anchor="w").pack(fill="x", pady=(2, 0))
        tk.Label(frame, text="Click to open the app", background=p["panel"], foreground=p["muted"],
                 font="AppNoticeSmall", anchor="w").pack(fill="x", pady=(4, 0))
        win.update_idletasks()
        w, h = max(win.winfo_reqwidth(), 300), win.winfo_reqheight()
        x, y = win.winfo_screenwidth() - w - 16, win.winfo_screenheight() - h - 60
        win.wm_geometry(f"{w}x{h}+{x}+{y}")

        def bring_front(_e=None):
            close()
            try:
                root.deiconify()
                root.lift()
                root.focus_force()
            except tk.TclError:
                pass

        def close(_e=None):
            try:
                win.destroy()
            except tk.TclError:
                pass
        for widget in [frame] + list(frame.winfo_children()):
            widget.bind("<Button-1>", bring_front)
        win.after(SHOW_MS, close)
    except tk.TclError:
        pass
