"""Appearance of the Train Planning Tools window: theme, fonts and text size.

Light mode on Windows keeps the native 'vista' look. Dark and high-contrast modes (and light mode
elsewhere) use ttk's 'clam' theme recoloured from one palette, so every tab, box and button matches.
'Follow Windows' reads the Windows app theme and high-contrast setting (no admin rights needed) and
keeps following them.

Fonts are the ones Windows itself uses: Segoe UI Variable (Windows 11) or Segoe UI for text, and
Cascadia Mono or Consolas for logs. Every widget uses a named font, so changing the text size resizes
the whole window at once.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
import tkinter as tk
from typing import Dict, Literal, Tuple
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
    native = name == "light" and sys.platform.startswith("win") and "vista" in style.theme_names()
    wanted = "vista" if native else "clam"
    if style.theme_use() != wanted:             # switching to the same theme again would restyle every widget
        style.theme_use(wanted)

    if not native:
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
    style.configure("Warn.TLabel", foreground=p["warn"])
    style.configure("Bold.TLabel", font="AppBold")
    style.configure("Bold.TCheckbutton", font="AppBold")
    style.configure("Run.TButton", font="AppRun", padding=(14, 7))
    if not native:
        style.configure("Run.TButton", background=p["accent"], foreground=p["accent_fg"])
        style.map("Run.TButton", background=[("disabled", p["panel"]), ("pressed", p["select"]),
                                             ("active", p["accent"])],
                  foreground=[("disabled", p["disabled"]), ("active", p["accent_fg"])])
    # tick boxes, radio buttons, drop-down arrows and scrollbars sized for the display's scaling and text size
    k = getattr(root, "ui_scale", 1.0)
    style.configure("TCheckbutton", indicatorsize=round(10 * k), indicatormargin=(0, 0, round(4 * k), 0))
    style.configure("TRadiobutton", indicatorsize=round(10 * k), indicatormargin=(0, 0, round(4 * k), 0))
    style.configure("TCombobox", arrowsize=round(14 * k))
    style.configure("TScrollbar", arrowsize=round(14 * k), width=round(14 * k))
    style.configure("Vertical.TScrollbar", arrowsize=round(14 * k), width=round(14 * k))
    style.configure("Horizontal.TScrollbar", arrowsize=round(14 * k), width=round(14 * k))

    # a section of a tab that is not the one chosen (e.g. Utilities while comparing CWNs): its title greyed
    style.configure("Off.TLabelframe", **({} if native else dict(background=p["bg"], bordercolor=p["border"],
                                                                  relief="groove")))
    style.configure("Off.TLabelframe.Label", foreground=p["muted"],
                    **({} if native else dict(background=p["bg"], font="AppBold")))

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


def tip(widget):
    """Mark a description or tip label: it is hidden in the compact layout (its text stays in the hover
    help), and stays hidden even when a tab shows it again after a mode change."""
    widget._tip = True
    widget.bind("<Map>", _hide_if_compact, add="+")
    return widget


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
