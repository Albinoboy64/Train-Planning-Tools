"""Small icons for buttons, tabs and help captions, drawn in code (no image files, no third-party artwork).

Each icon is a few shapes (outlines, dots, bars) rasterised with anti-aliasing at the display's scaling, in
a colour taken from the theme in use, and saved as PNG data for Tk. The images are kept per window and
redrawn in place when the theme or scaling changes, so every button that shows one changes at once.
"""
from __future__ import annotations

import math
from functools import lru_cache
import tkinter as tk
from typing import Callable, Dict, List, Sequence, Tuple

Point = Tuple[float, float]
Shape = Callable[[float, float], float]          # signed distance (in icon units, 0..1) to the shape's edge
BASE = 14                                        # icon size in pixels at 100% scaling and normal text size


# --------------------------------------------------------------------------- shapes (unit square, y down)
def _circle(cx: float, cy: float, r: float) -> Shape:
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def _ellipse(cx: float, cy: float, a: float, b: float) -> Shape:
    return lambda x, y: (math.hypot((x - cx) / a, (y - cy) / b) - 1) * min(a, b)


def _box(x0: float, y0: float, x1: float, y1: float, r: float = 0.0) -> Shape:
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2

    def d(x, y):
        qx, qy = abs(x - cx) - (hx - r), abs(y - cy) - (hy - r)
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
    return d


def _seg_dist(x: float, y: float, a: Point, b: Point) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / (vx * vx + vy * vy or 1e-9)))
    return math.hypot(x - a[0] - t * vx, y - a[1] - t * vy)


def _polygon(pts: Sequence[Point]) -> Shape:
    """Filled polygon (negative inside)."""
    edges = list(zip(pts, list(pts[1:]) + [pts[0]]))

    def d(x, y):
        dist = min(_seg_dist(x, y, a, b) for a, b in edges)
        inside = False
        for (ax, ay), (bx, by) in edges:
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
        return -dist if inside else dist
    return d


def _stroke(shape: Shape, width: float) -> Shape:
    """The outline of a filled shape, `width` wide, centred on its edge."""
    return lambda x, y: abs(shape(x, y)) - width / 2


def _line(pts: Sequence[Point], width: float) -> Shape:
    segs = list(zip(pts, pts[1:]))
    return lambda x, y: min(_seg_dist(x, y, a, b) for a, b in segs) - width / 2


def _union(*shapes: Shape) -> Shape:
    return lambda x, y: min(s(x, y) for s in shapes)


W = 0.085                                        # outline width (about 1.4 px at 16 px)

SHAPES: Dict[str, Shape] = {
    # help: a ring with an 'i'
    "info": _union(_stroke(_circle(0.5, 0.5, 0.40), W), _circle(0.5, 0.31, 0.065),
                   _line([(0.5, 0.46), (0.5, 0.72)], 0.11)),
    "run": _polygon([(0.30, 0.18), (0.30, 0.82), (0.82, 0.50)]),
    "folder": _stroke(_polygon([(0.08, 0.24), (0.38, 0.24), (0.47, 0.34), (0.92, 0.34), (0.92, 0.80),
                                (0.08, 0.80)]), W),
    "file": _union(_stroke(_polygon([(0.20, 0.08), (0.58, 0.08), (0.80, 0.30), (0.80, 0.92), (0.20, 0.92)]), W),
                   _line([(0.58, 0.08), (0.58, 0.30), (0.80, 0.30)], W),
                   _line([(0.34, 0.55), (0.66, 0.55)], W), _line([(0.34, 0.72), (0.66, 0.72)], W)),
    "add": _union(_line([(0.5, 0.18), (0.5, 0.82)], 0.12), _line([(0.18, 0.5), (0.82, 0.5)], 0.12)),
    "stop": _box(0.24, 0.24, 0.76, 0.76, 0.06),
    "clear": _union(_line([(0.24, 0.24), (0.76, 0.76)], 0.11), _line([(0.76, 0.24), (0.24, 0.76)], 0.11)),
    # two arrows, one each way
    "swap": _union(_line([(0.14, 0.34), (0.80, 0.34)], W), _line([(0.64, 0.18), (0.82, 0.34), (0.64, 0.50)], W),
                   _line([(0.86, 0.66), (0.20, 0.66)], W), _line([(0.36, 0.50), (0.18, 0.66), (0.36, 0.82)], W)),
    # an arrow leaving a tray
    "export": _union(_line([(0.12, 0.56), (0.12, 0.88), (0.88, 0.88), (0.88, 0.56)], W),
                     _line([(0.5, 0.66), (0.5, 0.12)], W), _line([(0.30, 0.32), (0.5, 0.12), (0.70, 0.32)], W)),
    # a window with an arrow out of its corner
    "popout": _union(_line([(0.46, 0.14), (0.12, 0.14), (0.12, 0.88), (0.86, 0.88), (0.86, 0.54)], W),
                     _line([(0.44, 0.56), (0.88, 0.12)], W), _line([(0.60, 0.12), (0.88, 0.12), (0.88, 0.40)], W)),
    # tabs: a unit (carriage), a bar chart, a clock and an eye
    "stock": _union(_stroke(_box(0.08, 0.22, 0.92, 0.72, 0.12), W), _box(0.20, 0.34, 0.40, 0.50, 0.03),
                    _box(0.60, 0.34, 0.80, 0.50, 0.03), _circle(0.30, 0.84, 0.075), _circle(0.70, 0.84, 0.075)),
    "stats": _union(_box(0.12, 0.52, 0.30, 0.88, 0.03), _box(0.41, 0.30, 0.59, 0.88, 0.03),
                    _box(0.70, 0.12, 0.88, 0.88, 0.03)),
    "timing": _union(_stroke(_circle(0.5, 0.5, 0.40), W), _line([(0.5, 0.26), (0.5, 0.5), (0.68, 0.62)], W)),
    "live": _union(_stroke(_ellipse(0.5, 0.5, 0.42, 0.26), W), _circle(0.5, 0.5, 0.12)),
}


# --------------------------------------------------------------------------- drawing
def _rgb(colour: str) -> Tuple[int, int, int]:
    c = colour.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@lru_cache(maxsize=512)
def draw(name: str, size: int, colour: str) -> str:
    """The icon `size` pixels square in `colour`, as PNG data (transparent background)."""
    from rstools.theme import _png
    shape = SHAPES[name]
    r, g, b = _rgb(colour)
    px: List[Tuple[int, int, int, int]] = []
    edge = 1.0 / size                           # one pixel, in icon units
    for yi in range(size):
        for xi in range(size):
            d = shape((xi + 0.5) / size, (yi + 0.5) / size) / edge          # distance in pixels
            a = min(1.0, max(0.0, 0.5 - d))
            px.append((r, g, b, round(a * 255)))
    return _png(size, size, px)


def _store(root) -> Dict[tuple, tk.PhotoImage]:
    return root.__dict__.setdefault("_drawn_icons", {})


def image(widget, name: str, role: str = "fg", scale: float = 1.0) -> tk.PhotoImage:
    """The window's icon `name` in the theme colour `role` (a palette key, e.g. 'fg', 'muted', 'accent_fg')."""
    from rstools import theme
    root = widget.nametowidget(".")
    store = _store(root)
    key = (name, role, scale)
    img = store.get(key)
    if img is None:
        img = store[key] = tk.PhotoImage(master=root)
        p = theme.CURRENT or theme.PALETTES["light"]
        img.configure(data=draw(name, _size(root, scale), p.get(role, p["fg"])), format="png")
    return img


def spec(widget, name: str, role: str = "fg", disabled: str = "disabled"):
    """An image option for a ttk widget: the icon, greyed when the widget is disabled."""
    return (image(widget, name, role), "disabled", image(widget, name, disabled))


def _size(root, scale: float, k: float = 0.0) -> int:
    return max(10, round(BASE * (k or getattr(root, "ui_scale", 1.0)) * scale))


def prewarm(root, k: float, p: dict):
    """Draw the window's icons for another scaling `k` ahead of time (kept in draw()'s cache)."""
    for (name, role, scale) in list(_store(root)):
        draw(name, _size(root, scale, k), p.get(role, p["fg"]))


def refresh(root, p: dict):
    """Redraw every icon of the window for the theme `p` and the window's scaling (only when either changed)."""
    store = _store(root)
    key = (p.get("name"), round(getattr(root, "ui_scale", 1.0), 3))
    if root.__dict__.get("_drawn_icons_key") == key:
        return
    root._drawn_icons_key = key
    for (name, role, scale), img in store.items():
        try:
            img.configure(data=draw(name, _size(root, scale), p.get(role, p["fg"])), format="png")
        except tk.TclError:
            pass


# --------------------------------------------------------------------------- buttons
def _for_button(widget) -> Tuple[str, str]:
    """(icon, colour role) a button should show from its text and style ('' for none)."""
    if str(widget.cget("style")) == "Run.TButton":
        return "run", "accent_fg"
    text = str(widget.cget("text")).strip().lower()
    if text.startswith("browse") or text.startswith("open folder"):
        return "folder", "fg"
    if text.startswith("open"):
        return "file", "fg"
    if text.startswith("add"):
        return "add", "fg"
    for start, name in (("stop", "stop"), ("clear", "clear"), ("swap", "swap"), ("export", "export"),
                        ("pop out", "popout")):
        if text.startswith(start):
            return name, "fg"
    return "", ""


def _decorate(event):
    w = event.widget
    try:
        text = str(w.cget("text"))
        if getattr(w, "_icon_text", None) == text:
            return
        w._icon_text = text
        name, role = _for_button(w)
        w.configure(image=spec(w, name, role) if name else "", compound="left" if name else "none")
    except (tk.TclError, AttributeError):
        pass


def refresh_button(button):
    """Pick the icon again after a button's text changed (e.g. 'Browse...' to 'Add...')."""
    _decorate(type("E", (), {"widget": button})())


def decorate_all(root):
    """Give every Run, Browse, Open and Add button already built its icon now, before the window is shown, so
    no button grows (and the layout shifts) the first time its tab is opened."""
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if w.winfo_class() == "TButton":
            _decorate(type("E", (), {"widget": w})())


def watch_buttons(root):
    """Give Run, Browse, Open and Add buttons their icon: those built already at once, any made later (dialogs)
    the first time each is shown."""
    decorate_all(root)
    root.bind_class("TButton", "<Map>", _decorate, add="+")
