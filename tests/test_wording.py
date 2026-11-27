"""3.38.8: clearing remembered inputs, the built-in chart's wording, counts with the right plural, and suggestion
lists that close when the task or tab changes. Synthetic data only."""
import gzip
import json
import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_clear_options_empties_remembered_inputs_and_keeps_defaults():
    from cwn_compare.options import Options
    from rstools import remembered
    o = Options()
    o.original, o.updated, o.output_dir, o.book_station = "a.xlsx", "b.xlsx", "C:\\out", "Brighton"
    o.berth_leave_out, o.berth_add = {"SNGX": ["Barnham"]}, {"TLGN": ["Bedford"]}
    o.recent = {"cwn": ["x.xlsx"]}
    o.berth_files = {"berth_make": ["p.xml"]}
    o.colour, o.theme, o.text_size, o.book_group, o.output_type = "00FF00", "dark", "large", "SNGX", "acwn"
    o.saved = {"k": {"tab": 0, "state": {}}}
    o.mode, o.categories["PLATFORM"]["cwn"] = "batch", False
    remembered.clear_options(o)
    fresh = Options()
    for name in remembered.OPTION_FIELDS:
        assert getattr(o, name) == getattr(fresh, name), name
    assert (o.colour, o.theme, o.text_size, o.book_group, o.output_type, o.mode) == \
        ("00FF00", "dark", "large", "SNGX", "acwn", "batch")
    assert o.saved and o.categories["PLATFORM"]["cwn"] is False
    assert "No input or output files are deleted" in remembered.question()


def test_clear_fields_are_real_options():
    from cwn_compare.options import Options
    from rstools import remembered
    assert all(hasattr(Options(), n) for n in remembered.OPTION_FIELDS)


def _layout_text():
    from rstools.berthing import layout
    with gzip.open(layout.DEFAULT_FILE, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    out = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            out.append(o)
    walk(data)
    return out


def test_built_in_layout_wording():
    """The hand-typed text of the built-in chart is spelt correctly: 'outberth' as one word, no 'ATTATCH',
    'FUTHER' or '1s a', no double spaces."""
    text = _layout_text()
    joined = "\n".join(text)
    assert "outberth" in joined.lower()
    for bad in ("Out Berth", "out berth", "ATTATCH", "Attatch", "FUTHER", "1s a ", "indicated coupled", "en-route",
                "Walk Way", "377'S", "dual Voltage"):
        assert bad not in joined, bad
    assert not [t for t in text if "  " in t]


def test_built_in_sheets_still_find_their_berths():
    """Renamed sheets (St Leonards, RDH Up Tonb Sdg) still match the berth list."""
    from rstools.berthing import layout, mapping
    locations = mapping.load()
    lay = layout.load_default()
    found = {s.name: sum(1 for b in s.blocks if locations.berth(s.name, b.label)) for s in lay.sheets
             if isinstance(s, layout.GridSheet)}
    assert found["St Leonards"] > 0 and found["RDH Up Tonb Sdg"] > 0


def test_plural_and_agree():
    from rstools.naming import agree, plural
    assert f"{plural(1, 'unit')} {agree(1, 'does', 'do')}" == "1 unit does"
    assert f"{plural(3, 'unit')} {agree(3, 'does', 'do')}" == "3 units do"
    assert plural(2, "headcode mismatch") == "2 headcode mismatches"


def test_no_count_with_s_in_brackets_followed_by_a_verb():
    """Output text never says '1 unit(s) do': counts are written with the right singular or plural."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    verbs = r"(?:do|does|have|has|are|is|were|was|go|goes|need|needs|berth|end|start|name|point|form|differ|belong)"
    pattern = re.compile(r"\{[^{}]+\} (?:[A-Za-z-]+ )*[A-Za-z-]+\(s\)[^\"{]* " + verbs + r"\b")
    bad = []
    for folder in ("rstools", "cwn_compare"):
        for dirpath, _dirs, files in os.walk(os.path.join(root, folder)):
            for f in files:
                if f.endswith(".py") and not f.startswith("gui"):
                    with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                        for n, line in enumerate(fh, 1):
                            if pattern.search(line):
                                bad.append(f"{f}:{n}")
    assert not bad, bad


def test_suggestion_lists_close_on_task_tab_and_hide():
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from rstools import autocomplete, widgets
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        frame = ttk.Frame(root)
        frame.pack()
        entry = ttk.Entry(frame)
        entry.pack()
        s = autocomplete.Suggest(entry, lambda: ["Brighton", "Bedford", "Bognor Regis"])
        root.update()
        s.show(["Brighton", "Bedford"])
        root.update()
        assert s.shown
        widgets.close_popups()                       # a task or tab change, Load/Save, the window moving
        root.update()
        assert not s.shown
        s.show(["Brighton"])
        root.update()
        entry.pack_forget()                          # its row hidden by a tick box
        root.update()
        assert not s.shown
    finally:
        root.destroy()


def test_tip_not_shown_for_a_hidden_control():
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from rstools.widgets import Tooltip
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        b = ttk.Button(root, text="x")
        tip = Tooltip(b, "help")
        root.update()
        tip.show()
        assert tip.tip is None                       # never mapped: no tip
    finally:
        root.destroy()


def test_app_clear_remembered_inputs(monkeypatch):
    tk = pytest.importorskip("tkinter")
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            pytest.skip("no display")
        try:
            app.orig.set("a.xlsx")
            app.out_dir.set(d)
            app.book_vars["station"].set("Brighton")
            app.colour.set("00FF00")
            app.opts.recent = {"cwn": ["a.xlsx"]}
            app.stats_tab.seat_station.set("Brighton")
            app.stats_tab.out_dir.set(d)
            app.tt_tab.vars["a"].set("p.pdf")
            assert app.clear_remembered(ask=False)
            assert app.orig.get() == "" and app.out_dir.get() == "" and app.book_vars["station"].get() == ""
            assert app.colour.value == "00FF00" or app.colour.get() == "00FF00"
            assert app.opts.recent == {}
            assert app.stats_tab.seat_station.get() == "London Victoria" and app.stats_tab.out_dir.get() == ""
            assert app.tt_tab.vars["a"].get() == ""
        finally:
            app.destroy()
