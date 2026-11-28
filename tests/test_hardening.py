"""Safety fixes found in the 3.36 review: write probes, formula text from older Excel files, the hidden
comparison data, update downloads, temporary files and settings copies (synthetic data only)."""
import base64
import os
import sys
import zlib

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rstools import branding, fsutil, limits  # noqa: E402


def test_the_write_probe_never_touches_an_existing_file(tmp_path):
    keep = tmp_path / f"~write{os.getpid()}.tmp"          # the name the old probe used
    keep.write_text("someone else's file")
    assert branding._writable(str(tmp_path))
    assert keep.read_text() == "someone else's file"
    assert sorted(os.listdir(tmp_path)) == [keep.name]      # the probe itself is gone


def test_text_from_an_old_excel_file_stays_text(tmp_path):
    import openpyxl
    from cwn_compare.loader import _put
    wb = openpyxl.Workbook()
    ws = wb.active
    cell = _put(ws, 1, 1, "=HYPERLINK(\"http://x\")")
    _put(ws, 1, 2, "a\x01b")
    assert cell.data_type == "s"
    out = tmp_path / "o.xlsx"
    wb.save(out)
    back = openpyxl.load_workbook(out).active
    assert back["A1"].data_type == "s" and back["A1"].value.startswith("=HYPERLINK")
    assert back["B1"].value == "ab"


def test_hidden_comparison_data_has_a_size_cap(tmp_path, monkeypatch):
    import openpyxl
    from cwn_compare import meta
    wb = openpyxl.Workbook()
    meta.write_meta(wb, {"x": "y" * 5000})
    path = tmp_path / "c.xlsx"
    wb.save(path)
    assert meta.read_meta_file(str(path)) == {"x": "y" * 5000}
    monkeypatch.setattr(limits, "_cache", {**limits.DEFAULTS, "META_MAX_BYTES": 1000})
    assert meta.read_meta_file(str(path)) is None             # would unpack to more than the cap
    assert base64 and zlib                                     # (imports used by the format)


def test_temporary_names_are_random_and_short(tmp_path):
    names = {os.path.basename(fsutil.temp_path(str(tmp_path / "x.xlsx"))) for _ in range(50)}
    assert len(names) == 50 and all(n.startswith("~tpt") and len(n) <= 20 for n in names)


def test_a_settings_copy_is_complete_or_not_made(tmp_path):
    src = tmp_path / "src.csv"
    src.write_text("A,B\n1,2\n", encoding="utf-8")
    dest = tmp_path / "data" / "mine.csv"
    assert fsutil.copy_default(str(src), str(dest))
    assert dest.read_text(encoding="utf-8-sig") == "A,B\n1,2\n"
    assert [n for n in os.listdir(dest.parent) if n.startswith("~tpt")] == []
    assert not fsutil.copy_default(str(tmp_path / "missing.csv"), str(tmp_path / "data" / "x.csv"))


def test_too_large_settings_lists_are_not_read(tmp_path, monkeypatch):
    from rstools.statspack import fleet
    big = tmp_path / "fleet.csv"
    big.write_text("Class,Operator\n" + "377,GTR\n" * 50)
    monkeypatch.setattr(limits, "_cache", {**limits.DEFAULTS, "SETTINGS_CSV_MAX_BYTES": 100})
    assert fleet._read_csv(str(big)) == ([], [])


def test_update_page_and_file_names_are_safe(tmp_path, monkeypatch):
    from rstools import updater
    assert updater._safe_page("javascript:alert(1)") == updater.RELEASES_PAGE
    assert updater._safe_page("https://github.com/x/y/releases/tag/v1") == "https://github.com/x/y/releases/tag/v1"
    monkeypatch.setattr(updater, "running_exe", lambda: None)
    monkeypatch.setattr(fsutil, "downloads_dir", lambda: str(tmp_path))
    rel = updater.Release("..\\..\\evil", "", "", "", "", 0, "")
    first = updater.download_target(rel)
    assert os.path.dirname(first) == str(tmp_path) and ".." not in os.path.basename(first)
    open(first, "w").close()
    assert updater.download_target(rel) != first             # an earlier download is never overwritten
    assert updater.signature_state(first) in ("none", "bad", "good")


def test_a_download_larger_than_expected_is_refused(tmp_path, monkeypatch):
    import io
    from rstools import updater

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Opener:
        def open(self, *a, **k): return Resp(b"MZ" + b"0" * 5000)
    monkeypatch.setattr(updater.urllib.request, "build_opener", lambda *a: Opener())
    rel = updater.Release("9", "v9", "", "", "https://api.github.com/x", 100, "sha256:" + "0" * 64)
    with pytest.raises(updater.UpdateError, match="larger than expected"):
        updater.download(rel, str(tmp_path / "new.exe"))
    assert os.listdir(tmp_path) == []


# --------------------------------------------------------------------------- shared helpers (3.36 clean-up)
def test_shared_helpers():
    import xml.etree.ElementTree as ET
    from rstools import attune_xml, clock, naming
    assert attune_xml.location(ET.fromstring('<location tiploc=" " longDesc="X"/>')) is None
    assert attune_xml.location(ET.fromstring('<location tiploc="VICT" shortDesc="Vic"/>')) == ("VICT", "Vic")
    assert attune_xml.plan_type({"planType": "L", "provisional": "true"}) == "D"
    assert attune_xml.secs("25:01") == 90060 and attune_xml.secs("x") is None
    assert clock.clock(90060, "+") == "01+01" and clock.clock(None) == "" and clock.hhmm(1445) == "0005"
    assert naming.output_stem('a/b:c.xlsx') == "a-b-c" and naming.output_stem("") == ""


def test_the_file_cache_keeps_unchanged_files_and_is_bounded(tmp_path):
    from rstools import filecache
    filecache.clear()
    reads = []

    def reader(path):
        reads.append(path)
        return open(path).read()
    paths = []
    for i in range(filecache.SIZE + 2):
        p = tmp_path / f"f{i}.txt"
        p.write_text(str(i))
        paths.append(str(p))
    assert filecache.remember(reader, paths[0]) == "0"
    assert filecache.remember(reader, paths[0]) == "0" and len(reads) == 1
    for p in paths[1:]:
        filecache.remember(reader, p)
    filecache.remember(reader, paths[0])                     # pushed out by the newer ones: read again
    assert reads.count(paths[0]) == 2 and len(filecache._STORE) == filecache.SIZE


def test_save_failures_become_one_plain_message(tmp_path):
    class Problem(Exception):
        pass

    def locked():
        raise PermissionError(13, "denied")
    with pytest.raises(Problem, match="open in Excel"):
        fsutil.save_output(locked, str(tmp_path / "x.xlsx"), Problem)


# --------------------------------------------------------------------------- command-line options checked up front
@pytest.mark.parametrize("cmd, argv, msg", [
    ("compare", ["--original", "a.xlsx", "--updated", "b.xlsx", "--colour", "yellowish"], "hex colour"),
    ("compare", ["--original", "a.xlsx", "--updated", "b.xlsx", "--acwn", "--highlight-only"], "together"),
    ("compare", ["--original", "a.xlsx", "--updated", "b.xlsx", "--exclude", "PLATFORM,NOPE"], "NOPE"),
    ("berthing", ["--compare", "a.xlsx", "b.xlsx", "--layout", "c.xlsx"], "--layout"),
    ("berthing", ["--xml", "a.xml", "--updated", "b.xml"], "--updated"),
    ("statspack", ["--old-pack", "a.xlsx", "--new-pack", "b.xlsx", "--xml", "c.xml"], "--xml"),
    ("statspack", ["--xml", "a.xml", "--trent", "t.docx", "--per-day"], "--per-day"),
    ("stationbook", ["--xml", "a.xml", "--station", "A; B", "--name", "x"], "one station"),
])
def test_ignored_option_combinations_are_refused(cmd, argv, msg, capsys, tmp_path):
    import TrainPlanningTools as T
    with pytest.raises(SystemExit):
        T.main(([] if cmd == "compare" else [cmd]) + argv + ["--out", str(tmp_path)])
    assert msg in capsys.readouterr().err


# --------------------------------------------------------------------------- stopping a run
def test_a_stopped_run_ends_at_its_next_step():
    import threading
    from rstools.cancel import Cancelled, StopQueue
    q = StopQueue()
    q.put(("log", "before"))
    q.stop()
    q.put(("done", "the window may still post its own messages"))
    seen = []

    def worker():
        try:
            q.put(("log", "step 2"))
            seen.append("carried on")
        except Cancelled:
            seen.append("stopped")
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    items = [q.get_nowait() for _ in range(q.qsize())]
    assert seen == ["stopped"] and items[-1] == ("stopped",) and ("log", "step 2") not in items
    q.reset()
    assert not q.stopping


def test_the_stop_buttons_follow_each_tabs_run(monkeypatch, tmp_path):
    pytest.importorskip("tkinter")
    import tkinter as tk
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        import cwn_compare.gui as g
        app = g.App()
    except tk.TclError:
        return
    try:
        tab = app.stats_tab
        assert "disabled" in tab.stop_btn.state()
        tab.running = True
        app.set_busy(True)
        assert "disabled" not in tab.stop_btn.state() and "disabled" in app.tt_tab.stop_btn.state()
        app.notebook.select(1)
        app._stop_current_tab()
        assert tab.q.stopping and "disabled" in tab.stop_btn.state()
        tab.q.put(("stopped",))
        tab._poll()
        assert not tab.running and "Stopped" in tab.status.cget("text")
        tab.running = True
        app.set_busy(True)
        assert not tab.q.stopping                                       # a new run starts afresh
    finally:
        app.destroy()


def test_left_out_categories_are_not_counted_as_changes(tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_compare as tc
    from cwn_compare import engine
    from cwn_compare.options import Options
    a, b = str(tmp_path / "a.xlsx"), str(tmp_path / "b.xlsx")
    tc.make(a, tc.BTN_ORIG, tc.VIC_ORIG)
    tc.make(b, *tc._upd_rows())
    opts = Options(original=a, updated=b, output_dir=str(tmp_path), output_name="x")
    for k in ("PLATFORM", "STOCK"):
        opts.categories[k] = {"cwn": False, "show_old": False, "report": False}
    lines = []
    res = engine.run(opts, log=lines.append)
    import openpyxl
    listed = list(openpyxl.load_workbook(res["report"])["All Changes"].iter_rows(min_row=2, values_only=True))
    assert res["changes"] == len(listed) == 5
    assert any("2 left out, as asked" in m for m in lines)


def test_a_vpt_is_refused_for_a_timetable_check_with_the_reason(tmp_path):
    from rstools.timetable.engine import read_attune_print
    from rstools.timetable.prints import PrintError
    p = tmp_path / "plan.vpt"
    p.write_text("x")
    with pytest.raises(PrintError, match="no public times"):
        read_attune_print(str(p))


def test_short_sections_share_a_page_and_empty_wide_tables_are_not_split(tmp_path):
    import zipfile
    import pypdf
    from rstools.docexport import Section, split_wide, write_docx, write_pdf
    secs = [Section(f"Table {i}", ["A", "B"], [["1", "2"]]) for i in range(6)]
    write_pdf(str(tmp_path / "s.pdf"), "T", secs)
    assert len(pypdf.PdfReader(str(tmp_path / "s.pdf")).pages) == 1
    write_docx(str(tmp_path / "s.docx"), "T", secs)
    assert "pageBreakBefore" not in zipfile.ZipFile(tmp_path / "s.docx").read("word/document.xml").decode()
    wide = Section("Clashes", [f"H{i}" for i in range(30)], [["None identified"]])
    assert len(split_wide(wide)) == 1
    assert len(split_wide(Section("Full", [f"H{i}" for i in range(30)], [[str(i) for i in range(30)]]))) == 2


@pytest.mark.parametrize("cmd", ["compare", "statspack", "reorder", "berthing"])
def test_a_missing_out_folder_is_refused_not_sent_to_downloads(cmd, capsys, tmp_path):
    import TrainPlanningTools as T
    first = {"compare": ["--original", "a.xlsx", "--updated", "b.xlsx"], "statspack": ["--xml", "a.xml", "--trent",
             "t.docx"], "reorder": ["reorder", "a.xlsx"], "berthing": ["berthing", "--xml", "a.xml"]}[cmd]
    argv = ([cmd] if cmd == "statspack" else []) + first + ["--out", str(tmp_path / "typo")]
    with pytest.raises(SystemExit) as exc:
        T.main(argv)
    assert exc.value.code == 2 and "does not exist" in capsys.readouterr().err


def test_reorder_on_a_damaged_file_gives_an_error_line_not_a_traceback(capsys, tmp_path):
    import TrainPlanningTools as T
    bad = tmp_path / "not a cwn.xlsx"
    bad.write_bytes(b"this is not a workbook")
    with pytest.raises(SystemExit) as exc:
        T.main(["reorder", str(bad), "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert exc.value.code == 1 and "\nERROR: " in out and "Traceback" not in out


def test_batch_with_a_missing_or_repeated_folder_says_so(capsys, tmp_path):
    import TrainPlanningTools as T
    for argv, says in ((["--original-folder", str(tmp_path / "nope"), "--updated", str(tmp_path)], "does not exist"),
                       (["--original-folder", str(tmp_path), "--updated", str(tmp_path)], "the same folder")):
        with pytest.raises(SystemExit) as exc:
            T.main(argv)
        assert exc.value.code == 1 and says in capsys.readouterr().out
