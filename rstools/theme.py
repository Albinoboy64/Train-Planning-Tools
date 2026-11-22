"""Appearance of the Train Planning Tools window: theme, fonts and text size.

Every mode (light, dark, high contrast) uses ttk's 'clam' theme recoloured from one palette, so every tab,
box and button matches, with the same flat look on Windows and elsewhere.
'Follow Windows' reads the Windows app theme and high-contrast setting (no admin rights needed) and
keeps following them.

Fonts are the ones Windows itself uses: Segoe UI Variable (Windows 11) or Segoe UI for text, and
Cascadia Mono or Consolas for logs. Every widget uses a named font, so changing the text size resizes
the whole window at once.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from functools import lru_cache
import tkinter as tk
from typing import Dict, List, Literal, Sequence, Tuple
from tkinter import ttk

MODES = {"system": "Follow Windows", "light": "Light", "dark": "Dark", "contrast": "High contrast"}
TEXT_SIZES = {"small": ("Small", 0.9), "normal": ("Normal", 1.0), "large": ("Large", 1.2),
              "xlarge": ("Extra large", 1.45)}
BASE_PT = 9                     # Windows' standard UI text size

PALETTES = {
    "light": {"bg": "#F3F3F3", "panel": "#FDFDFD", "fg": "#1B1B1B", "muted": "#5A5A5A", "field": "#FFFFFF",
              "border": "#C4C4C4", "accent": "#0F6CBD", "accent_fg": "#FFFFFF", "hover": "#E5E5E5",
              "select": "#CCE4F7", "disabled": "#A0A0A0", "warn": "#9C5700", "error": "#C00000",
              "ok": "#0B6A0B", "tip": "#FFFFE1", "trough": "#E1E1E1",
              "d_changed": "#FFF2CC", "d_added": "#E2EFDA", "d_removed": "#F8D7DA", "d_issue": "#FCE4D6",
              "d_muted": "#8A8A8A"},
    "dark": {"bg": "#202020", "panel": "#2B2B2B", "fg": "#F0F0F0", "muted": "#ABABAB", "field": "#1A1A1A",
             "border": "#4A4A4A", "accent": "#4CC2FF", "accent_fg": "#000000", "hover": "#3A3A3A",
             "select": "#1F4E79", "disabled": "#6E6E6E", "warn": "#FFB454", "error": "#FF7B72",
             "ok": "#7EE787", "tip": "#2D2D30", "trough": "#2E2E2E",
             "d_changed": "#4D4119", "d_added": "#1F3D24", "d_removed": "#4A1F24", "d_issue": "#4D2E17",
             "d_muted": "#7E7E7E"},
    # Windows 'High Contrast Black' colours: white on black, yellow links and focus, cyan selection
    "contrast": {"bg": "#000000", "panel": "#000000", "fg": "#FFFFFF", "muted": "#FFFFFF", "field": "#000000",
                 "border": "#FFFFFF", "accent": "#FFFF00", "accent_fg": "#000000", "hover": "#1A1A1A",
                 "select": "#1AEBFF", "select_fg": "#000000", "disabled": "#3FF23F", "warn": "#FFFF00",
                 "error": "#FF8080", "ok": "#3FF23F", "tip": "#000000", "trough": "#000000",
                 "d_changed": "#4D4100", "d_added": "#003D14", "d_removed": "#5C0011", "d_issue": "#5C2E00",
                 "d_muted": "#C0C0C0"},
}
_UI_FAMILIES = ("Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Noto Sans", "DejaVu Sans")
_MONO_FAMILIES = ("Cascadia Mono", "Consolas", "Menlo", "Noto Sans Mono", "DejaVu Sans Mono")
FONT = "TkDefaultFont"          # family name, set by setup_fonts()
MONO = ""                       # fixed-width family, set by setup_fonts()


def _first_family(root, wanted) -> str:
    from tkinter import font
    have = {f.casefold(): f for f in font.families(root)}
    return next((have[w.casefold()] for w in wanted if w.casefold() in have), "")


def setup_fonts(root: tk.Tk, size: str = "normal"):
    """Point Tk's standard fonts at the Windows UI fonts, at the chosen text size, and create the
    app's named fonts (AppBold, AppHead, AppTitle, AppRun, AppLink, AppSmall). Named fonts update
    every widget that uses them, so this can be called again to change the size."""
    from tkinter import font
    global FONT, MONO
    scale = TEXT_SIZES.get(size, TEXT_SIZES["normal"])[1]
    pt = lambda n: max(7, round(n * scale))
    if FONT == "TkDefaultFont":
        FONT = _first_family(root, _UI_FAMILIES) or font.nametofont("TkDefaultFont", root).actual("family")
    if not MONO:
        MONO = _first_family(root, _MONO_FAMILIES) or font.nametofont("TkFixedFont", root).actual("family")
    mono = MONO
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont",
                 "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
        try:
            font.nametofont(name, root).configure(family=FONT, size=pt(BASE_PT), weight="normal")
        except tk.TclError:
            pass
    font.nametofont("TkFixedFont", root).configure(family=mono, size=pt(BASE_PT))
    named: Dict[str, Tuple[int, Literal["normal", "bold"], bool]] = {
        "AppBold": (BASE_PT, "bold", False), "AppHead": (14, "bold", False), "AppTitle": (15, "bold", False),
        "AppRun": (11, "bold", False), "AppLink": (BASE_PT, "bold", True), "AppSmall": (BASE_PT, "normal", False),
        "AppNotice": (10, "bold", False), "AppNoticeSmall": (8, "normal", False)}
    for name, (size_pt, weight, underline) in named.items():
        if name in font.names(root):
            font.nametofont(name, root).configure(family=FONT, size=pt(size_pt), weight=weight, underline=underline)
        else:                       # kept on the window: Tk deletes a named font when its Python object goes
            root.__dict__.setdefault("_app_fonts", []).append(
                font.Font(root, name=name, family=FONT, size=pt(size_pt), weight=weight, underline=underline))
    return scale


def row_height(root) -> int:
    """Table row height that fits the current text size."""
    from tkinter import font
    return font.nametofont("TkDefaultFont", root).metrics("linespace") + 6


# --------------------------------------------------------------------------- display scaling (DPI)
BASE_DPI = 96                  # Windows' 100% scaling


def enable_dpi_awareness():
    """Per-monitor DPI awareness (call before the first window): Windows then draws the app sharply at each
    display's own scaling instead of stretching a 100% image (blurry on a 4K laptop next to a 1440p monitor)."""
    if not sys.platform.startswith("win"):
        return
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # per monitor, v2
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)                               # per monitor
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def window_dpi(root) -> int:
    """The DPI of the display the window is on (96 at 100% scaling, 192 at 200%)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)             # GA_ROOT: the frame
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            if dpi:
                return int(dpi)
        except (AttributeError, OSError, tk.TclError):
            pass
    try:
        return int(round(root.winfo_fpixels("1i")))
    except tk.TclError:
        return BASE_DPI


@contextmanager
def freeze_redraw(root):
    """On Windows, hold the window's painting while it is rescaled and repaint it once at the end, so it does
    not redraw piece by piece. Does nothing elsewhere, and painting is always switched back on."""
    hwnd = 0
    if sys.platform.startswith("win"):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)            # GA_ROOT: the frame
            if hwnd:
                ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 0, 0)            # WM_SETREDRAW off
        except (AttributeError, OSError, tk.TclError):
            hwnd = 0
    try:
        yield
    finally:
        if hwnd:
            try:
                import ctypes
                ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 1, 0)            # WM_SETREDRAW on
                # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_FRAME | RDW_UPDATENOW
                ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x1 | 0x4 | 0x80 | 0x400 | 0x100)
            except (AttributeError, OSError):
                pass


def px(widget, n: float) -> int:
    """n pixels at 100% scaling and normal text size, as pixels on the window's display at the chosen text size
    (the main window keeps the factor as `ui_scale`)."""
    try:
        scale = getattr(widget.nametowidget("."), "ui_scale", 1.0)
    except (tk.TclError, KeyError, AttributeError):
        scale = 1.0
    return int(round(n * scale))


def work_area(root):
    """(left, top, right, bottom) of the work area (no taskbar) of the display the window is on, or None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
        mon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)                        # nearest display
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right, r.bottom
    except (AttributeError, OSError, tk.TclError):
        pass
    return None


def screen_area(widget):
    """(left, top, right, bottom) of the display a widget's window is on: its work area on Windows, else the
    screen."""
    try:
        area = work_area(widget.winfo_toplevel())
    except tk.TclError:
        area = None
    if area:
        return area
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight() - 40


def rescaled_size(width: int, height: int, ratio: float, area=None):
    """A window's size after moving to a display with `ratio` times the scaling (the same physical size),
    kept inside the display's work area when it is known."""
    w, h = int(round(width * ratio)), int(round(height * ratio))
    if area:
        w = min(w, area[2] - area[0])
        h = min(h, area[3] - area[1])
    return max(w, 200), max(h, 150)


def place_window(x: int, y: int, w: int, h: int, need_w: int, need_h: int, area, frame=(0, 0)):
    """Where the window goes after a scaling change: at least as big as its content needs (so nothing is cut
    off), never bigger than the display's work area, and moved back inside it if it now sticks out.
    (x, y) is the window frame's top-left, (w, h) its inside size, `frame` the extra width / height of the
    border and title bar, `area` the work area (left, top, right, bottom). Returns (x, y, w, h)."""
    left, top, right, bottom = area
    fw, fh = frame
    w = max(200, min(max(w, need_w), right - left - fw))
    h = max(150, min(max(h, need_h), bottom - top - fh))
    x = max(left, min(x, right - w - fw))
    y = max(top, min(y, bottom - h - fh))
    return x, y, w, h


def mouse_held() -> bool:
    """True while a mouse button is held down (Windows: the window is still being dragged)."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        state = ctypes.windll.user32.GetAsyncKeyState
        return bool(state(0x01) & 0x8000 or state(0x02) & 0x8000)          # left / right button
    except (AttributeError, OSError):
        return False


def windows_high_contrast() -> bool:
    """True when Windows high-contrast mode is on."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint), ("lpszDefaultScheme", ctypes.c_wchar_p)]
        hc = HIGHCONTRAST()
        hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
        if ctypes.windll.user32.SystemParametersInfoW(0x0042, hc.cbSize, ctypes.byref(hc), 0):   # SPI_GETHIGHCONTRAST
            return bool(hc.dwFlags & 1)                                                         # HCF_HIGHCONTRASTON
    except Exception:
        pass
    return False


def windows_prefers_dark() -> bool:
    """True when Windows is set to dark mode for apps."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def resolve(mode: str) -> str:
    """'light', 'dark' or 'contrast' for a theme setting."""
    if mode == "system":
        if windows_high_contrast():
            return "contrast"
        return "dark" if windows_prefers_dark() else "light"
    return mode if mode in PALETTES else "light"


def title_bar(root: tk.Tk, dark: bool):
    """Windows: a dark or light title bar to match the theme."""
    _dark_title_bar(root, dark)


def _dark_title_bar(root: tk.Tk, dark: bool):
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):            # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 11 / older Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


CURRENT: dict = {}             # the palette in use (for widgets made later, e.g. suggestion lists)


def apply(root: tk.Tk, mode: str, recolour: bool = True) -> dict:
    """Style the whole window for a theme setting; returns the palette in use. `recolour=False` (only the
    display's scaling changed): the ttk styles, sizes included, are set again, but plain tk widgets are not
    recoloured one by one, as their colours are the same."""
    name = resolve(mode)
    p = dict(PALETTES[name], name=name)
    p.setdefault("select_fg", p["fg"])
    CURRENT.clear()
    CURRENT.update(p)
    hc = name == "contrast"
    style = ttk.Style(root)
    if style.theme_use() != "clam":             # switching to the same theme again would restyle every widget
        style.theme_use("clam")

    style.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"], troughcolor=p["trough"],
                    selectbackground=p["select"], selectforeground=p["select_fg"], insertcolor=p["fg"],
                    focuscolor=p["accent"], font="TkDefaultFont")
    style.map(".", foreground=[("disabled", p["disabled"])])
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabelframe", background=p["bg"], bordercolor=p["border"], relief="groove")
    style.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"], font="AppBold")
    style.configure("TButton", background=p["panel"], foreground=p["fg"], bordercolor=p["border"],
                    lightcolor=p["panel"], darkcolor=p["panel"], padding=(8, 2), relief="solid",
                    borderwidth=2 if hc else 1)
    style.map("TButton", background=[("disabled", p["bg"]), ("pressed", p["select"]), ("active", p["hover"])],
              foreground=[("disabled", p["disabled"]), ("pressed", p["select_fg"])],
              bordercolor=[("focus", p["accent"]), ("active", p["accent"] if hc else p["border"])])
    for cls in ("TCheckbutton", "TRadiobutton"):
        style.configure(cls, background=p["bg"], foreground=p["fg"], indicatorbackground=p["field"],
                        indicatorforeground=p["accent"], upperbordercolor=p["border"],
                        lowerbordercolor=p["border"])
        style.map(cls, background=[("active", p["bg"])], foreground=[("disabled", p["disabled"])],
                  indicatorbackground=[("disabled", p["bg"]), ("selected", p["accent"]),
                                       ("pressed", p["select"])],
                  indicatorforeground=[("selected", p["accent_fg"])])
    style.configure("TEntry", fieldbackground=p["field"], foreground=p["fg"], bordercolor=p["border"],
                    padding=2)
    style.map("TEntry", bordercolor=[("focus", p["accent"])], fieldbackground=[("disabled", p["bg"])])
    style.configure("TCombobox", fieldbackground=p["field"], foreground=p["fg"], background=p["panel"],
                    arrowcolor=p["fg"], bordercolor=p["border"], padding=2)
    style.map("TCombobox", fieldbackground=[("readonly", p["field"]), ("disabled", p["bg"])],
              foreground=[("readonly", p["fg"]), ("disabled", p["disabled"])],
              selectbackground=[("readonly", p["field"])], selectforeground=[("readonly", p["fg"])],
              bordercolor=[("focus", p["accent"])])
    layouts = root.__dict__.setdefault("_layouts", set())
    if "Suggest.TCombobox" not in layouts:
        # a box with suggestions as you type (or a recent-files list): no drop-down arrow
        def no_arrow(layout):
            return [(el, dict(opts, children=no_arrow(opts["children"])) if "children" in opts else opts)
                    for el, opts in layout if not el.endswith("downarrow")]
        style.layout("Suggest.TCombobox", no_arrow(style.layout("TCombobox")))
        layouts.add("Suggest.TCombobox")
    style.configure("TNotebook", background=p["bg"], bordercolor=p["border"], tabmargins=(4, 4, 4, 0))
    style.configure("TNotebook.Tab", background=p["panel"], foreground=p["muted"], padding=(14, 5),
                    bordercolor=p["border"])
    style.map("TNotebook.Tab", background=[("selected", p["select"] if hc else p["bg"])],
              foreground=[("selected", p["select_fg"] if hc else p["fg"])],
              expand=[("selected", (0, 2, 0, 0))])
    style.configure("Horizontal.TProgressbar", background=p["accent"], troughcolor=p["trough"],
                    bordercolor=p["border"], lightcolor=p["accent"], darkcolor=p["accent"])
    style.configure("Vertical.TScrollbar", background=p["panel"], troughcolor=p["bg"], arrowcolor=p["fg"],
                    bordercolor=p["bg"])
    style.map("Vertical.TScrollbar", background=[("active", p["hover"])])

    # tables (Live View)
    style.configure("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"],
                    bordercolor=p["border"], rowheight=row_height(root), font="TkDefaultFont")
    style.map("Treeview", background=[("selected", p["select"])], foreground=[("selected", p["select_fg"])])
    style.configure("Treeview.Heading", background=p["panel"], foreground=p["fg"], bordercolor=p["border"],
                    relief="flat", font="AppBold")
    style.map("Treeview.Heading", background=[("active", p["hover"])])
    style.configure("Bar.TFrame", background=p["panel"])
    style.configure("Bar.TLabel", background=p["panel"], foreground=p["fg"], padding=(8, 3))
    style.configure("BarHot.TLabel", background=p["hover"] if name == "dark" else p["select"],
                    foreground=p["select_fg"] if hc else p["fg"], padding=(8, 3))
    style.configure("Head.TLabel", font="AppHead")
    style.configure("Title.TLabel", font="AppTitle")
    style.configure("Link.TLabel", foreground=p["accent"], font="AppLink")
    style.configure("Small.TLabel", foreground=p["muted"], font="AppSmall")
    style.configure("Caption.TLabel", foreground=p["muted"], font="AppSmall")
    style.configure("Warn.TLabel", foreground=p["warn"])
    style.configure("Bold.TLabel", font="AppBold")
    style.configure("Bold.TCheckbutton", font="AppBold")
    style.configure("Run.TButton", font="AppRun", padding=(14, 7))
    style.configure("Run.TButton", background=p["accent"], foreground=p["accent_fg"])
    style.map("Run.TButton", background=[("disabled", p["panel"]), ("pressed", p["select"]),
                                         ("active", p["accent"])],
              foreground=[("disabled", p["disabled"]), ("active", p["accent_fg"])])
    _sizes(root, style, p)

    # a section of a tab that is not the one chosen (e.g. Utilities while comparing CWNs): its title greyed
    style.configure("Off.TLabelframe", background=p["bg"], bordercolor=p["border"], relief="groove")
    style.configure("Off.TLabelframe.Label", foreground=p["muted"], background=p["bg"], font="AppBold")

    # plain tk widgets: drop-down lists, logs, tooltips
    root.option_add("*TCombobox*Listbox.background", p["field"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["select"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])
    root.configure(background=p["bg"])
    if recolour:
        _recolour(root, p)
        _dark_title_bar(root, name != "light")
    if hasattr(root, "_focus_shown"):
        focus_cues(root, root._focus_shown)
    return p


def apply_sizes(root: tk.Tk):
    """Only what depends on the display's scaling and the text size (a move to a display with other scaling):
    tick boxes, radio buttons, drop-down arrows, scrollbars and icons. Colours are left as they are."""
    _sizes(root, ttk.Style(root), CURRENT or dict(PALETTES["light"], name="light", select_fg=PALETTES["light"]["fg"]))


def _sizes(root, style: ttk.Style, p: dict):
    k = getattr(root, "ui_scale", 1.0)
    style.configure("Treeview", rowheight=row_height(root))
    style.configure("TCheckbutton", indicatorsize=round(10 * k), indicatormargin=(0, 0, round(4 * k), 0))
    style.configure("TRadiobutton", indicatorsize=round(10 * k), indicatormargin=(0, 0, round(4 * k), 0))
    try:
        _indicators(root, style, p, k)
    except tk.TclError:             # an old Tk without PNG images: the theme's own (fixed-width) marks
        pass
    style.configure("TCombobox", arrowsize=round(14 * k))
    style.configure("TScrollbar", arrowsize=round(14 * k), width=round(14 * k))
    style.configure("Vertical.TScrollbar", arrowsize=round(14 * k), width=round(14 * k))
    style.configure("Horizontal.TScrollbar", arrowsize=round(14 * k), width=round(14 * k))
    from rstools import icons
    icons.refresh(root, p)


# --------------------------------------------------------------------------- #
# tick boxes and radio buttons drawn for the display's scaling
# --------------------------------------------------------------------------- #
_SWAP = (("TCheckbutton", "Checkbutton.indicator", "TPT.Checkbutton.indicator"),
         ("TRadiobutton", "Radiobutton.indicator", "TPT.Radiobutton.indicator"))


def _png(w: int, h: int, px: List[Tuple[int, int, int, int]]) -> str:
    """An RGBA image as base64 PNG data (Tk 8.6 reads PNG, transparency included)."""
    import base64
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes(c for pix in px[y * w:(y + 1) * w] for c in pix) for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")


def _rgb(colour: str) -> Tuple[int, int, int]:
    c = colour.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@lru_cache(maxsize=256)
def indicator_image(kind: str, on: bool, size: int, gap: int, box: str, edge: str, mark: str) -> str:
    """A tick box ('check') or radio button ('radio') `size` pixels square, anti-aliased, with `gap`
    transparent pixels to its right (the space before the text): the theme's own marks have fixed-width
    lines, which look thin and faint on a high-scaling display. Off: `box` filled, `edge` outline; on:
    `box` filled with a `mark` tick or dot. Returned as PNG data."""
    import math
    s = float(size)
    c = s / 2
    half = s / 2 - 0.5
    bw = max(1.0, s / 13)                                   # outline width (1 px at 100%)
    rad = max(1.5, s * 0.16)                                # tick box corner rounding

    def cover(d: float) -> float:                           # signed distance -> pixel coverage
        return min(1.0, max(0.0, 0.5 - d))

    def shape(x: float, y: float, inset: float = 0.0) -> float:
        if kind == "radio":
            return math.hypot(x - c, y - c) - (half - inset)
        r = max(0.5, rad - inset)
        qx, qy = abs(x - c) - (half - inset - r), abs(y - c) - (half - inset - r)
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r

    pts = [(0.25 * s, 0.53 * s), (0.43 * s, 0.71 * s), (0.76 * s, 0.32 * s)]
    stroke = max(1.6, s * 0.14)

    def tick(x: float, y: float) -> float:
        best = 1e9
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            vx, vy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy)))
            best = min(best, math.hypot(x - ax - t * vx, y - ay - t * vy))
        return best - stroke / 2

    layers = [(_rgb(edge), lambda x, y: cover(shape(x, y))), (_rgb(box), lambda x, y: cover(shape(x, y, bw)))]
    if on and kind == "check":
        layers.append((_rgb(mark), lambda x, y: cover(tick(x, y))))
    elif on:
        dot = max(1.5, s * 0.2)
        layers.append((_rgb(mark), lambda x, y: cover(math.hypot(x - c, y - c) - dot)))
    w = size + gap
    px: List[Tuple[int, int, int, int]] = []
    for yi in range(size):
        for xi in range(w):
            x, y = xi + 0.5, yi + 0.5
            r = g = b = a = 0.0                             # premultiplied, painted bottom to top
            if xi < size:
                for (lr, lg, lb), cov in layers:
                    f = cov(x, y)
                    if f:
                        r, g, b, a = lr * f + r * (1 - f), lg * f + g * (1 - f), lb * f + b * (1 - f), f + a * (1 - f)
            px.append((round(r / a), round(g / a), round(b / a), round(a * 255)) if a else (0, 0, 0, 0))
    return _png(w, size, px)


def _swap_element(layout, old: str, new: str):
    out = []
    for name, opts in layout or []:
        opts = dict(opts)
        if "children" in opts:
            opts["children"] = _swap_element(opts["children"], old, new)
        out.append((new if name == old else name, opts))
    return out


def _indicator_size(k: float) -> Tuple[int, int]:
    return max(11, round(13 * k)), max(3, round(4 * k))


def _indicator_specs(p: dict):
    """(image name, kind, ticked, box colour, outline colour, mark colour) for each tick box / radio state."""
    on_box, edge = p["accent"], p["border"]
    return (("check", "check", False, p["field"], edge, ""),
            ("check_on", "check", True, on_box, on_box, p["accent_fg"]),
            ("check_off_dis", "check", False, p["bg"], p["disabled"], ""),
            ("check_on_dis", "check", True, p["disabled"], p["disabled"], p["bg"]),
            ("radio", "radio", False, p["field"], edge, ""),
            ("radio_on", "radio", True, on_box, on_box, p["accent_fg"]),
            ("radio_off_dis", "radio", False, p["bg"], p["disabled"], ""),
            ("radio_on_dis", "radio", True, p["disabled"], p["disabled"], p["bg"]))


def monitor_dpis() -> List[int]:
    """The scaling (DPI) of every display connected to this PC, on Windows (empty elsewhere or on error)."""
    if not sys.platform.startswith("win"):
        return []
    try:
        import ctypes
        from ctypes import wintypes
        found: List[int] = []
        proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                  wintypes.LPARAM)

        def each(hmon, _hdc, _rect, _data):
            x, y = ctypes.c_uint(), ctypes.c_uint()
            if ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(x), ctypes.byref(y)) == 0:   # effective
                found.append(int(x.value))
            return 1
        ctypes.windll.user32.EnumDisplayMonitors(None, None, proc(each), 0)
        return sorted(set(found))
    except (AttributeError, OSError, ValueError):
        return []


def prewarm(root, dpis: Sequence[int]):
    """Draw, ahead of time, the tick boxes, radio buttons and icons for displays with other scaling (e.g. a
    4K laptop next to a 1440p monitor), so moving the window there does not have to draw them."""
    from rstools import icons
    p = CURRENT or PALETTES["light"]
    text = getattr(root, "ui_scale", 1.0) / max(getattr(root, "dpi_scale", 1.0), 0.01)     # the text size factor
    for dpi in dpis:
        k = text * dpi / BASE_DPI
        size, gap = _indicator_size(k)
        for _name, kind, on, box, line, mark in _indicator_specs(p):
            indicator_image(kind, on, size, gap, box, line, mark or box)
        icons.prewarm(root, k, p)


def _indicators(root, style: ttk.Style, p: dict, k: float):
    """Tick boxes and radio buttons drawn at the display's scaling (a tick and a dot in proportion), in the
    theme's colours. The images are redrawn in place, so every tick box changes at once."""
    size, gap = _indicator_size(k)
    images = root.__dict__.setdefault("_indicator_images", {})
    key = (p["name"], size, gap)
    if root.__dict__.get("_indicator_key") != key:
        for name, kind, on, box, line, mark in _indicator_specs(p):
            img = images.get(name) or images.setdefault(name, tk.PhotoImage(master=root))
            img.configure(data=indicator_image(kind, on, size, gap, box, line, mark or box), format="png")
        root._indicator_key = key
    have = style.element_names()
    for cls, old, new in _SWAP:
        if new not in have:
            kind = "check" if cls == "TCheckbutton" else "radio"
            style.element_create(new, "image", images[kind],
                                 ("disabled", "selected", images[f"{kind}_on_dis"]),
                                 ("disabled", images[f"{kind}_off_dis"]), ("selected", images[f"{kind}_on"]),
                                 sticky="")
        style.layout(cls, _swap_element(style.layout(cls), old, new))
    saved = root.__dict__.get("_focus_layouts", {}).get(style.theme_use())
    if saved:                                   # the focus-outline switch restores these layouts
        for cls, old, new in _SWAP:
            if cls in saved:
                saved[cls] = _swap_element(saved[cls], old, new)


def style_text(widget: tk.Text, p: dict):
    widget.configure(background=p["field"], foreground=p["fg"], insertbackground=p["fg"],
                     selectbackground=p["select"], selectforeground=p["select_fg"],
                     highlightthickness=2 if p.get("name") == "contrast" else 1,
                     highlightbackground=p["border"], highlightcolor=p["accent"], relief="flat", borderwidth=0)
    widget.tag_configure("warn", foreground=p["warn"])
    widget.tag_configure("error", foreground=p["error"])
    widget.tag_configure("ok", foreground=p["ok"])


def apply_menu(menu, p: dict):
    """Colour a menu (and its sub-menus) built after the theme was applied."""
    _recolour(menu, p)


def _recolour(widget, p: dict):
    if isinstance(widget, tk.Text):
        style_text(widget, p)
    elif isinstance(widget, tk.Canvas):
        widget.configure(background=p["bg"])
    elif isinstance(widget, tk.Menu):
        widget.configure(background=p["panel"], foreground=p["fg"], activebackground=p["select"],
                         activeforeground=p.get("select_fg", p["fg"]), selectcolor=p["fg"],
                         disabledforeground=p["disabled"], relief="flat", borderwidth=1)
    for child in widget.winfo_children():
        _recolour(child, p)


# --------------------------------------------------------------------------- #
# keyboard focus cues, as Windows draws them
# --------------------------------------------------------------------------- #
_FOCUS_CLASSES = ("TNotebook.Tab", "TCheckbutton", "TRadiobutton", "TButton")


def _strip_focus(layout):
    """A ttk layout with every '*.focus' element (the dotted focus outline) replaced by what it contains."""
    out = []
    for name, opts in layout or []:
        opts = dict(opts)
        children = _strip_focus(opts.pop("children", []))
        if name.endswith(".focus"):
            out.extend(children)
        else:
            if children:
                opts["children"] = children
            out.append((name, opts))
    return out


def focus_cues(root, show: bool):
    """Windows only draws the focus outline on tabs, tick boxes and buttons once the keyboard is used
    (Tab), and hides it again after a mouse click. ttk always draws it, so the outline is removed from
    the layouts while the mouse is being used and put back for keyboard users."""
    style = ttk.Style(root)
    theme_now = style.theme_use()
    saved = root.__dict__.setdefault("_focus_layouts", {})
    if theme_now not in saved:                      # the theme's own layouts, kept to restore
        saved[theme_now] = {cls: style.layout(cls) for cls in _FOCUS_CLASSES}
    for cls, layout in saved[theme_now].items():
        style.layout(cls, layout if show else _strip_focus(layout))
    root._focus_shown = show


def watch_focus_cues(root):
    """Show focus outlines when a control is reached with the keyboard (Tk sends <<TraverseIn>> when Tab
    or Shift+Tab moves to a control), hide them on a mouse click. Tab itself is left alone, so keyboard
    navigation works exactly as before."""
    def show(_e=None):
        if not getattr(root, "_focus_shown", False):
            focus_cues(root, True)

    def hide(_e=None):
        if getattr(root, "_focus_shown", True):
            focus_cues(root, False)
    root.bind_all("<<TraverseIn>>", show, add="+")
    root.bind_all("<ButtonPress>", hide, add="+")
    focus_cues(root, False)


# --------------------------------------------------------------------------- compact layout (short screens)
COMPACT = {"on": False}
COMPACT_BELOW = 900          # screen height (logical pixels) below which the layout is compact


def tip(widget, caption: str = ""):
    """Mark a description or tip label: it is hidden in the compact layout (its text stays in the hover
    help), and stays hidden even when a tab shows it again after a mode change.

    With a `caption` the label shows only an info icon and the caption (e.g. 'Tips'); its full text appears
    when the mouse rests on it (or on a click), so long notes don't crowd the controls. Setting the label's
    text later (as each mode does) updates the hover text; an empty text hides the caption too."""
    widget._tip = True
    widget.bind("<Map>", _hide_if_compact, add="+")
    if caption:
        _caption(widget, caption)
    return collapse_empty(widget)


def collapse_empty(widget):
    """A note label that takes no room while it has nothing to show (an empty label is as tall as a line of
    text) and comes back when text is set. Hiding and showing it for a mode works as before."""
    if getattr(widget, "_collapses", False):
        return widget
    widget._collapses = True
    real = widget.configure

    def configure(cnf=None, **kw):
        if isinstance(cnf, dict):
            kw, cnf = {**cnf, **kw}, None
        out = real(cnf, **kw) if (cnf is not None or kw) else real()
        if "text" in kw or "image" in kw:
            _fit(widget)
        return out
    widget.configure = widget.config = configure        # this label only
    widget.bind("<Map>", lambda _e: _fit(widget), add="+")
    return widget


def _fit(widget):
    try:
        empty = not str(widget.cget("text")) and not str(widget.cget("image"))
        if empty and widget.winfo_manager() == "grid":
            widget.grid_remove()
            widget._collapsed = True
        elif not empty and getattr(widget, "_collapsed", False):
            widget._collapsed = False
            if not (COMPACT["on"] and getattr(widget, "_tip", False)):
                widget.grid()
    except tk.TclError:
        pass


def _caption(widget, caption: str):
    from rstools import icons
    from rstools.widgets import Tooltip
    hover = Tooltip(widget, "", delay=150)
    real = widget.configure

    def configure(cnf=None, **kw):
        if isinstance(cnf, dict):
            kw, cnf = {**cnf, **kw}, None
        if "text" in kw:
            hover.text = str(kw.pop("text") or "")
            kw["text"] = caption if hover.text else ""
            kw["image"] = icons.image(widget, "info", "accent", 0.9) if hover.text else ""
        return real(cnf, **kw) if (cnf is not None or kw) else real()
    full = str(widget.cget("text"))
    widget.configure = widget.config = configure        # this label only
    widget.configure(text=full, compound="left", cursor="question_arrow", style="Caption.TLabel")
    widget.bind("<Button-1>", lambda _e: hover.show(), add="+")
    widget.full_text = lambda: hover.text


def _hide_if_compact(event):
    if COMPACT["on"]:
        try:
            event.widget.after_idle(event.widget.grid_remove)
        except Exception:
            pass


def set_compact(root, on: bool):
    """Compact layout: description and tip labels hidden, tighter section frames. Set once at start-up."""
    COMPACT["on"] = bool(on)
    if not on:
        return
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            if getattr(w, "_tip", False):
                w.grid_remove()
            elif w.winfo_class() == "TLabelframe":
                w.configure(padding=(6, 3, 6, 4))
        except Exception:
            pass
