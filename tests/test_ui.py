"""The window's wording, order and responsiveness (3.37 review): plurals, message boxes over the window, the
Live View run row and list, task tips and the shared run rows (synthetic data only)."""
import ast
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rstools.naming import file_label, plural  # noqa: E402

GUI_FILES = ["cwn_compare/gui.py", "rstools/statspack/gui_tab.py", "rstools/timetable/gui_tab.py",
             "rstools/live/gui_tab.py", "rstools/update_dialog.py", "rstools/rules_dialog.py", "rstools/widgets.py",
             "rstools/live/popout.py"]


def test_plurals_and_box_names_read_as_words():
    assert plural(1, "train") == "1 train" and plural(2, "train") == "2 trains" and plural(0, "train") == "0 trains"
    assert plural(1, "clash") == "1 clash" and plural(3, "clash") == "3 clashes"
    assert plural(1200, "difference") == "1,200 differences"
    assert plural(2, "more file", "more files") == "2 more files"
    assert file_label("Original TRENT VL29 print(s):") == "original TRENT VL29 print"
    assert file_label("Section 4 PDF(s) (optional):") == "Section 4 PDF"
    assert file_label("Train print(s) - reference:") == "train print"


def test_every_message_box_opens_over_the_window():
    """A message box without parent= can open behind the Live View window or on another display."""
    missing = []
    for rel in GUI_FILES:
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef) or not fn.args.args or fn.args.args[0].arg != "self":
                continue
            for n in ast.walk(fn):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "messagebox"
                        and not any(k.arg == "parent" for k in n.keywords)):
                    missing.append(f"{rel}:{n.lineno}")
    assert not missing, missing


def test_every_help_tip_belongs_to_a_control_that_exists():
    """Tips are found by a control's text: a renamed control leaves its tip behind, never shown."""
    pytest.importorskip("tkinter")
    from rstools.help_text import TIPS
    texts = []                                           # every string in the window code (joined parts too)
    for rel in GUI_FILES + ["rstools/live/adapters.py", "rstools/statspack/engine.py",
                            "rstools/timetable/engine.py", "rstools/theme.py"]:
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        texts += [" ".join(n.value.split()) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    source = "\n".join(texts)
    stale = [k for k in TIPS if k not in source and k.rstrip(":") not in source]
    assert not stale, stale


@pytest.fixture
def app(monkeypatch, tmp_path):
    pytest.importorskip("tkinter")
    import tkinter as tk
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        import cwn_compare.gui as g
        window = g.App()
    except tk.TclError:
        pytest.skip("no display")
    yield window
    window.destroy()


def test_each_tab_has_the_same_run_row(app):
    """Run | progress bar (stretching) | Stop on one row, the status line under it, on every tab."""
    for tab in (app, app.stats_tab, app.tt_tab, app.live_tab):
        run, stop, bar = tab.run_btn.grid_info(), tab.stop_btn.grid_info(), (tab.prog if hasattr(tab, "prog")
                                                                             else None)
        assert run["row"] == stop["row"] and int(stop["column"]) > int(run["column"])
        if bar is not None and bar.master is tab.stop_btn.master:
            info = bar.grid_info()
            assert (info["row"], info["column"]) != (stop["row"], stop["column"])     # never on top of Stop
            assert int(info["column"]) < int(stop["column"]) and "e" in info["sticky"] and "w" in info["sticky"]
        assert tab.status.grid_info()["row"] != run["row"] or tab.status.master is not tab.run_btn.master


def test_the_task_list_shows_the_tip_of_the_task_chosen(app):
    from rstools.help_text import _TextTip, lookup
    box = app.stats_tab.task_box
    box.show("seats")
    tip = _TextTip(box, box)
    tip.show()
    try:
        assert tip.text == lookup(box.get()) and "headcode group" in tip.text
    finally:
        tip.hide()


def test_choosing_the_same_live_task_keeps_the_results(app):
    from rstools.live.model import CHANGED, LiveItem, LiveResult, LiveRow
    live = app.live_tab
    live.mode_box.show("cwn")
    live._task_picked()
    res = LiveResult("t", ["Field", "a", "b"], [LiveItem("1", "g", "1A01", CHANGED, "Time changed",
                                                         [LiveRow(["Time", "0700", "0705"], CHANGED)])])
    live._loaded("cwn", res, False, {}, None)
    assert live.listv.get_children() == ("1",)
    live.mode_box.show("cwn")
    live._task_picked()                                  # the same task again: nothing is cleared
    assert live.result is not None and live.listv.get_children() == ("1",)
    live.mode_box.show("tprs")
    live._task_picked()                                  # another task: cleared
    assert live.result is None and not live.listv.get_children()


def test_a_long_live_list_fills_in_batches(app):
    """20,000 trains: the first rows (and the selection) at once, the rest between events."""
    from rstools.live import gui_tab
    from rstools.live.model import CHANGED, LiveItem, LiveResult, LiveRow
    live = app.live_tab
    live.mode_box.show("cwn")
    live._task_picked()
    items = [LiveItem(str(i), "g", f"1A{i:05d}", CHANGED, "Time changed", [LiveRow(["Time", "0700", "0705"], CHANGED)])
             for i in range(20000)]
    t0 = time.perf_counter()
    live._loaded("cwn", LiveResult("t", ["Field", "a", "b"], items), False, {}, None)
    first = time.perf_counter() - t0
    assert len(live.listv.get_children()) == gui_tab.LIST_BATCH and live.listv.selection() == ("0",)
    assert first < 5
    end = time.monotonic() + 30
    while len(live.listv.get_children()) < 20000 and time.monotonic() < end:
        app.update()
    assert len(live.listv.get_children()) == 20000 and live.listv.selection() == ("0",)


def test_the_live_stop_button_can_be_seen(app):
    live = app.live_tab
    app.notebook.select(3)
    app.update()
    assert live.stop_btn.winfo_ismapped() and live.prog.winfo_ismapped()
    sx, px = live.stop_btn.winfo_rootx(), live.prog.winfo_rootx()
    assert sx >= px + live.prog.winfo_width()                    # the bar ends before the button starts
