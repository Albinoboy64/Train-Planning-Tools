"""Tests for the shared helpers: parallel ZIP writer, updater logic, and default names."""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rstools import naming, updater  # noqa: E402
from rstools.zipw import write_zip  # noqa: E402


def test_zip_round_trip():
    parts = [(f"xl/worksheets/sheet{i}.xml", (f"<row r='{i}'/>" * 20000).encode()) for i in range(1, 6)]
    parts.append(("[Content_Types].xml", b"<Types/>"))
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "t.xlsx")
        write_zip(path, parts)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert [(name, archive.read(name)) for name in archive.namelist()] == parts
        assert not os.path.exists(path + ".tmp")


def test_versions_and_token():
    assert updater.is_newer("v2.1.5", "2.1.4")
    assert not updater.is_newer("v2.1.4", "2.1.4")
    assert updater.is_newer("v2.1.0", "2.01")
    assert not updater.is_newer("2.00", "2.1.4")
    assert updater.unprotect(updater.protect("secret-token")) == "secret-token"
    assert updater.unprotect("garbage") == "" and updater.protect("") == ""


def test_names():
    assert naming.short_label("C:/x/DEC26 CWN Proof 2 (1).xlsx") == "DEC26 Proof 2"
    assert naming.vs("Brighton v3", "Brighton v4") == "Brighton v3 vs v4"
    assert naming.vs("DEC26 Proof 1", "DEC26 Proof 2") == "DEC26 Proof 1 vs Proof 2"
    assert naming.timetable_of(["14/12/2026", "13/12/2026", "19/05/2027"]) == "DEC26"
    assert naming.compare_name("19-11-2026 P1 vs P2.xlsx", "P3.xlsx").endswith(" P2 vs P3")
    assert len(naming.clip("x" * 500)) == naming.MAX_NAME


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("ok", _name)


def test_batch_pairing_and_run():
    import tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_compare as t
    from cwn_compare.batch import pair_files, run_batch
    from cwn_compare.options import Options
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "orig"), os.path.join(d, "upd")
    os.makedirs(a)
    os.makedirs(b)
    for n in ("BTN CWN Proof 1", "VIC 14-12-2026", "Gatwick"):
        t.make(os.path.join(a, n + ".xlsx"), t.BTN_ORIG, t.VIC_ORIG)
    btn, vic = t._upd_rows()
    for n in ("BTN CWN Proof 2", "VIC 21-12-2026", "Eastbourne", "~$BTN CWN Proof 2"):
        t.make(os.path.join(b, n + ".xlsx"), btn, vic)
    pairs, left, right = pair_files(a, b)
    assert [(os.path.basename(x), os.path.basename(y)) for x, y in pairs] == [
        ("BTN CWN Proof 1.xlsx", "BTN CWN Proof 2.xlsx"), ("VIC 14-12-2026.xlsx", "VIC 21-12-2026.xlsx")]
    assert [os.path.basename(x) for x in left] == ["Gatwick.xlsx"]
    assert [os.path.basename(x) for x in right] == ["Eastbourne.xlsx"]       # Excel's ~$ lock file ignored
    seen = []
    results = run_batch(pairs, Options(output_dir=d), lambda *a: seen.append(a))
    assert len(results) == 2 and all(r.get("changes") for r in results) and len(seen) == 2


def test_settings_keep_app_wide_values():
    """Options saved by a CWN run must keep the app-wide settings (token, update check, saved comparisons)."""
    import pytest
    pytest.importorskip("tkinter")
    from cwn_compare.gui import APP_WIDE
    from cwn_compare.options import Options
    assert {"github_token", "check_updates", "saved", "notify_done", "theme", "recent"} <= set(APP_WIDE)
    assert all(hasattr(Options(), k) for k in APP_WIDE)


def test_help_text_lookup():
    import pytest
    pytest.importorskip("tkinter")
    from rstools.help_text import lookup
    # help that adds something is kept: formats, examples, what blank means, what is copied
    assert "never overwritten" in lookup("Output name:") and "10-15" in lookup("Platforms (optional):")
    assert "48 hours" in lookup("Fuel check (171s)") and lookup("Other depots")
    # no pop-ups on the menu bar, and none that only repeat the control's own words
    for redundant in ("Options", "Save/Load", "Help", "Browse...", "Clear", "Swap files", "Create stats pack",
                      "Open report", "All days", "Weekdays", "Mon", "MO", "377/4", "SNGX (BI, SU, SL)",
                      "Original Attune XML:", "Changed rows only"):
        assert lookup(redundant) is None, redundant
    assert lookup("nothing like this") is None


def test_output_paths_fit_and_never_overwrite():
    import tempfile
    from rstools import fsutil
    d = tempfile.mkdtemp()
    deep = os.path.join(d, *["Long Term Planning Team folder"] * 4)
    os.makedirs(deep)
    stem = "20-11-2026 SNGX SX Dec 26 Proof 3 vs Proof 5"
    tails = (".xlsx", " - Change Report.xlsx")
    room = fsutil.EXCEL_MAX_PATH - len(os.path.abspath(deep)) - 1 - len(tails[1]) - 4
    fitted = fsutil.fit_stem(deep, stem, tails)
    if room >= fsutil.MIN_STEM:                       # shortened to fit, at a word break
        assert len(fitted) <= room and stem.startswith(fitted)
    else:                                             # too deep to help: the full name is kept
        assert fitted == stem
    open(os.path.join(deep, fitted + ".xlsx"), "w").close()
    assert fsutil.unique_stem(deep, stem, tails) == fitted + " (2)"
    very_deep = os.path.join(d, "x" * 200)
    assert fsutil.fit_stem(very_deep, stem, tails) == stem                 # never cut to a useless name
    assert fsutil.excel_warning([os.path.join(very_deep, stem + ".xlsx")])
    assert not fsutil.excel_warning([os.path.join(d, "short.xlsx")])
    assert os.path.basename(fsutil.temp_path(os.path.join(deep, stem + " - Change Report.xlsx"))).startswith("~tpt")
    with fsutil.atomic_path(os.path.join(deep, "a.txt")) as tmp, open(tmp, "w") as fh:
        fh.write("ok")
    assert open(os.path.join(deep, "a.txt")).read() == "ok" and not [n for n in os.listdir(deep) if n.endswith(".tmp")]


def test_every_module_imports():
    """A broken import (e.g. a name moved between modules) fails here, not in the built app.
    Window modules are imported only where tkinter is available."""
    import importlib
    import importlib.util
    import pkgutil
    have_tk = importlib.util.find_spec("tkinter") is not None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for pkg in ("cwn_compare", "rstools"):
        for mod in pkgutil.walk_packages([os.path.join(root, pkg)], prefix=pkg + "."):
            name = mod.name
            if not have_tk and (name.endswith(("gui", "gui_tab", "theme", "widgets", "icons", "help_text", "notify",
                                               "update_dialog", "autocomplete", "rules_dialog"))):
                continue
            importlib.import_module(name)


def test_logo_files_ship_and_icons_refresh_after_an_update(monkeypatch):
    """The logo is in every place it is shown (exe icon in all sizes, header and window PNGs), the build
    embeds it, and after an update Windows is told to refresh the icon - once per new exe."""
    import tempfile
    import pytest
    Image = pytest.importorskip("PIL.Image")          # installed for the tests in the Windows build
    from rstools import updater
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico = Image.open(os.path.join(root, "packaging", "TrainPlanningTools.ico"))
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])
    for name, size in (("logo.png", 64), ("logo_48.png", 48), ("logo_32.png", 32), ("logo_16.png", 16)):
        assert Image.open(os.path.join(root, "rstools", "assets", name)).size == (size, size)
    spec = open(os.path.join(root, "packaging", "TrainPlanningTools.spec"), encoding="utf-8").read()
    assert "icon=ICON" in spec and '(ICON, "packaging")' in spec
    d = tempfile.mkdtemp()
    exe = os.path.join(d, "TrainPlanningTools.exe")
    open(exe, "wb").write(b"v1")
    open(exe + ".old", "wb").write(b"v0")
    refreshed = []
    monkeypatch.setattr(updater, "running_exe", lambda: exe)
    monkeypatch.setattr(updater, "refresh_icons", lambda e=None: refreshed.append(e))
    stamp = os.path.join(d, "installed.txt")
    updater.after_start(stamp)
    assert refreshed == [exe] and not os.path.exists(exe + ".old")       # first start of this exe
    updater.after_start(stamp)
    assert refreshed == [exe]                                             # same exe: nothing to do
    open(exe, "wb").write(b"version 2")                                   # updated
    updater.after_start(stamp)
    assert refreshed == [exe, exe]


def test_outputs_never_contain_formulas_from_input_text():
    """A cell such as '=cmd|...' in an input file is written to outputs as text, never as a live formula."""
    import tempfile
    import zipfile
    import openpyxl
    from rstools.timetable.xlstyle import add_sheet, new_workbook
    from cwn_compare.xlsxfix import save_workbook
    p = os.path.join(tempfile.mkdtemp(), "x.xlsx")
    wb = new_workbook()
    add_sheet(wb, "S", ["A", "B"], [['=cmd|"/c calc"!A1', '=HYPERLINK("http://example.com","x")']], [10, 10])
    save_workbook(wb, p)
    assert b"<f>" not in zipfile.ZipFile(p).read("xl/worksheets/sheet1.xml")
    assert openpyxl.load_workbook(p).active["A2"].value == '=cmd|"/c calc"!A1'


def test_zip_bomb_is_refused(tmp_path):
    import zipfile
    from rstools.fsutil import UnsafeFileError, check_office_file
    from cwn_compare.loader import LoadError, load_any
    p = str(tmp_path / "bomb.xlsx")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * (600 * 1024 * 1024))   # 600 MB of nothing, ~0.6 MB packed
    import pytest
    with pytest.raises(UnsafeFileError):
        check_office_file(p)
    with pytest.raises(LoadError):
        load_any(p)


def test_xml_entity_attacks_are_refused():
    """The XML parser refuses 'billion laughs' entity expansion and never reads other files (XXE)."""
    import tempfile
    import xml.etree.ElementTree as ET
    import pytest
    lol = ('<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">' + "".join(
        f'<!ENTITY {chr(98 + i)} "' + ("&" + chr(97 + i) + ";") * 10 + '">' for i in range(9)) + ']><l>&j;</l>')
    with pytest.raises(ET.ParseError):
        ET.fromstring(lol)
    secret = os.path.join(tempfile.mkdtemp(), "secret.txt")
    with open(secret, "w") as fh:
        fh.write("TOPSECRET")
    with pytest.raises(ET.ParseError):
        ET.fromstring(f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file://{secret}">]><r>&x;</r>')


def test_updater_only_installs_verified_windows_programs(monkeypatch):
    """No checksum, a wrong checksum or a file that is not a Windows program: nothing is installed."""
    import hashlib
    import io
    import tempfile
    import pytest
    from rstools import updater
    good = b"MZ" + b"\0" * 100
    d = tempfile.mkdtemp()

    def fake_open(self, req, timeout=None):
        return io.BytesIO(payload)
    monkeypatch.setattr(updater.urllib.request.OpenerDirector, "open", fake_open)
    rel = lambda digest="", notes="": updater.Release("9.9.9", "v9.9.9", notes, "", "https://api", len(payload),
                                                       digest)
    payload = good
    dest = os.path.join(d, "new.exe")
    with pytest.raises(updater.UpdateError, match="no checksum"):
        updater.download(rel(), dest)
    with pytest.raises(updater.UpdateError, match="did not match"):
        updater.download(rel("sha256:" + "0" * 64), dest)
    assert updater.download(rel("sha256:" + hashlib.sha256(good).hexdigest()), dest) == dest
    os.remove(dest)
    note = f"SHA-256 `{hashlib.sha256(good).hexdigest().upper()}`"           # releases made before GitHub digests
    assert updater.download(rel(notes=note), dest) == dest
    payload = b"<html>not a program</html>"
    with pytest.raises(updater.UpdateError, match="not a Windows program"):
        updater.download(rel("sha256:" + hashlib.sha256(payload).hexdigest()), os.path.join(d, "bad.exe"))
    assert not os.path.exists(os.path.join(d, "bad.exe")) and not os.path.exists(os.path.join(d, "bad.exe.part"))
    assert updater._cmd_path(r"C:\Users\a%PATH%b\x.exe") == r"C:\Users\a%%PATH%%b\x.exe"
    with pytest.raises(updater.UpdateError):
        updater._cmd_path('C:\\a" & del x\\b.exe')


def test_typed_output_names_stay_in_the_chosen_folder():
    import tempfile
    from rstools.fsutil import unique_stem
    d = tempfile.mkdtemp()
    for name in (r"..\..\Windows\x", "../../etc/x", "a:b", "CON", "..."):
        stem = unique_stem(d, name)
        full = os.path.abspath(os.path.join(d, stem + ".xlsx"))
        assert os.path.dirname(full) == os.path.abspath(d), name


def test_control_characters_never_break_an_output():
    """A stray control character in an input (e.g. text from a PDF print) is dropped, so Excel, Word
    and PDF outputs are still written and open cleanly."""
    import tempfile
    import zipfile
    import xml.etree.ElementTree as ET
    from rstools.statspack.output import sink_for
    from rstools.statspack.units import Report
    from rstools.timetable.xlstyle import add_sheet, new_workbook
    from cwn_compare.xlsxfix import save_workbook
    d = tempfile.mkdtemp()
    nasty = ["ctrl\x01\x0bchar", "\x00null", "<b>&amp;", "line\nbreak"]
    wb = new_workbook()
    add_sheet(wb, "S", ["A"], [[v] for v in nasty], [10])
    save_workbook(wb, os.path.join(d, "a.xlsx"))
    for fmt in ("xlsx", "docx", "pdf"):
        sink = sink_for(fmt)
        sink.report(Report("T", "title\x02", ["A"], [[v] for v in nasty], ["body"] * len(nasty)))
        path = os.path.join(d, "b" + sink.ext)
        sink.save(path, "x")
        if fmt != "pdf":
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.endswith(".xml"):
                        ET.fromstring(z.read(name))


def test_updater_never_hangs_on_odd_replies_or_cut_downloads(monkeypatch):
    """Anything unexpected from GitHub becomes a readable UpdateError, and a half download is removed."""
    import http.client
    import io
    import json
    import tempfile
    import pytest
    from rstools import updater

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: Resp(json.dumps([1, 2]).encode()))
    with pytest.raises(updater.UpdateError):
        updater.latest_release()

    class Cut(Resp):
        def read(self, n=-1):
            raise http.client.IncompleteRead(b"x")

    class Opener:
        def open(self, *a, **k):
            return Cut(b"")
    monkeypatch.setattr(updater.urllib.request, "build_opener", lambda *a: Opener())
    rel = updater.Release(version="9.9.9", tag="v9.9.9", notes="", page="", asset_api="https://x", asset_size=10,
                          digest="sha256:" + "0" * 64)
    with tempfile.TemporaryDirectory() as d:
        dest = os.path.join(d, "new.exe")
        with pytest.raises(updater.UpdateError):
            updater.download(rel, dest)
        assert os.listdir(d) == []


def test_compact_layout_hides_tips_only():
    import pytest
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from rstools import theme
    try:
        root = tk.Tk()
    except tk.TclError:
        return                                          # no display
    try:
        frame = ttk.LabelFrame(root, text="1.", padding=8)
        frame.grid()
        tip = theme.tip(ttk.Label(frame, text="Tip: drag and drop..."))
        tip.grid(row=0, column=0)
        keep = ttk.Label(frame, text="Leave the name blank...")
        keep.grid(row=1, column=0)
        theme.set_compact(root, True)
        root.update()
        assert not tip.winfo_ismapped() and keep.winfo_ismapped()
        tip.grid(row=0, column=0)                        # a tab showing it again after a mode change
        root.update()
        root.update()
        assert not tip.winfo_ismapped()
    finally:
        theme.COMPACT["on"] = False
        root.destroy()


def test_third_party_notices_ship():
    """The licences of the bundled open-source software ship with the app (Help > Third-party software)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rstools", "assets",
                        "THIRD_PARTY_NOTICES.txt")
    text = open(path, encoding="utf-8").read()
    for name in ("openpyxl", "pyxlsb", "LGPL", "pypdf", "pypdfium2", "PDFium", "ReportLab", "tkinterdnd2"):
        assert name in text


def test_station_suggestions_open_above_a_box_at_the_bottom_of_the_screen():
    """The list of names opens below the box, or above it when there is no room below (the box near the
    bottom of the screen); closing the box stops any pending hide check."""
    import pytest
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from rstools import theme
    from rstools.autocomplete import Suggest
    names = [f"Station {i}" for i in range(20)]
    try:
        root = tk.Tk()
    except tk.TclError:
        return
    try:
        box = ttk.Entry(root)
        box.pack()
        s = Suggest(box, lambda: names)
        bottom = theme.screen_area(box)[3]
        for y, below in ((0, True), (bottom - 60, False)):
            root.geometry(f"+0+{y}")
            root.update()
            s.show(names)
            root.update()
            top = s.popup.winfo_rooty()
            if below:
                assert top >= box.winfo_rooty() + box.winfo_height() - 1
            else:
                assert top + s.popup.winfo_height() <= box.winfo_rooty() + 1
            s.hide()
        s._later_hide()
        assert s._hide_job is not None
        box.destroy()
        assert s._hide_job is None
    finally:
        root.destroy()


def test_station_suggestions_as_you_type():
    """Typing in a station box lists matching names below it (starts-with first); Down + Enter takes one,
    and anything can still be typed over the box."""
    import pytest
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from rstools.autocomplete import Suggest, matches
    names = ["Brighton", "Preston Park", "London Bridge", "London Victoria", "Hove", "Burgess Hill"]
    assert matches("lon", names) == ["London Bridge", "London Victoria"]
    assert matches("bri", names) == ["Brighton", "London Bridge"]         # a word starting with it comes next
    assert matches("ill", names) == ["Burgess Hill"]
    try:
        root = tk.Tk()
    except tk.TclError:
        return
    try:
        picked = []
        box = ttk.Combobox(root, values=names)
        box.pack()
        box.set("Hove")                                   # existing text can be typed over
        s = Suggest(box, lambda: names, picked.append)
        root.update()
        box.focus_force()
        box.delete(0, "end")
        box.insert(0, "lon")
        box.event_generate("<KeyRelease>", keysym="n")
        root.update()
        assert s.shown and list(s.box.get(0, "end")) == ["London Bridge", "London Victoria"]
        box.event_generate("<Down>")
        box.event_generate("<Down>")
        box.event_generate("<Return>")
        root.update()
        assert box.get() == "London Victoria" and picked == ["London Victoria"] and not s.shown
        box.delete(0, "end")
        box.insert(0, "Somewhere new")                    # a name not in the list is kept as typed
        box.event_generate("<KeyRelease>", keysym="w")
        root.update()
        assert box.get() == "Somewhere new" and not s.shown
    finally:
        root.destroy()


def test_service_groups_listed_without_an_xml():
    """Before an XML is chosen the capacity report lists the built-in GTR groups, SNGX and TLGN."""
    from rstools.statspack.seats import default_headcode_groups
    codes = [c for c, _d in default_headcode_groups()]
    assert len(codes) > 40 and {"1A", "1C", "1T", "2V", "9J", "9Y"} <= set(codes)


def test_display_scaling_maths():
    """Moving to a display with other scaling keeps the window's physical size, inside that display."""
    import pytest
    pytest.importorskip("tkinter")
    from rstools import theme
    assert theme.rescaled_size(1200, 800, 2.0) == (2400, 1600)
    assert theme.rescaled_size(1200, 800, 2.0, (0, 0, 3840, 2100)) == (2400, 1600)
    assert theme.rescaled_size(2400, 1600, 0.5, (2560, 0, 5120, 1400)) == (1200, 800)
    assert theme.rescaled_size(2400, 1600, 1.0, (0, 0, 1920, 1040)) == (1920, 1040)


def test_window_rescales_when_moved_to_a_display_with_other_scaling(monkeypatch):
    """The app redrawn for a 200% display: fonts, wrapped text, column room and the window double, and come
    back when it returns to the 100% display."""
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from tkinter import font
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        try:
            app.update()
            base_dpi = app.dpi
            # the window-move watcher asks the display for its scaling: it must see the faked display too, or
            # on a slow machine it fires mid-test and (correctly) switches back to the real display's scaling
            shown = {"dpi": base_dpi}
            monkeypatch.setattr(g.theme, "window_dpi", lambda root: shown["dpi"])
            monkeypatch.setattr(g.theme, "displays", lambda: [])        # (Windows: the real displays are not used)
            line = font.nametofont("TkDefaultFont", app).metrics("linespace")
            wrap = int(str(app.dnd_hint.cget("wraplength")))
            col = int(app.outer.columnconfigure(0)["minsize"])
            app.geometry("1200x800")
            app.update()
            shown["dpi"] = base_dpi * 2
            app.dpi_changed(base_dpi * 2)
            app.update()
            assert font.nametofont("TkDefaultFont", app).metrics("linespace") >= line * 1.7
            assert int(str(app.dnd_hint.cget("wraplength"))) == wrap * 2
            assert int(app.outer.columnconfigure(0)["minsize"]) == col * 2
            assert app.winfo_width() >= 2000 or app.winfo_width() >= app.winfo_screenwidth() - 50
            shown["dpi"] = base_dpi
            app.dpi_changed(base_dpi)
            app.update()
            assert font.nametofont("TkDefaultFont", app).metrics("linespace") == line
            assert int(str(app.dnd_hint.cget("wraplength"))) == wrap
            assert int(app.outer.columnconfigure(0)["minsize"]) == col
        finally:
            app._on_close()


def test_data_folder_beside_the_exe(monkeypatch, tmp_path):
    """The exe keeps its data beside itself; a new data folder starts with the settings from AppData."""
    from rstools import branding
    appdata, exe_dir = tmp_path / "appdata", tmp_path / "app"
    (appdata / branding.FOLDER / "rules").mkdir(parents=True)
    (appdata / branding.FOLDER / "settings.json").write_text('{"theme": "dark"}')
    (appdata / branding.FOLDER / "rules" / "s4.json.gz").write_bytes(b"x")
    exe_dir.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "TrainPlanningTools.exe"))
    monkeypatch.setattr(branding, "_chosen", {})
    path = branding.settings_dir()
    assert path == str(exe_dir / branding.PORTABLE_FOLDER)
    assert open(os.path.join(path, "settings.json")).read() == '{"theme": "dark"}'
    assert os.path.isfile(os.path.join(path, "rules", "s4.json.gz"))
    assert os.path.isfile(appdata / branding.FOLDER / "settings.json")        # the original is left alone
    assert not [n for n in os.listdir(path) if n.endswith(".tmp")]           # the write test leaves nothing


def test_data_folder_falls_back_when_the_exe_folder_is_read_only(monkeypatch, tmp_path):
    from rstools import branding
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ro" / "TrainPlanningTools.exe"))
    monkeypatch.setattr(branding, "_chosen", {})
    monkeypatch.setattr(branding, "_writable", lambda path: False)          # e.g. a shared, read-only folder
    assert branding.settings_dir() == str(appdata / branding.FOLDER)
    assert os.path.isdir(appdata / branding.FOLDER)
    assert not os.path.exists(tmp_path / "ro" / branding.PORTABLE_FOLDER)


def test_data_folder_from_source_is_appdata(monkeypatch, tmp_path):
    from rstools import branding
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert branding.settings_dir() == str(tmp_path / branding.FOLDER)


def test_error_messages(monkeypatch, tmp_path):
    """Files open in Excel and full disks get plain messages; anything else is logged for support."""
    import errno
    from rstools import errorlog
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    locked = errorlog.describe(PermissionError(13, "Permission denied", "C:\\out\\pack.xlsx"))
    assert "Close it in Excel" in locked and "pack.xlsx" in locked
    assert "disk is full" in errorlog.describe(OSError(errno.ENOSPC, "No space left on device"))
    try:
        raise KeyError("unexpected")
    except KeyError as exc:
        msg = errorlog.describe(exc)
    assert msg.startswith("Unexpected error") and errorlog.log_path() in msg
    assert "KeyError" in open(errorlog.log_path(), encoding="utf-8").read()


def test_help_menu_opens_the_error_log(monkeypatch):
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from rstools import errorlog
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        shown, opened = [], []
        monkeypatch.setattr(g.messagebox, "showinfo", lambda *a, **k: shown.append(a[1]))
        monkeypatch.setattr(g, "_open_path", lambda path: opened.append(path))
        try:
            app._open_error_log()
            assert "No errors have been recorded" in shown[0] and not opened
            errorlog.write('Traceback: test\nValueError: \'London Victoria 05.37\' in C:\\Users\\jsmith\\a b\\x.xlsx')
            app._open_error_log()
            win = app._error_log_win
            box = next(w for w in win.winfo_children() if isinstance(w, tk.Text))
            text = box.get("1.0", "end")
            assert "Traceback: test" in text and "jsmith" not in text and "London Victoria" not in text
            assert "<path>\\x.xlsx" in text and "'<text>'" in text
            ticks = [w for f in win.winfo_children() for w in f.winfo_children() if w.winfo_class() == "TCheckbutton"]
            assert len(ticks) == 3
            for t in ticks:
                t.invoke()                                  # untick: everything shown as logged
            text = box.get("1.0", "end")
            assert "jsmith" in text and "London Victoria" in text
            win.destroy()
            assert not opened
        finally:
            app._on_close()


def test_error_log_redaction(monkeypatch):
    """Paths, user and computer names, emails and quoted file text are hidden - each only when asked - and the app's
    own traceback lines are kept."""
    from rstools import errorlog as E
    monkeypatch.setenv("USERNAME", "jsmith")
    monkeypatch.setenv("COMPUTERNAME", "GTR-PC042")
    log = ("Traceback (most recent call last):\n"
           '  File "C:\\Users\\jsmith\\Desktop\\tpt app\\rstools\\stationbook.py", line 166, in read_plan\n'
           '    raise StationBookError(f"The XML \'{name}\' could not be read")\n'
           "ValueError: Cell 'London Victoria 05.37 1A01' in C:\\Users\\jsmith\\OneDrive\\Dec26 CWN.xlsx on "
           "GTR-PC042 for j.smith@example.com\n"
           "OSError: \\\\server\\share\\plans\\x y.xml and /home/jsmith/plans/a.xml and C:\\Plans\\\n"
           "PermissionError: [Errno 13] Permission denied: 'C:\\\\Users\\\\jsmith\\\\Downloads\\\\out.xlsx'\n")
    out = E.redact(log)
    assert out.splitlines() == [
        "Traceback (most recent call last):",
        '  File "<path>\\stationbook.py", line 166, in read_plan',
        '    raise StationBookError(f"The XML \'{name}\' could not be read")',          # source line kept
        "ValueError: Cell '<text>' in <path>\\Dec26 CWN.xlsx on <user> for <email>",
        "OSError: <path>\\x y.xml and <path>/a.xml and <folder>",
        "PermissionError: [Errno 13] Permission denied: '<path>\\out.xlsx'"]
    assert E.redact(log, paths=False, user=False, content=False) == log
    only_paths = E.redact(log, user=False, content=False)
    assert "jsmith" not in only_paths.split("ValueError")[1].split(" on ")[0] and "GTR-PC042" in only_paths
    assert "London Victoria" in only_paths and "j.smith@example.com" in only_paths
    only_user = E.redact(log, paths=False, content=False)
    assert "jsmith" not in only_user and "GTR-PC042" not in only_user and "OneDrive" in only_user
    only_content = E.redact(log, paths=False, user=False)
    assert "London Victoria" not in only_content and "jsmith" in only_content


def test_error_log_never_keeps_file_contents_and_export_never_overwrites(tmp_path, monkeypatch):
    from rstools import errorlog as E
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr("rstools.branding.settings_dir", lambda: str(tmp_path / "appdata"))
    xml = "<train id='1A01' " + "x" * 5000 + "/>"
    E.write(f"Traceback (most recent call last):\nParseError: {xml}")
    logged = E.read()
    assert "Traceback" in logged and "x" * (E.LINE_LIMIT + 1) not in logged and "characters left out" in logged
    out = tmp_path / "out"
    out.mkdir()
    import datetime
    existing = out / f"error log {datetime.date.today():%Y-%m-%d}.txt"
    existing.write_text("keep me")
    p1 = E.export("first", str(out))
    p2 = E.export("second", str(out))
    assert existing.read_text() == "keep me"
    assert len({str(existing), p1, p2}) == 3 and open(p1).read() == "first" and open(p2).read() == "second"
    assert sorted(os.listdir(out)) == sorted([existing.name, os.path.basename(p1), os.path.basename(p2)])  # no temp
    import pytest
    with pytest.raises(OSError, match="this PC only"):
        E.export("x", r"\\server\share")
    assert E.clear() and E.read() == "" and E.clear()


def test_batch_pairing_ignores_versions_and_dates_written_with_underscores(tmp_path):
    """Underscores are word characters to a regular expression, so 'BTN_CWN_v1.2' or '_14-12-2026' kept their
    version or date and never paired. GTR's 'D12' drafts and '260918_' date stamps are ignored too."""
    from cwn_compare.batch import _key, pair_files
    assert {_key(n) for n in ("BTN_CWN_v1.2.xlsx", "BTN_CWN_v2.0.xlsx", "BTN_CWN_V1_2.xlsx", "BTN_CWN_Proof_2.xlsx",
                              "BTN-CWN-Proof-4.xlsx", "BTN_CWN_14-12-2026.xlsx", "BTN_CWN_14_12_2026.xlsx",
                              "BTN_CWN_D12.xlsx", "BTN CWN Proof 3 (1).xlsx")} == {"btn"}
    assert _key("Line_2_CWN_Proof_1.xlsx") == "line 2"                 # a number that is part of the name stays
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    for day in ("SX", "SO", "Su"):
        (a / f"260918_-_GTRTLGN_Dec26_D12_Draft_CWN_-_{day}.xlsx").write_bytes(b"")
        (b / f"261002_-_GTRTLGN_Dec26_D13_Draft_CWN_-_{day}.xlsx").write_bytes(b"")
    pairs, left, right = pair_files(str(a), str(b))
    assert not left and not right
    assert sorted(os.path.basename(o)[-7:] + os.path.basename(u)[-7:] for o, u in pairs) == [
        "SO.xlsxSO.xlsx", "SX.xlsxSX.xlsx", "Su.xlsxSu.xlsx"]


def test_between_flag_is_checked_before_reading():
    """--between / --at / --direction mistakes stop the run at once with a plain message - never ignored."""
    import contextlib
    import io
    import TrainPlanningTools as cli
    base = ["--xml", "missing.xml", "--trent", "missing.docx"]
    for args, says in ((["--capacity-group", "1A", "--between", "07:00", "--at", "Brighton"], "two times"),
                       (["--capacity-group", "1A", "--between", "23:00-24:30", "--at", "Brighton"], "'24:30'"),
                       (["--between", "07:00-10:00", "--at", "Brighton"], "are for a capacity report"),
                       (["--capacity-group", "1A", "--at", "Brighton"], "go with --between"),
                       (["--capacity-group", "1A", "--between", "07:00-10:00"], "needs --at"),
                       (["--capacity-from", "Brighton", "--capacity-to", "Victoria", "--between", "07:00-10:00",
                         "--at", "Brighton"], "Leave out --at")):
        out, code = io.StringIO(), None
        with contextlib.redirect_stdout(out):
            try:
                cli.statspack_cli(base + args)
            except SystemExit as exc:
                code = exc.code
        assert code == 1 and says in out.getvalue(), (args, code, out.getvalue())


def test_window_times_stop_at_24_00():
    import pytest
    from rstools.statspack.seats import SeatsError, parse_time
    assert parse_time("07:00") == 7 * 3600 and parse_time("0700") == 7 * 3600 and parse_time("24:00") == 86400
    for bad in ("24:30", "24:59", "07:60", "7", ""):
        with pytest.raises(SeatsError):
            parse_time(bad)


def test_batch_key_keeps_numbers_that_are_not_versions_or_dates():
    from cwn_compare.batch import _key
    assert _key("BTN_CWN_v1_2.xlsx") == _key("BTN_CWN_v2_0.xlsx") == "btn"            # underscore versions
    assert _key("260918_-_GTRTLGN_Dec26_D12_Draft_CWN_-_SX.xlsx") == _key(
        "261002_-_GTRTLGN_Dec26_D13_Draft_CWN_-_SX.xlsx") != _key("261002_-_GTRTLGN_Dec26_D13_Draft_CWN_-_SO.xlsx")
    assert _key("Line 2 CWN Proof 1.xlsx") != _key("Line 3 CWN Proof 1.xlsx")
    assert _key("Unit 377001 CWN.xlsx") != _key("Unit 377002 CWN.xlsx")                 # not a date: kept
    assert _key("Diagram 20261399.xlsx") == "diagram 20261399"                           # month 13: not a date
    assert _key("Route 12 13 14 CWN.xlsx") == "route 12 13 14"
    assert _key("BTN v2 12 car.xlsx") == "btn 12 car"                                    # the version only
    for dated in ("BTN 20260918.xlsx", "BTN 260918.xlsx", "BTN 14 12 26.xlsx", "BTN_14_12_2026.xlsx",
                  "BTN 2026.12.14.xlsx", "BTN-14-12-2026.xlsx"):
        assert _key(dated) == "btn", dated


def _capacity_args(**kw):
    import argparse
    base = dict(seats_group="", seats_corridor="", seats_from="", seats_to="", between="", at="", direction=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_capacity_window_raises_instead_of_exiting():
    import pytest
    import TrainPlanningTools as cli
    from rstools.statspack.engine import StatsPackError
    with pytest.raises(StatsPackError, match="two times"):
        cli._capacity_window(_capacity_args(seats_group="1A", between="07:00", at="Brighton"))
    with pytest.raises(StatsPackError, match="not a time"):
        cli._capacity_window(_capacity_args(seats_group="1A", between="07:00-25:00", at="Brighton"))
    assert cli._capacity_window(_capacity_args(seats_group="1A", between="07:00-10:00", at="Brighton")) == (
        "Brighton", "07:00", "10:00")
    assert cli._capacity_window(_capacity_args(seats_group="1A")) is None


def test_every_between_at_direction_combination():
    """Each mix of capacity report, --between, --at and --direction: a plain message for every invalid one,
    given before any file is read; the valid ones get past the checks."""
    import contextlib
    import io
    import itertools
    import TrainPlanningTools as cli
    reports = {"none": [], "group": ["--capacity-group", "1A"], "corridor": ["--capacity-corridor", "BML"],
               "journey": ["--capacity-from", "Brighton", "--capacity-to", "Victoria"]}
    betweens = {"none": [], "ok": ["--between", "07:00-10:00"], "one": ["--between", "07:00"],
                "late": ["--between", "23:00-24:30"]}
    ats = {"none": [], "at": ["--at", "Brighton"]}
    directions = {"none": [], "both": ["--direction", "both"]}
    seen = 0
    for (rk, r), (bk, b), (ak, at), (dk, d) in itertools.product(reports.items(), betweens.items(), ats.items(),
                                                                 directions.items()):
        if rk == "none" and bk == ak == dk == "none":
            continue                                            # a stats pack: not a window question
        if rk == "none":
            expect = "are for a capacity report"
        elif bk == "none" and (ak != "none" or dk != "none"):
            expect = "go with --between"
        elif bk == "one":
            expect = "two times"
        elif bk == "late":
            expect = "'24:30' is not a time"
        elif bk == "ok" and rk == "journey" and ak == "at":
            expect = "Leave out --at"
        elif bk == "ok" and rk != "journey" and ak == "none":
            expect = "needs --at"
        else:
            expect = ""                                         # valid: fails later, on the missing XML
        out, code = io.StringIO(), None
        with contextlib.redirect_stdout(out):
            try:
                cli.statspack_cli(["--xml", "missing.xml", "--trent", "missing.docx"] + r + b + at + d)
            except SystemExit as exc:
                code = exc.code
        text = out.getvalue()
        assert code == 1, (rk, bk, ak, dk, text)
        if expect:
            assert expect in text, (rk, bk, ak, dk, text)
        else:
            assert "--between" not in text and "--at " not in text and "not a time" not in text, (rk, bk, ak, dk, text)
        seen += 1
    assert seen == 4 * 4 * 2 * 2 - 1


def test_rules_in_use_line(monkeypatch, tmp_path):
    import datetime
    from rstools import rules
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    text, stale = rules.in_use(datetime.date(2027, 1, 10))
    assert text == "Rules: TPR 2027 (v4) · Section 4: 2027 EAS v4 (built in)" and not stale     # built-in set
    monkeypatch.setattr(rules, "active_set_info", lambda: None)
    text, stale = rules.in_use(datetime.date(2027, 1, 10))
    assert "Section 4: none added" in text and stale
    monkeypatch.setattr(rules, "active_set_info", lambda: {"name": "2027 EAS v4", "to": "2027-12-11"})
    assert rules.in_use(datetime.date(2027, 1, 10)) == ("Rules: TPR 2027 (v4) · Section 4: 2027 EAS v4", False)
    assert rules.in_use(datetime.date(2028, 1, 10))[1]                       # both past their last date


def test_professional_layout_captions_icons_and_status_bar(monkeypatch):
    """Long notes show as a short caption with the full text on hover; an empty note takes no room;
    Run / Browse / Open buttons and the tabs carry drawn icons; the status bar shows the last result with
    links to its output (not after a failure)."""
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from rstools import theme
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        monkeypatch.setenv("TPT_COMPACT", "0")              # the full layout, whatever the screen height
        monkeypatch.setitem(theme.COMPACT, "on", False)
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        try:
            app.update()
            hint = app.dnd_hint
            assert str(hint.cget("text")) == "Tips" and "drag" in hint.full_text().lower()
            assert str(hint.cget("image"))                                  # the info icon
            hint.configure(text="")
            app.update()
            assert hint.winfo_manager() == "" and not str(hint.cget("text"))   # empty: no room taken
            hint.configure(text="Drop two CWNs here.")
            app.update()
            assert hint.winfo_manager() == "grid" and hint.full_text() == "Drop two CWNs here."
            assert app.prev_info.winfo_manager() == ""                       # blank in this mode
            assert str(app.run_btn.cget("image")) and str(app.open_cwn.cget("image"))
            assert all(str(app.notebook.tab(i, "image")) for i in range(4))
            out = os.path.join(d, "result.xlsx")
            open(out, "w").close()
            app.open_outputs([out])                         # a run finished (not opened: the box is unticked)
            app.notify_done("CWN comparison finished", "3 change(s) found.")
            app.update()
            assert "CWN comparison finished" in str(app.status_text.cget("text"))
            assert app.status_open.winfo_manager() == "grid" and app._status_paths == [out]
            app.notify_done("CWN comparison failed", "The file is locked.", False)
            app.update()
            assert "failed" in str(app.status_text.cget("text")) and app.status_open.winfo_manager() == ""
            theme.COMPACT["on"] = True                      # compact layout: captions stay hidden when set
            hint.configure(text="")
            app.update()
            hint.configure(text="Another tip.")
            app.update()
            assert hint.winfo_manager() == "" and hint.full_text() == "Another tip."
        finally:
            theme.COMPACT["on"] = False
            app._on_close()


def test_tick_boxes_and_radio_buttons_drawn_for_the_scaling(monkeypatch):
    """The drawn themes (dark, high contrast, light off Windows) draw tick boxes and radio buttons as images
    sized for the display: twice the scaling gives twice the size, and the focus-outline switch (mouse /
    keyboard) keeps them in the layout."""
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from tkinter import ttk
    from rstools import theme
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        try:
            root = tk.Tk()
        except tk.TclError:
            return                                          # no display
        try:
            style = ttk.Style(root)
            root.ui_scale = 1.0
            theme.apply(root, "dark")
            images = root._indicator_images
            small = (images["check"].width(), images["check"].height())
            assert "TPT.Checkbutton.indicator" in str(style.layout("TCheckbutton"))
            assert "TPT.Radiobutton.indicator" in str(style.layout("TRadiobutton"))
            for show in (True, False, True):
                theme.focus_cues(root, show)
                assert "TPT.Checkbutton.indicator" in str(style.layout("TCheckbutton"))
                assert "TPT.Radiobutton.indicator" in str(style.layout("TRadiobutton"))
            root.ui_scale = 2.0
            theme.apply(root, "dark", recolour=False)
            assert images["check"].height() == 2 * small[1] and images["radio_on"].height() == 2 * small[1]
            box = ttk.Checkbutton(root, text="x")
            box.pack()
            root.update()
            assert box.winfo_reqheight() >= 2 * small[1]
            theme.apply(root, "contrast")                 # recoloured in place: same images, new colours
            assert root._indicator_images["check"] is images["check"]
        finally:
            root.destroy()


def test_display_watcher_only_watches_the_main_window(monkeypatch):
    """Child widgets resizing never run the display watcher; a move within the same display schedules nothing;
    moving to a display with other scaling rescales once, soon after."""
    import time
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        seen, rescaled = [], []
        try:
            app.update()
            shown = {"dpi": app.dpi}
            monkeypatch.setattr(g.theme, "window_dpi", lambda root: shown["dpi"])
            monkeypatch.setattr(g.theme, "displays", lambda: [])        # (Windows: the real displays are not used)
            real_moved = app._moved
            app.bind_class("TPTMain", "<Configure>", lambda e: (seen.append(e.widget), real_moved(e)))
            monkeypatch.setattr(app, "dpi_changed", lambda dpi: rescaled.append(dpi))
            app.geometry("1300x850")
            app.update()
            assert seen and all(w is app for w in seen)          # only the main window's own events
            assert app._dpi_after is None and not rescaled       # same display: nothing to do
            shown["dpi"] = app.dpi * 2
            app.geometry("1310x850")
            app.update()
            assert app._dpi_after is not None
            end = time.time() + 2
            while not rescaled and time.time() < end:
                app.update()
                time.sleep(0.02)
            assert rescaled == [shown["dpi"]]
        finally:
            app._on_close()


def test_zip_part_compressed_as_it_is_made():
    """A Word document is compressed section by section (never held whole); the file is a valid zip with the
    same content as writing the text in one go."""
    import zipfile
    from rstools.zipw import Deflated, write_zip
    with tempfile.TemporaryDirectory() as d:
        text = "".join(f"<row n='{i}'>Ünïcødé text {i}</row>" for i in range(20000))
        part = Deflated()
        for i in range(0, len(text), 777):
            part.write(text[i:i + 777])
        write_zip(os.path.join(d, "a.zip"), [("doc.xml", part.close()), ("small.xml", b"<x/>")])
        with zipfile.ZipFile(os.path.join(d, "a.zip")) as z:
            assert z.testzip() is None
            assert z.read("doc.xml").decode("utf-8") == text and z.read("small.xml") == b"<x/>"


def test_rescale_reuses_drawn_images(monkeypatch):
    """Icons and tick boxes drawn for a display's scaling are kept, and can be drawn ahead of time for the other
    displays: moving to one (and back) draws nothing new. A scaling change only re-applies sizes, not colours."""
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from rstools import icons, theme
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        monkeypatch.setenv("TPT_COMPACT", "0")
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        try:
            app.update()
            assert theme.monitor_dpis() == [] or sys.platform.startswith("win")
            recoloured = []
            monkeypatch.setattr(theme, "_recolour", lambda *a: recoloured.append(a))
            theme.prewarm(app, [app.dpi * 2])
            drawn = (icons.draw.cache_info().misses, theme.indicator_image.cache_info().misses)
            base = app.dpi
            app.dpi_changed(base * 2)
            app.update()
            app.dpi_changed(base)
            app.update()
            assert (icons.draw.cache_info().misses, theme.indicator_image.cache_info().misses) == drawn
            assert not recoloured                            # sizes only
            assert app.run_btn.cget("image") and app._indicator_images["check"].height() >= 11
        finally:
            app._on_close()


def test_window_placed_on_screen_after_a_scaling_change():
    """After a move to a display with other scaling the window is at least as big as its content needs
    (nothing cut off), no bigger than the work area, and moved back inside it if it sticks out."""
    import pytest
    pytest.importorskip("tkinter")
    from rstools.theme import place_window
    area = (0, 0, 1920, 1040)
    assert place_window(100, 100, 1000, 700, 1200, 800, area) == (100, 100, 1200, 800)        # grown to fit
    assert place_window(100, 100, 1500, 900, 1200, 800, area) == (100, 100, 1500, 900)        # kept if bigger
    assert place_window(1500, 600, 1200, 800, 1200, 800, area, (16, 40)) == (704, 200, 1200, 800)  # moved in
    assert place_window(-300, -50, 3000, 2000, 2500, 1500, area, (16, 40)) == (0, 0, 1904, 1000)   # screen-sized
    left = (-1920, 0, 0, 1080)                                                                  # a display on the left
    assert place_window(-200, 100, 800, 600, 900, 700, left) == (-900, 100, 900, 700)


def test_rescale_waits_for_the_drag_to_end_then_fits_the_window(monkeypatch):
    """While the mouse button is held (the window still being dragged) the rescale waits; once let go it rescales
    in one step, and the window ends up fully on the screen and big enough for its content."""
    import time
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from rstools import theme
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        monkeypatch.setenv("TPT_COMPACT", "0")
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        try:
            app.update()
            shown = {"dpi": app.dpi, "held": True}
            monkeypatch.setattr(g.theme, "window_dpi", lambda root: shown["dpi"])
            monkeypatch.setattr(g.theme, "displays", lambda: [])        # (Windows: the real displays are not used)
            monkeypatch.setattr(g.theme, "mouse_held", lambda: shown["held"])
            area = theme.screen_area(app)
            app.geometry(f"1100x700+{area[2] - 1150}+{area[1] + 20}")      # near the right edge
            app.update()
            base = app.dpi
            shown["dpi"] = base * 2
            app._check_dpi()
            app.update()
            assert app.dpi == base and app._dpi_after is not None          # still dragging: waits
            shown["held"] = False
            end = time.time() + 2
            while app.dpi == base and time.time() < end:
                app.update()
                time.sleep(0.02)
            assert app.dpi == base * 2
            end = time.time() + 2                   # the final check runs once painting is back on
            while time.time() < end and not (area[0] <= app.winfo_x() and area[1] <= app.winfo_y()):
                app.update()
                time.sleep(0.02)
            app.update()
            need_w, need_h = app._needed_size()
            where = (f"window {app.winfo_x()},{app.winfo_y()} {app.winfo_width()}x{app.winfo_height()}, "
                     f"screen area {area}, needed {need_w}x{need_h}, {app.state()}")
            assert app.winfo_x() >= area[0] and app.winfo_x() + app.winfo_width() <= area[2] + 1, where
            assert app.winfo_y() >= area[1] and app.winfo_y() + app.winfo_height() <= area[3] + 1, where
            side = max(0, app.winfo_rootx() - app.winfo_x())               # window border (Windows: ~8-10 px)
            fw, fh = 2 * side, max(0, app.winfo_rooty() - app.winfo_y()) + side
            # big enough for its content, or filling the screen (within the border, whose size Windows reports
            # only roughly while the window is being moved)
            assert app.winfo_width() >= min(need_w, area[2] - area[0] - fw) - 24, where
            assert app.winfo_height() >= min(need_h, area[3] - area[1] - fh) - 60, where
        finally:
            app._on_close()


def test_window_partly_off_screen_is_moved_back(monkeypatch):
    import time
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    from rstools import theme
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        monkeypatch.setenv("TPT_COMPACT", "0")
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return                                          # no display
        try:
            area = theme.screen_area(app)
            w = min(1000, area[2] - area[0] - 40)
            app.geometry(f"{w}x600+{area[0] - 150}+{area[1] + 10}")        # sticking out past the left edge
            app.update()
            app._keep_on_screen()
            end = time.time() + 2
            while app.winfo_x() < area[0] and time.time() < end:
                app.update()
                time.sleep(0.02)
            assert app.winfo_x() >= area[0], (app.winfo_x(), area)
            assert app.winfo_x() + app.winfo_width() <= area[2] + 1
        finally:
            app._on_close()


# ------------------------------------------------------------------ 3.27: drops, local outputs, steady UI
class _Var:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


def test_drop_replaces_the_box_it_is_dropped_on():
    """A file dropped on a filled box replaces it; dropped elsewhere it fills an empty box first, else replaces
    the box it belongs in; two files for two boxes go in date order; files with no box are left over."""
    from rstools.dropping import Slot, route_drop
    d = tempfile.mkdtemp()
    old, new = os.path.join(d, "old.xlsx"), os.path.join(d, "new.xlsx")
    for i, p in enumerate((old, new)):
        open(p, "w").close()
        os.utime(p, (1000 + i, 1000 + i))
    xlsx = (lambda p: p.endswith(".xlsx"))
    a, b = _Var("a.xlsx"), _Var("b.xlsx")
    slots = [Slot(a, xlsx), Slot(b, xlsx, prefer=lambda p: True)]
    assert route_drop(["x.xlsx"], slots, slots[0]) == (1, []) and a.v == "x.xlsx" and b.v == "b.xlsx"
    assert route_drop(["y.xlsx"], slots) == (1, []) and b.v == "y.xlsx"              # its home box, replaced
    a.v = ""
    route_drop(["z.xlsx"], slots)
    assert a.v == "z.xlsx" and b.v == "y.xlsx"                                     # the empty box first
    route_drop([new, old], slots)
    assert (a.v, b.v) == (old, new)                                                # older file first
    placed, left = route_drop(["n.xml"], slots)
    assert placed == 0 and left == ["n.xml"]
    many = _Var("p1.pdf")
    route_drop(["p2.pdf"], [Slot(many, lambda p: p.endswith(".pdf"), multi=True)])
    assert many.v == "p1.pdf ; p2.pdf"                                             # a box of several adds


def test_outputs_saved_locally(monkeypatch):
    """No folder chosen, or a network folder: outputs go to Downloads; a local folder chosen is used."""
    from rstools import fsutil
    d = tempfile.mkdtemp()
    monkeypatch.setattr(fsutil, "downloads_dir", lambda: d)
    assert fsutil.is_network_path(r"\\server\share\CWNs")
    assert fsutil.is_network_path(r"\\?\UNC\server\share")
    assert not fsutil.is_network_path(r"\\?\C:\Users\me")
    assert not fsutil.is_network_path(tempfile.gettempdir())
    assert fsutil.output_folder("") == d
    assert fsutil.output_folder(r"\\server\share") == d
    assert fsutil.output_folder(tempfile.gettempdir()) == tempfile.gettempdir()


def test_progress_never_goes_back():
    """Real progress from the reorder engine only ever moves forward and ends at 1."""
    import openpyxl
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_compare as tc
    from cwn_compare.reorder import reorder_cwn
    d = tempfile.mkdtemp()
    rows = [list(r) for r in tc.BTN_ORIG]
    rows[2][1] = "FO"
    late = list(rows[2]); late[1] = "MO"
    src = os.path.join(d, "p.xlsx")
    tc.make(src, rows[:3] + [late] + rows[3:], tc.VIC_ORIG)
    seen = []
    reorder_cwn(src, d, progress=lambda f, m: seen.append(f))
    assert seen == sorted(seen) and seen[-1] == 1.0 and len(seen) > 4
    assert openpyxl.load_workbook(os.path.join(d, "p (variants in day order).xlsx"))


def test_idle_window_runs_no_fast_timers(monkeypatch):
    """Once started and idle, the window reads its queues about once a second (not several times a second on
    every tab), the window was built before being shown, and buttons have their icons before first shown."""
    import pytest
    pytest.importorskip("tkinter")
    import tkinter as tk
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        try:
            import cwn_compare.gui as g
            app = g.App()
        except tk.TclError:
            return
        try:
            assert app.pump.parts and len(app.pump.parts) == 4                     # one pump for every tab
            for q, handle, _busy in app.pump.parts:                                 # start-up work read
                while not q.empty():
                    handle()
            app.pump.stop()
            app.pump._fast_until = 0
            app.pump._tick()
            assert app.pump._due - __import__("time").monotonic() > 0.5            # idle: the slow beat
            run = app.run_btn
            assert str(run.cget("image"))                                         # icon set before shown
            for tab in (app.stats_tab, app.tt_tab, app.live_tab):
                assert not hasattr(tab, "_poll_id")
            assert app.live_tab._watch_id is None                                  # nothing to watch yet
        finally:
            app.destroy()


def test_every_tab_and_mode_fits_a_small_screen(tmp_path, monkeypatch):
    """On a 1366 x 768 laptop, with the window filling the screen, no tab or mode needs a scrollbar."""
    import pytest
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TPT_COMPACT", "1")
    from cwn_compare import gui
    from rstools.statspack import gui_tab as sg
    from rstools.timetable import gui_tab as tg
    try:
        app = gui.App()
    except tk.TclError:
        return                                          # no display
    try:
        if app.winfo_screenwidth() != 1366 or app.winfo_screenheight() != 768 or app.dpi != 96:
            pytest.skip("measured on a 1366 x 768 screen at 96 dpi only")
        app.geometry("1366x696+0+0")
        app.update()
        over = []

        def sweep(idx, page, var, redraw, values):
            app.notebook.select(idx)
            app.update()
            for value in values:
                var.set(value)
                redraw()
                app.update()
                app.update()
                if page.body.winfo_reqheight() > page.canvas.winfo_height() + 1:
                    over.append((idx, value, page.body.winfo_reqheight(), page.canvas.winfo_height()))

        stock = app.notebook.nametowidget(app.notebook.tabs()[0])
        sweep(0, stock, app.mode, app._mode_changed, [m for m, _t in gui.STOCK_TASKS])
        sweep(1, app.stats_page, app.stats_tab.mode, app.stats_tab._mode_changed, list(sg.MODES))
        sweep(2, app.tt_page, app.tt_tab.mode, app.tt_tab._mode_changed, list(tg.MODE_TEXT) + [tg.S4])
        app.notebook.select(3)
        app.update()
        if app.live_page.body.winfo_reqheight() > app.live_page.canvas.winfo_height() + 1:
            over.append((3, "live"))
        assert not over, over
    finally:
        app.destroy()


def test_task_box_groups_headings_and_picks():
    """The grouped Task list: a heading line per group, tasks indented under it, a heading picks its group's first
    task, and every task shows its own line."""
    import pytest
    tk = pytest.importorskip("tkinter")
    from rstools.widgets import TaskBox
    try:
        root = tk.Tk()
    except tk.TclError:
        return                                          # no display
    try:
        box = TaskBox(root, [("One", [("a", "Alpha"), ("b", "Beta")]), ("Two", [("c", "Gamma")])])
        values = list(box.cget("values"))
        assert values[0].strip("─ ") == "One" and values[1] == "   Alpha" and values[3].strip("─ ") == "Two"
        assert box.tasks == [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]
        for mode, label in box.tasks:
            box.show(mode)
            assert box.picked() == mode and box.get().strip() == label
        box.set(values[3])                              # the heading of group Two
        assert box.picked() == "c"
        box.set(values[0])
        assert box.picked() == "a"
    finally:
        root.destroy()


def test_stats_tab_shows_its_task_and_numbers_its_frames_without_gaps(tmp_path, monkeypatch):
    """A fresh start shows a task in every Task box, and the Stats Pack frames run 1, 2, 3... whichever are shown."""
    import pytest
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cwn_compare import gui
    from rstools.statspack import gui_tab as sg
    try:
        app = gui.App()
    except tk.TclError:
        return                                          # no display
    try:
        for tab in (app, app.stats_tab, app.tt_tab):
            assert tab.task_box.get().strip(), type(tab).__name__
        assert app.live_tab.mode_box.get().strip()
        st = app.stats_tab
        for mode in sg.MODES:
            st.mode.set(mode)
            st._mode_changed()
            app.update()
            frames = (st.in_frame, st.opt_frame, st.out_frame, st.sel_frame, st.run_frame)
            shown = [f for f in frames if f.winfo_manager()]
            numbers = [int(f.cget("text").split(".")[0]) for f in shown]
            assert numbers == list(range(1, len(shown) + 1)), (mode, [f.cget("text") for f in shown])
    finally:
        app.destroy()


def test_settings_are_saved_even_when_the_live_window_place_cannot_be(tmp_path, monkeypatch):
    import pytest
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cwn_compare import gui
    try:
        app = gui.App()
    except tk.TclError:
        return                                          # no display
    saved = []
    monkeypatch.setattr(app.live_window, "_save_place", lambda: (_ for _ in ()).throw(RuntimeError("no place")))
    monkeypatch.setattr(app, "save_app_settings", lambda: saved.append(True))
    app._on_close()
    assert saved == [True]


def test_command_line_unknown_command_and_help(capsys):
    import pytest
    import TrainPlanningTools as cli
    with pytest.raises(SystemExit) as caught:
        cli.main(["statpack", "--xml", "x.xml"])
    err = capsys.readouterr().err
    assert caught.value.code == 2 and "unknown command 'statpack'" in err
    for name in ("stationbook", "reorder", "statspack", "timetable", "section4", "berthing", "workings-berthing",
                 "selftest"):
        assert name in err
    with pytest.raises(SystemExit) as caught:
        cli.main(["--help"])
    assert caught.value.code == 0 and "section4" in capsys.readouterr().out      # the commands are listed
    cli.main(["selftest", "--help"])                                              # help, not a file called --help
    assert "usage: TrainPlanningTools selftest" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        cli.main(["SECTION4", "--xml", "missing.xml"])                             # commands are not case sensitive
    assert caught.value.code == 2 and "could not be found" in capsys.readouterr().err


def test_update_dialog_reports_a_new_version_and_an_error(tmp_path, monkeypatch):
    import pytest
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cwn_compare import gui
    from rstools import update_dialog, updater
    try:
        app = gui.App()
    except tk.TclError:
        return                                          # no display
    try:
        newer = updater.Release("99.0.0", "v99.0.0", "Notes for the new version", "https://example.invalid/r",
                                "https://example.invalid/a", 1000, "sha256:abc")
        dlg = update_dialog.UpdateDialog(app, "1.0.0", "", release=newer)
        app.update()
        assert "99.0.0 is available" in dlg.head.cget("text")
        assert not dlg.install_btn.instate(["disabled"])
        assert "Notes for the new version" in dlg.notes.get("1.0", "end")
        dlg._error("The update check failed: offline")                       # an error keeps an offered update usable
        assert dlg.head.cget("text") == "Could not check for updates" and "offline" in dlg.sub.cget("text")
        assert not dlg.install_btn.instate(["disabled"])
        dlg.destroy()
        same = updater.Release("1.0.0", "v1.0.0", "", "https://example.invalid/r", "https://example.invalid/a", 1, "")
        dlg = update_dialog.UpdateDialog(app, "1.0.0", "", release=same)
        app.update()
        assert dlg.head.cget("text") == "You have the latest version" and dlg.install_btn.instate(["disabled"])
        assert "(No release notes.)" in dlg.notes.get("1.0", "end")
        dlg.destroy()
    finally:
        app.destroy()


def test_rules_dialog_lists_sets_and_protects_the_built_in_one(tmp_path, monkeypatch):
    import pytest
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cwn_compare import gui
    from rstools import rules, rules_dialog
    try:
        app = gui.App()
    except tk.TclError:
        return                                          # no display
    try:
        dlg = rules_dialog.RulesDialog(app)
        app.update()
        names = list(dlg.tree.get_children())
        assert rules.BUILT_IN_S4 in names
        dlg.tree.selection_set(rules.BUILT_IN_S4)
        dlg._buttons()
        assert dlg.del_btn.instate(["disabled"]) and not dlg.use_btn.instate(["disabled"])
        asked = []
        monkeypatch.setattr(rules_dialog.messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)
        dlg._remove()                                    # the built-in set cannot be removed, and is not asked about
        assert asked == [] and rules.BUILT_IN_S4 in dlg.tree.get_children()
        dlg._use()
        assert "is now the Section 4 rule set in use" in dlg.status.cget("text")
        dlg.destroy()
    finally:
        app.destroy()


def test_display_is_decided_by_the_window_centre_and_rescales_are_limited():
    """Moving between displays: the display under the window's centre decides (a window across two displays is
    not taken for each in turn), and a rescale is never repeated in quick succession."""
    import pytest
    pytest.importorskip("tkinter")
    from rstools import theme
    left = ((0, 0, 1920, 1040), 96)
    right = ((1920, 0, 3840, 1040), 192)
    assert theme.pick_display((100, 100), [left, right]) == left
    assert theme.pick_display((2500, 500), [left, right]) == right
    assert theme.pick_display((1919, 5), [left, right]) == left          # the edge pixel is still the left display
    assert theme.pick_display((4500, 500), [left, right]) == right       # off every display: the nearest one
    assert theme.pick_display((0, 0), []) is None

    now = [100.0]
    guard = theme.RescaleGuard(clock=lambda: now[0])
    assert guard.allow()                                                 # the first rescale
    guard.done()
    now[0] += 0.5
    assert not guard.allow()                                             # Windows still settling the window
    now[0] += 1.2
    assert guard.allow()                                                 # quiet time over
    guard.done()
    now[0] += 0.3
    guard.mouse(True)                                                    # a new drag: allowed again...
    assert not guard.allow()                                             # ...but never a third time in 3 seconds
    now[0] += 3.0
    assert guard.allow() and guard.refused == 2


def test_a_failed_rescale_is_logged_and_leaves_the_window_usable(tmp_path, monkeypatch):
    import pytest
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cwn_compare import gui
    from rstools import errorlog
    try:
        app = gui.App()
    except tk.TclError:
        return
    try:
        written = []
        monkeypatch.setattr(errorlog, "write", lambda text: written.append(text))
        monkeypatch.setattr(app, "set_text_size", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        before = app.dpi
        app.dpi_changed(before * 2)
        assert written and "boom" in written[0]
        assert app.dpi == before and app.winfo_exists()                  # nothing half rescaled
        app.update()
    finally:
        app.destroy()


def test_painting_is_held_on_the_client_window_and_always_switched_back(monkeypatch):
    """freeze_redraw (Windows): WM_SETREDRAW goes to the Tk client window, never the frame, and is switched back on
    (and the frame repainted) even when the rescale fails."""
    import sys
    import types
    import pytest
    pytest.importorskip("tkinter")
    from rstools import theme
    calls = []
    user32 = types.SimpleNamespace(
        SendMessageW=lambda hwnd, msg, w, l: calls.append(("send", hwnd, msg, w)),
        GetAncestor=lambda hwnd, flag: 999,
        RedrawWindow=lambda hwnd, *a: calls.append(("redraw", hwnd)))
    fake = types.SimpleNamespace(windll=types.SimpleNamespace(user32=user32))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "ctypes", fake)
    root = types.SimpleNamespace(winfo_id=lambda: 123)
    try:
        with theme.freeze_redraw(root):
            raise ValueError("rescale failed")
    except ValueError:
        pass
    assert calls == [("send", 123, 0x000B, 0), ("send", 123, 0x000B, 1), ("redraw", 999)]
