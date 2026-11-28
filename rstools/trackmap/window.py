"""The track map view window: a track diagram page with the units standing at a station or siding drawn on it, and a
time slider (drag it, step train by train, or play the day). Reading and matching are in rstools.trackmap.engine;
this only draws."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from rstools.branding import APP_NAME
from rstools.days import DAY_NAMES

TITLE = f"{APP_NAME} - Track map view"
COLOURS = {"running": "#5A5A6E", "siding": "#63BC46", "points": "#C72E1F", "platform": "#A6469A"}
UNIT = "#1E6EDC"
LONG = "#DC3C3C"
SPEEDS = {"1 min / s": 60, "5 min / s": 300, "15 min / s": 900}
_OPEN: dict = {}


def open_view(app) -> "TrackMapWindow":
    win = _OPEN.get("win")
    if win is not None:
        try:
            win.deiconify()
            win.lift()
            return win
        except tk.TclError:
            pass
    win = TrackMapWindow(app)
    _OPEN["win"] = win
    return win


class TrackMapWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(TITLE)
        self.geometry("1280x820")
        self.q: "queue.Queue" = queue.Queue()
        self.view = None
        self.t = 8 * 3600
        self.playing = False
        self.scale_k = 1.0
        self.items: dict = {}
        self._build()
        self._fill_maps()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll)

    # ------------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self, padding=(10, 8, 10, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Track map:").grid(row=0, column=0, sticky="w")
        self.map_var = tk.StringVar()
        self.map_box = ttk.Combobox(top, textvariable=self.map_var, state="readonly", width=40)
        self.map_box.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(top, text="Add track map PDF...", command=self._add_map).grid(row=0, column=2, padx=4)
        ttk.Label(top, text="Attune XML:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.xml_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.xml_var, width=60).grid(row=1, column=1, columnspan=2, sticky="we", padx=4,
                                                                 pady=(4, 0))
        ttk.Button(top, text="Browse...", command=self._browse_xml).grid(row=1, column=3, pady=(4, 0))
        ttk.Label(top, text="Station or siding:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.place_var = tk.StringVar(value="Brighton")
        ttk.Entry(top, textvariable=self.place_var, width=24).grid(row=2, column=1, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(top, text="Page:").grid(row=2, column=2, sticky="e", pady=(4, 0))
        self.page_var = tk.StringVar()
        self.page_box = ttk.Combobox(top, textvariable=self.page_var, state="readonly", width=30)
        self.page_box.grid(row=2, column=3, sticky="w", padx=4, pady=(4, 0))
        ttk.Button(top, text="Find pages", command=self._find_pages).grid(row=2, column=4, padx=4, pady=(4, 0))
        ttk.Label(top, text="Day:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.day_var = tk.StringVar(value="")
        ttk.Combobox(top, textvariable=self.day_var, values=["(busiest)"] + list(DAY_NAMES), state="readonly",
                     width=12).grid(row=3, column=1, sticky="w", padx=4, pady=(4, 0))
        self.show_btn = ttk.Button(top, text="Show", style="Run.TButton", command=self._show)
        self.show_btn.grid(row=3, column=3, sticky="w", padx=4, pady=(4, 0))
        self.status = ttk.Label(top, text="", style="Small.TLabel")
        self.status.grid(row=4, column=0, columnspan=5, sticky="w", pady=(4, 0))

        bar = ttk.Frame(self, padding=(10, 0, 10, 4))
        bar.pack(fill="x")
        self.time_lbl = ttk.Label(bar, text="08:00", font="AppHead", width=6)
        self.time_lbl.grid(row=0, column=0)
        ttk.Button(bar, text="<<", width=3, command=lambda: self._step(-1)).grid(row=0, column=1)
        self.play_btn = ttk.Button(bar, text="Play", width=6, command=self._toggle_play)
        self.play_btn.grid(row=0, column=2, padx=2)
        ttk.Button(bar, text=">>", width=3, command=lambda: self._step(1)).grid(row=0, column=3)
        self.speed_var = tk.StringVar(value="5 min / s")
        ttk.Combobox(bar, textvariable=self.speed_var, values=list(SPEEDS), state="readonly", width=10).grid(
            row=0, column=4, padx=6)
        self.slider = ttk.Scale(bar, from_=0, to=30 * 3600, orient="horizontal", command=self._slid)
        self.slider.grid(row=0, column=5, sticky="we", padx=6)
        bar.columnconfigure(5, weight=1)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas = tk.Canvas(body, background="white", highlightthickness=0)
        body.add(self.canvas, weight=4)
        side = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(side, weight=1)
        ttk.Label(side, text="Selected / not on this page", style="Bold.TLabel").pack(anchor="w")
        self.info = tk.Text(side, height=30, width=40, wrap="word", relief="flat", padx=6, pady=4)
        self.info.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._fit())
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        for key, step in (("<Left>", -1), ("<Right>", 1)):
            self.bind(key, lambda _e, s=step: self._step(s))
        self.bind("<space>", lambda _e: self._toggle_play())

    # ------------------------------------------------------------------ inputs
    def _fill_maps(self, pick: str = ""):
        from .pdfmap import stored_maps
        names = stored_maps()
        self.map_box.configure(values=names)
        if pick or (names and not self.map_var.get()):
            self.map_var.set(pick or names[0])

    def _add_map(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a track diagram PDF",
                                          filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
        if not path:
            return
        self.status.configure(text="Reading the track map (once; only its track layout is kept)...")

        def work():
            from .pdfmap import TrackMapError, import_map
            try:
                self.q.put(("map", import_map(os.path.normpath(path)), ""))
            except TrackMapError as exc:
                self.q.put(("map", "", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _browse_xml(self):
        path = filedialog.askopenfilename(parent=self, title="Choose the Attune XML",
                                          filetypes=[("Attune diagram XML", "*.xml"), ("All files", "*.*")])
        if path:
            self.xml_var.set(os.path.normpath(path))

    def _find_pages(self):
        name, place = self.map_var.get(), self.place_var.get().strip()
        if not name or not place:
            messagebox.showinfo(TITLE, "Choose a track map and type the station or siding.", parent=self)
            return

        def work():
            from .engine import pages_for
            from .pdfmap import TrackMapError
            try:
                pages = pages_for(name, place)
                self.q.put(("pages", [(p.index, f"{p.title or 'Page ' + str(p.index + 1)} - "
                                                f"{', '.join(p.headings[:1])}") for p in pages], ""))
            except TrackMapError as exc:
                self.q.put(("pages", [], str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _page_index(self) -> Optional[int]:
        text = self.page_var.get()
        return next((i for i, label in getattr(self, "_pages", []) if label == text), None)

    def _show(self):
        name, xml, place = self.map_var.get(), self.xml_var.get().strip(), self.place_var.get().strip()
        page = self._page_index()
        if not (name and xml and place and page is not None):
            messagebox.showinfo(TITLE, "Choose the track map, the Attune XML, the station or siding and its page "
                                       "(Find pages).", parent=self)
            return
        day = self.day_var.get()
        self.show_btn.state(["disabled"])
        self.status.configure(text="Reading the XML and placing the units...")

        def work():
            from .engine import build, busiest_day
            from .pdfmap import TrackMapError
            try:
                d = DAY_NAMES.index(day) if day in DAY_NAMES else busiest_day(xml)
                self.q.put(("view", build(name, page, xml, place, d), ""))
            except TrackMapError as exc:
                self.q.put(("view", None, str(exc)))
            except Exception as exc:                 # shown, and in the error log
                from rstools import errorlog
                self.q.put(("view", None, errorlog.describe(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, value, error = self.q.get_nowait()
                if error:
                    self.status.configure(text="")
                    self.show_btn.state(["!disabled"])
                    messagebox.showwarning(TITLE, error, parent=self)
                elif kind == "map":
                    self.status.configure(text="Track map added.")
                    self._fill_maps(value)
                elif kind == "pages":
                    self._pages = value
                    self.page_box.configure(values=[label for _i, label in value])
                    if value:
                        self.page_box.set(value[0][1])
                    from rstools.naming import agree, plural
                    self.status.configure(text=f"{plural(len(value), 'page')} {agree(len(value), 'names', 'name')} "
                                               f"{self.place_var.get().strip()}." if value
                                          else "No page names that place.")
                elif kind == "view":
                    self.show_btn.state(["!disabled"])
                    self.view = value
                    self.status.configure(text=f"{DAY_NAMES[value.day]}: {len(value.stands)} unit stands at "
                                               f"{value.place}. " + " ".join(value.warnings))
                    self._draw_page()
                    self._draw_units()
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(100, self._poll)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ drawing
    def _fit(self):
        if self.view is None:
            return
        w, h = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        self.scale_k = min(w / self.view.page.width, h / self.view.page.height)
        self._draw_page()
        self._draw_units()

    def _xy(self, p):
        return p[0] * self.scale_k, p[1] * self.scale_k

    def _draw_page(self):
        c = self.canvas
        c.delete("all")
        if self.view is None:
            return
        page = self.view.page
        for tr in page.tracks:
            c.create_line(*[v for p in tr.pts for v in self._xy(p)], fill=COLOURS.get(tr.kind, "#777777"),
                          width=2 if tr.kind == "running" else 1)
        for lb in page.labels:
            if lb.size <= 9:
                x, y = self._xy((lb.x, lb.y))
                c.create_text(x, y, text=lb.text, fill="#8A8A8A", font=("Segoe UI", max(6, int(6 * self.scale_k))))

    def _draw_units(self):
        c = self.canvas
        c.delete("unit")
        if self.view is None:
            return
        from .engine import clock, describe
        sc = self.view.at(self.t)
        self.time_lbl.configure(text=clock(self.t))
        size = max(6, int(6 * self.scale_k))
        for u in sc.units:
            (ax, ay), (bx, by) = self._xy(u.a), self._xy(u.b)
            item = c.create_line(ax, ay, bx, by, fill=LONG if u.beyond else UNIT, width=max(4, int(4 * self.scale_k)),
                                 capstyle="butt", tags=("unit",))
            c.create_text(bx, by - 9 * self.scale_k, text=f"{u.stand.fleet} {u.stand.unit}", anchor="e",
                          font=("Segoe UI", size, "bold"), tags=("unit",))
            c.create_text(bx, by + 9 * self.scale_k, text=f"{u.stand.arrived_as or '-'} > {u.stand.leaves_as or '-'}",
                          anchor="e", fill="#1B3A8A", font=("Segoe UI", size), tags=("unit",))
            c.tag_bind(item, "<Button-1>", lambda _e, s=u.stand: self._details(describe(s, self.view.locations)))
        lines = [describe(s, self.view.locations) for group in sc.unplaced.values() for s in group]
        self._details("\n\n".join(["Not on this page:"] + lines) if lines else "")
        if sc.warnings:
            self.status.configure(text=" ".join(sc.warnings))

    def _details(self, text: str):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("end", text)
        self.info.configure(state="disabled")

    def _wheel(self, event):
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        self.scale_k *= factor
        self._draw_page()
        self._draw_units()

    # ------------------------------------------------------------------ time
    def _slid(self, value):
        self.t = int(float(value))
        self._draw_units()

    def _set(self, t: int):
        self.t = max(0, min(30 * 3600, t))
        self.slider.set(self.t)
        self._draw_units()

    def _step(self, direction: int):
        if self.view is None:
            return
        times = self.view.events()
        nxt = ([x for x in times if x > self.t][:1] if direction > 0 else [x for x in times if x < self.t][-1:])
        if nxt:
            self._set(nxt[0])

    def _toggle_play(self):
        self.playing = not self.playing
        self.play_btn.configure(text="Pause" if self.playing else "Play")
        if self.playing:
            self._tick()

    def _tick(self):
        if not self.playing:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        step = SPEEDS.get(self.speed_var.get(), 300) // 10       # ten pictures a second
        if self.t + step > 30 * 3600:
            self._toggle_play()
            return
        self._set(self.t + step)
        self.after(100, self._tick)

    def _close(self):
        self.playing = False
        _OPEN.pop("win", None)
        self.destroy()
