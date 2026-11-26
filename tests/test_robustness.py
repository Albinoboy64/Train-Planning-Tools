"""Focused tests for small fixes and for refusing damaged, truncated or hostile input: the .xlsb archive check, the
day-detection helper process, the built-in rule set's summary file, the cached Section 4 XML, the reorder flag
checks, the updater's download folder / downloads / install recovery, and every reader's behaviour on cut-off files.
Everything is synthetic; the network, the clock and the real app folder are never used."""
import contextlib
import io
import itertools
import os
import sys
import urllib.error
import zipfile
from concurrent.futures import Future
from email.message import Message

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def make_zip(path, parts):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return str(path)


# --------------------------------------------------------------------------- 2. .xlsb goes through the archive check
def test_xlsb_is_checked_before_it_is_opened(tmp_path, monkeypatch):
    import openpyxl
    from cwn_compare import loader
    p = make_zip(tmp_path / "book.xlsb", {"[Content_Types].xml": "<Types/>", "xl/workbook.bin": b"\0" * 64})
    seen = []
    real = __import__("rstools.fsutil", fromlist=["check_office_file"]).check_office_file
    monkeypatch.setattr("rstools.fsutil.check_office_file", lambda path: seen.append(("check", path)) or real(path))
    monkeypatch.setattr(loader, "_load_xlsb", lambda path: seen.append(("load", path)) or openpyxl.Workbook())
    wb = loader.load_any(p)
    assert isinstance(wb, openpyxl.Workbook)
    assert [kind for kind, _p in seen] == ["check", "load"]          # the check comes first, on the same file


def test_oversized_xlsb_is_refused_like_xlsx(tmp_path, monkeypatch):
    """The same part and total limits apply to every zip-based CWN format; the unpacker is never reached."""
    from cwn_compare import loader
    from rstools import fsutil
    called = []
    monkeypatch.setattr(loader, "_load_xlsb", lambda path: called.append(path))
    monkeypatch.setattr(fsutil, "ZIP_PART_LIMIT", 1000)                  # a few KB stand in for 600 MB
    for ext in (".xlsb", ".xlsx", ".xlsm"):
        p = make_zip(tmp_path / f"big{ext}", {"[Content_Types].xml": "<Types/>", "xl/part.bin": os.urandom(5000)})
        with pytest.raises(loader.LoadError, match="unrealistic size"):
            loader.load_any(p)
    assert called == []
    monkeypatch.setattr(fsutil, "ZIP_PART_LIMIT", 10 ** 9)
    monkeypatch.setattr(fsutil, "ZIP_TOTAL_LIMIT", 3000)                 # many small parts add up
    p = make_zip(tmp_path / "many.xlsb", {f"xl/p{i}.bin": os.urandom(1200) for i in range(4)})
    with pytest.raises(loader.LoadError, match="over 2 GB"):
        loader.load_any(p)
    assert called == []


# --------------------------------------------------------------------------- 3. day detection: one helper process
class FakePool:
    """Stands in for ProcessPoolExecutor: counts pools, records what is submitted, runs the job at once."""
    created = 0
    events = []
    broken = False

    def __init__(self, max_workers=None, mp_context=None):
        FakePool.created += 1
        FakePool.workers = max_workers
        if FakePool.broken:
            raise OSError("no helper process")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        FakePool.events.append(("submit", args[0]))
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except Exception as exc:
            fut.set_exception(exc)
        return fut


@pytest.fixture
def pool(monkeypatch):
    FakePool.created, FakePool.events, FakePool.broken = 0, [], False
    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", FakePool)
    return FakePool


def day_files(tmp_path):
    from cwn_compare.days import LARGE_CWN
    small = tmp_path / "small.xlsx"
    small.write_bytes(b"x" * 1024)
    big = []
    for n in (1, 2):
        f = tmp_path / f"big{n}.xlsx"
        with open(f, "wb") as fh:
            fh.truncate(LARGE_CWN)                                   # a sparse file of exactly the threshold
        big.append(str(f))
    return str(small), big


def test_every_large_cwn_goes_to_one_helper_process(tmp_path, monkeypatch, pool):
    from cwn_compare import days
    small, (big1, big2) = day_files(tmp_path)
    reads = []
    monkeypatch.setattr(days, "read_days", lambda path: reads.append(path) or ([0, 1], False))
    found = days.read_days_cached([big1, small, big2], {})
    assert pool.created == 1 and pool.workers == 2                   # one pool, however many large files
    assert [p for kind, p in pool.events if kind == "submit"] == [big1, big2]    # every large file, none small
    assert list(found) == [big1, small, big2]                       # the caller's order
    assert all(v[1] == [0, 1] and v[2] is False for v in found.values())
    assert found[big1][0] == os.path.getmtime(big1)
    assert reads.count(small) == 1 and reads.count(big1) == 1       # nothing was read twice


def test_no_helper_process_for_small_files_or_cached_results(tmp_path, monkeypatch, pool):
    from cwn_compare import days
    small, (big1, big2) = day_files(tmp_path)
    monkeypatch.setattr(days, "read_days", lambda path: ([2], True))
    assert days.read_days_cached([small], {})[small][1:] == ([2], True) and pool.created == 0
    cache = {big1: (os.path.getmtime(big1), [4], False)}
    found = days.read_days_cached([big1, big2], cache)
    assert found[big1] == cache[big1] and [p for _k, p in pool.events] == [big2]      # only the changed/new one
    stale = {big1: (os.path.getmtime(big1) - 5, [4], False)}
    assert days.read_days_cached([big1], stale)[big1][1] == [2]                        # changed file: read again
    assert days.read_days_cached([str(tmp_path / "gone.xlsx")], {}) == {str(tmp_path / "gone.xlsx"): None}


def test_day_detection_fallbacks(tmp_path, monkeypatch, pool):
    from cwn_compare import days
    _small, (big1, big2) = day_files(tmp_path)
    monkeypatch.setattr(days, "read_days", lambda path: ([0], False))
    pool.broken = True                                              # the helper process cannot start
    found = days.read_days_cached([big1, big2], {})
    assert pool.created == 1 and found[big1][1] == [0] and found[big2][1] == [0]
    pool.created, pool.broken = 0, False
    calls = []

    def flaky(path):                                                # big1 fails in the helper, then works here
        calls.append(path)
        if path == big1 and calls.count(big1) == 1:
            raise RuntimeError("helper died")
        return ([1], False)
    monkeypatch.setattr(days, "read_days", flaky)
    found = days.read_days_cached([big1, big2], {})
    assert pool.created == 1 and found[big1][1] == [1] and found[big2][1] == [1]
    assert calls.count(big1) == 2 and calls.count(big2) == 1       # only the failed file was read again
    monkeypatch.setattr(days, "read_days", lambda path: (_ for _ in ()).throw(ValueError("unreadable")))
    assert days.read_days_cached([big1], {}) == {big1: None}       # the fallback fails too: shown as unread


def test_a_real_helper_process_gives_the_same_days(tmp_path, monkeypatch):
    """No fakes: two real CWNs sent together to one real helper process (the size threshold lowered so the small
    synthetic files count as large) give what reading them here gives."""
    import test_compare as tc
    from cwn_compare import days
    a, b = str(tmp_path / "a.xlsx"), str(tmp_path / "b.xlsx")
    tc.make(a, tc.BTN_ORIG, tc.VIC_ORIG)
    tc.make_multi_day(b)
    here = {p: days.read_days(p) for p in (a, b)}
    monkeypatch.setattr(days, "LARGE_CWN", 1)
    found = days.read_days_cached([a, b], {})
    assert {p: (v[1], v[2]) for p, v in found.items()} == {p: (list(d), assumed) for p, (d, assumed) in here.items()}
    assert all(v[0] == os.path.getmtime(p) for p, v in found.items())


def test_gui_uses_the_shared_day_reader():
    pytest.importorskip("tkinter")
    import inspect
    from cwn_compare.gui import App
    source = inspect.getsource(App._read_days)
    assert "read_days_cached" in source and "ProcessPoolExecutor" not in source


# --------------------------------------------------------------------------- 4. the built-in rule set's summary file
def test_rebuilt_builtin_rule_set_has_its_summary_file(tmp_path, monkeypatch):
    import json
    import test_timetable as tt
    from rstools import rules
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    gz, info = str(tmp_path / "s4.json.gz"), str(tmp_path / "s4.info.json")
    monkeypatch.setattr(rules, "BUILT_IN_S4_FILE", gz)
    monkeypatch.setattr(rules, "BUILT_IN_S4_INFO", info)
    rules._builtin_cache.clear()
    old, new = str(tmp_path / "s4_old.pdf"), str(tmp_path / "s4_new.pdf")
    tt.write_s4_pdf(old, tt.S4_ROWS)
    tt.write_s4_pdf(new, tt.S4_ROWS_NEW)
    summary = rules.build_builtin_set([old, new], out=gz, log=lambda m: None)
    with open(info, encoding="utf-8") as fh:
        stored = json.load(fh)
    assert stored == {"gz_size": os.path.getsize(gz), "info": summary, "files": ["s4_old.pdf", "s4_new.pdf"]}
    assert summary["possessions"] == 4 and summary["sections"] == 3
    assert summary["from"] == "2026-12-13" and summary["to"] == "2027-02-14"
    assert rules._builtin_summary() == stored                       # the fast path accepts it
    built = rules._builtin_info()
    assert built["name"] == rules.BUILT_IN_S4 and built["files"] == ["s4_old.pdf", "s4_new.pdf"]
    assert (built["from"], built["to"], built["possessions"]) == ("2026-12-13", "2027-02-14", 4)
    sets = rules.list_sets()
    assert [s["name"] for s in sets] == [rules.BUILT_IN_S4] and sets[0]["built_in"] and sets[0]["active"]
    from datetime import date
    line, stale = rules.in_use(date(2026, 12, 20))
    assert rules.BUILT_IN_S4 in line and not stale                  # within the rules' dates
    assert rules.in_use(date(2027, 3, 1))[1]                        # the dates ended in February 2027
    with open(gz, "ab") as fh:
        fh.write(b"x")                                              # no longer the file the summary describes
    assert rules._builtin_summary() is None


def test_summary_file_sits_beside_any_output_name(tmp_path, monkeypatch):
    import test_timetable as tt
    from rstools import rules
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    pdf = str(tmp_path / "a.pdf")
    tt.write_s4_pdf(pdf, tt.S4_ROWS)
    rules.build_builtin_set([pdf], out=str(tmp_path / "custom.bin"), log=lambda m: None)
    assert (tmp_path / "custom.bin.info.json").exists()
    assert rules.BUILT_IN_S4_INFO == rules.BUILT_IN_S4_FILE.replace(".json.gz", ".info.json")   # the shipped pair


# --------------------------------------------------------------------------- 5. Section 4 check: cached XML
def test_repeated_section4_checks_read_the_xml_once(tmp_path, monkeypatch):
    import openpyxl
    import test_timetable as tt
    from rstools import stationbook as SB
    from rstools.timetable import section4 as S4
    xml, pdf = str(tmp_path / "plan.xml"), str(tmp_path / "s4.pdf")
    tt.write_s4_xml(xml)
    tt.write_s4_pdf(pdf, tt.S4_ROWS)
    SB._PLANS.clear()
    reads = []
    real = SB.read_plan
    monkeypatch.setattr(SB, "read_plan", lambda path: reads.append(path) or real(path))

    def run(name):
        path, res, st, start = S4.run_check(xml, [pdf], str(tmp_path), name)
        sheets = {ws.title: [[c.value for c in row] for row in ws.iter_rows()]
                  for ws in openpyxl.load_workbook(path).worksheets}
        clashes = [(c.possession.number, c.train, c.day, c.at_a, c.at_b) for c in res.clashes]
        return clashes, res.trains, start, sheets
    first, second = run("first"), run("second")
    assert len(reads) == 1                                          # the second check reused the plan
    assert first == second and first[0]                             # identical output, and it found clashes
    with open(xml, "a", encoding="utf-8") as fh:
        fh.write("<!-- the timetable was saved again -->")
    run("third")
    assert len(reads) == 2                                          # a changed file is read again


def test_section4_check_reports_a_cut_off_xml_every_time(tmp_path, monkeypatch):
    import test_timetable as tt
    from rstools import stationbook as SB
    from rstools.timetable import section4 as S4
    xml, pdf = str(tmp_path / "plan.xml"), str(tmp_path / "s4.pdf")
    tt.write_s4_xml(xml)
    tt.write_s4_pdf(pdf, tt.S4_ROWS)
    data = open(xml, "rb").read()
    with open(xml, "wb") as fh:
        fh.write(data[: len(data) // 2])
    SB._PLANS.clear()
    reads = []
    real = SB.read_plan
    monkeypatch.setattr(SB, "read_plan", lambda path: reads.append(path) or real(path))
    for _ in range(2):
        with pytest.raises(S4.Section4Error, match="could not be read"):
            S4.run_check(xml, [pdf], str(tmp_path), "cut")
    assert len(reads) == 2 and not SB._PLANS                        # a failed read is never kept


# --------------------------------------------------------------------------- 6. reorder flag checks
FLAGS = ("--merge", "--merge-diagrams", "--merge-berths", "--merge-berth-diagrams")


def _combo_valid(merge, diagrams, berths, berth_diagrams):
    return (berths or not berth_diagrams) and (merge or not (diagrams or berths))


def _reorder(monkeypatch, *flags):
    import TrainPlanningTools as cli
    seen = []
    monkeypatch.setattr("cwn_compare.reorder.reorder_cwn",
                        lambda path, out, name, by_time, **kw: seen.append(kw) or {"trains": 0})
    out, code = io.StringIO(), None
    with contextlib.redirect_stdout(out):
        try:
            cli.reorder_cli(["missing.xlsx", *flags])               # the file need not exist: flags are checked first
        except SystemExit as exc:
            code = exc.code
    return seen, code, out.getvalue()


def test_every_reorder_flag_combination(monkeypatch):
    from cwn_compare.reorder import MergeRules
    valid = invalid = 0
    for combo in itertools.product((False, True), repeat=4):
        flags = [f for f, on in zip(FLAGS, combo) if on]
        seen, code, text = _reorder(monkeypatch, *flags)
        if _combo_valid(*combo):
            valid += 1
            merge, diagrams, berths, berth_diagrams = combo
            assert code is None and len(seen) == 1, flags
            assert seen[0]["merge"] is merge
            assert seen[0]["rules"] == MergeRules(diagrams, berths, berths and berth_diagrams)
        else:
            invalid += 1
            assert code == 1 and seen == [] and text.startswith("ERROR: --merge-"), (flags, text)
            wanted = "--merge-berths" if combo[3] and not combo[2] else "go with --merge"
            assert wanted in text, (flags, text)
    assert (valid, invalid) == (7, 9)


def test_reorder_flag_check_raises_instead_of_exiting():
    import argparse
    import TrainPlanningTools as cli
    from cwn_compare.reorder import ReorderError
    ns = lambda **kw: argparse.Namespace(**dict(dict(merge=False, merge_diagrams=False, merge_berths=False,
                                                    merge_berth_diagrams=False), **kw))
    cli._reorder_flags(ns())
    cli._reorder_flags(ns(merge=True, merge_berths=True, merge_berth_diagrams=True))
    with pytest.raises(ReorderError, match="--merge-berths"):
        cli._reorder_flags(ns(merge=True, merge_berth_diagrams=True))
    with pytest.raises(ReorderError, match="--merge-berths"):                       # the more specific message first
        cli._reorder_flags(ns(merge_berth_diagrams=True))
    with pytest.raises(ReorderError, match="go with --merge"):
        cli._reorder_flags(ns(merge_diagrams=True))


# --------------------------------------------------------------------------- 7. updater: where downloads are saved
def _release(version="9.9.9", **kw):
    from rstools import updater
    base = dict(version=version, tag="v" + version, notes="", page="", asset_api="https://api/asset", asset_size=0,
                digest="")
    return updater.Release(**dict(base, **kw))


def test_download_target_uses_the_real_downloads_folder(tmp_path, monkeypatch):
    from rstools import updater
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(updater, "running_exe", lambda: None)
    assert updater.download_target(_release()) == str(home / "Downloads" / "TrainPlanningTools-9.9.9.exe")
    assert updater.download_target(_release("")).endswith("TrainPlanningTools-latest.exe")
    moved = tmp_path / "D" / "My Downloads"                         # IT redirected the folder
    moved.mkdir(parents=True)
    monkeypatch.setattr("rstools.fsutil.downloads_dir", lambda: str(moved))
    assert updater.download_target(_release()) == str(moved / "TrainPlanningTools-9.9.9.exe")


def test_download_target_next_to_the_exe_is_unchanged(tmp_path, monkeypatch):
    from rstools import updater
    exe = str(tmp_path / "TrainPlanningTools.exe")
    monkeypatch.setattr(updater, "running_exe", lambda: exe)
    monkeypatch.setattr(updater, "can_replace_in_place", lambda: True)
    monkeypatch.setattr("rstools.fsutil.downloads_dir", lambda: pytest.fail("Downloads is not used in place"))
    assert updater.download_target(_release()) == exe + ".new"


# --------------------------------------------------------------------------- 8. updater downloads and installs
class Stream:
    """A download body: chunks, then (optionally) an error, as a network connection might."""

    def __init__(self, chunks, then=None):
        self.chunks, self.then = list(chunks), then

    def read(self, n=-1):
        if self.chunks:
            return self.chunks.pop(0)
        if self.then is not None:
            raise self.then
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def serve(monkeypatch, stream=None, error=None):
    from rstools import updater

    class Opener:
        def open(self, req, timeout=None):
            if error is not None:
                raise error
            return stream
    monkeypatch.setattr(updater.urllib.request, "build_opener", lambda *a: Opener())


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def test_interrupted_and_short_downloads_leave_nothing_behind(tmp_path, monkeypatch):
    from rstools import updater
    dest = tmp_path / "TrainPlanningTools-9.9.9.exe"
    dest.write_bytes(b"previous download")
    body = b"MZ" + b"\0" * 5000
    serve(monkeypatch, Stream([body[:2000]], then=ConnectionResetError("reset by peer")))
    with pytest.raises(updater.UpdateError, match="download failed"):
        updater.download(_release(asset_size=len(body), digest="sha256:" + sha(body)), str(dest))
    assert sorted(os.listdir(tmp_path)) == [dest.name] and dest.read_bytes() == b"previous download"
    serve(monkeypatch, Stream([body[:3000]]))                          # the connection simply ends early
    with pytest.raises(updater.UpdateError, match="incomplete"):
        updater.download(_release(asset_size=len(body), digest="sha256:" + sha(body)), str(dest))
    assert sorted(os.listdir(tmp_path)) == [dest.name] and dest.read_bytes() == b"previous download"


def test_checksums_must_be_valid_and_match(tmp_path, monkeypatch):
    from rstools import updater
    body = b"MZ" + b"\x01" * 300
    good, notes = sha(body), f"Checked with SHA-256 {sha(body).upper()} for IT"
    dest = str(tmp_path / "new.exe")
    cases = [("", "", "no checksum"), ("sha256:abc", "", "no checksum"), ("md5:" + "a" * 32, "", "no checksum"),
             ("sha256:" + "z" * 64, "", "no checksum"), ("sha256:" + "0" * 64, notes, "did not match"),   # digest wins
             ("sha256:" + "f" * 63, "SHA-256 " + "e" * 64, "did not match")]
    for digest, text, says in cases:
        serve(monkeypatch, Stream([body]))
        with pytest.raises(updater.UpdateError, match=says):
            updater.download(_release(asset_size=len(body), digest=digest, notes=text), dest)
        assert os.listdir(tmp_path) == [], (digest, text)
    for digest, text in (("sha256:" + good.upper(), ""), ("sha256:short", notes), ("", notes)):    # accepted forms
        serve(monkeypatch, Stream([body]))
        assert updater.download(_release(asset_size=len(body), digest=digest, notes=text), dest) == dest
        os.remove(dest)


def test_downloads_that_are_not_windows_programs_are_refused(tmp_path, monkeypatch):
    from rstools import updater
    dest = str(tmp_path / "new.exe")
    for body in (b"", b"M", b"<html>Not found</html>", b'{"message": "Bad credentials"}', b"PK\x03\x04zip", b"\0MZ"):
        serve(monkeypatch, Stream([body] if body else []))
        with pytest.raises(updater.UpdateError, match="not a Windows program"):
            updater.download(_release(asset_size=len(body), digest="sha256:" + sha(body)), dest)
        assert os.listdir(tmp_path) == [], body


def test_a_download_redirected_to_plain_http_is_refused(tmp_path, monkeypatch):
    from rstools import updater
    headers = Message()
    headers["Location"] = "http://downloads.example/exe"
    serve(monkeypatch, error=urllib.error.HTTPError("https://api/asset", 302, "Found", headers, None))
    with pytest.raises(updater.UpdateError, match="not secure"):
        updater.download(_release(asset_size=10, digest="sha256:" + "0" * 64), str(tmp_path / "new.exe"))
    assert os.listdir(tmp_path) == []
    serve(monkeypatch, error=urllib.error.HTTPError("https://api/asset", 500, "Server Error", Message(), None))
    with pytest.raises(updater.UpdateError, match="download failed"):
        updater.download(_release(asset_size=10, digest="sha256:" + "0" * 64), str(tmp_path / "new.exe"))
    assert os.listdir(tmp_path) == []


def test_unexpected_release_replies_become_update_errors(monkeypatch):
    import json
    from rstools import updater

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def reply(payload):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: Reply(data))
    exe = updater.ASSET
    for payload, says in (({"tag_name": "v1", "assets": []}, "no TrainPlanningTools.exe"),
                          ({"tag_name": "v1", "assets": [{"name": "o.zip", "url": "u"}]}, "no TrainPlanningTools.exe"),
                          ({"tag_name": "v1", "assets": None}, "could not be read"),
                          ({"tag_name": "v1", "assets": [{"name": exe}]}, "could not be read"),
                          ({"tag_name": "v1", "assets": [{"name": exe, "url": "u", "size": "x"}]}, "could not be read"),
                          (b"<html>Service unavailable</html>", "Could not reach GitHub"),
                          ([], "could not be read")):
        reply(payload)
        with pytest.raises(updater.UpdateError, match=says):
            updater.latest_release()
    good = {"tag_name": "v2.0.1", "body": "notes", "html_url": "page",
            "assets": [{"name": exe, "url": "https://api/a", "size": 5, "digest": "sha256:" + "a" * 64}]}
    reply(good)
    rel = updater.latest_release()
    assert (rel.version, rel.asset_size, rel.asset_api) == ("2.0.1", 5, "https://api/a")
    for code, says in ((404, "did not allow access"), (403, "did not allow access"), (500, "HTTP 500")):
        def boom(*a, code=code, **k):
            raise urllib.error.HTTPError("u", code, "x", Message(), None)
        monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
        with pytest.raises(updater.UpdateError, match=says):
            updater.latest_release()
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    with pytest.raises(updater.UpdateError, match="Could not reach GitHub"):
        updater.latest_release()


@pytest.fixture
def install(tmp_path, monkeypatch):
    """A fake 'installed' exe and a downloaded replacement, with starting programs and the Windows check mocked."""
    from rstools import updater
    exe, new = tmp_path / "TrainPlanningTools.exe", tmp_path / "TrainPlanningTools.exe.new"
    exe.write_bytes(b"old version")
    new.write_bytes(b"new version")
    started, icons, scripts = [], [], []
    monkeypatch.setattr(updater, "running_exe", lambda: str(exe))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: started.append(a[0]))
    monkeypatch.setattr(updater, "refresh_icons", lambda e=None: icons.append(e))
    monkeypatch.setattr(updater, "_install_with_script", lambda n, e: scripts.append((n, e)))
    return exe, new, started, icons, scripts


def test_install_puts_the_new_version_in_place_and_starts_it(install):
    from rstools import updater
    exe, new, started, icons, scripts = install
    (exe.parent / (exe.name + ".old")).write_bytes(b"left from an earlier update")
    updater.install_and_restart(str(new))
    assert exe.read_bytes() == b"new version" and (exe.parent / (exe.name + ".old")).read_bytes() == b"old version"
    assert not new.exists() and started == [[str(exe)]] and icons == [str(exe)] and scripts == []


def test_a_failed_install_puts_the_current_version_back(install, monkeypatch):
    from rstools import updater
    exe, new, started, icons, scripts = install
    real = os.replace

    def cannot_move_new_in(src, dst):
        if str(src) == str(new):
            raise PermissionError("the file is locked")
        return real(src, dst)
    monkeypatch.setattr(updater.os, "replace", cannot_move_new_in)
    with pytest.raises(updater.UpdateError, match="unchanged"):
        updater.install_and_restart(str(new))
    assert exe.read_bytes() == b"old version" and new.read_bytes() == b"new version"      # nothing lost
    assert not (exe.parent / (exe.name + ".old")).exists()
    assert started == [] and icons == [] and scripts == []                                # and nothing started


def test_when_the_running_exe_cannot_be_renamed_the_script_takes_over(install, monkeypatch):
    from rstools import updater
    exe, new, started, icons, scripts = install
    real = os.replace

    def refuses_rename(src, dst):
        if str(src) == str(exe):
            raise PermissionError("a network share")
        return real(src, dst)
    monkeypatch.setattr(updater.os, "replace", refuses_rename)
    updater.install_and_restart(str(new))
    assert scripts == [(str(new), str(exe))] and started == []
    assert exe.read_bytes() == b"old version" and new.read_bytes() == b"new version"


def test_install_only_works_for_the_windows_exe(install, monkeypatch):
    from rstools import updater
    exe, new, *_ = install
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(updater.UpdateError, match="only works for the Windows exe"):
        updater.install_and_restart(str(new))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(updater, "running_exe", lambda: None)
    with pytest.raises(updater.UpdateError, match="only works for the Windows exe"):
        updater.install_and_restart(str(new))
    assert exe.read_bytes() == b"old version"


# --------------------------------------------------------------------------- 8. oversized and truncated inputs
def test_zip_limits_refuse_oversized_parts_before_unpacking(tmp_path, monkeypatch):
    from rstools import fsutil
    monkeypatch.setattr(fsutil, "ZIP_PART_LIMIT", 1000)
    p = make_zip(tmp_path / "x.zip", {"small.xml": b"<a/>", "big.xml": os.urandom(4000)})
    with zipfile.ZipFile(p) as z:
        assert fsutil.zip_read(z, "small.xml") == b"<a/>"
        with pytest.raises(fsutil.UnsafeFileError, match="unrealistic size"):
            fsutil.zip_read(z, "big.xml")
        with pytest.raises(fsutil.UnsafeFileError):
            fsutil.check_zip(z)
        fsutil.check_zip(z, "small.xml")                                  # one part can be checked on its own
    with pytest.raises(fsutil.UnsafeFileError):
        fsutil.check_office_file(p)
    plain = tmp_path / "plain.xlsb"
    plain.write_bytes(b"not a zip at all")
    fsutil.check_office_file(str(plain))                                  # not a zip: left to the reader to report


def hostile_and_cut(tmp_path):
    """Each reader with its own file type, the exception it must raise, and a make-the-file function."""
    import test_compare as tc
    import test_statspack as ts
    import test_stationbook as tsb
    import test_timetable as tt
    from cwn_compare.loader import LoadError, load_any
    from rstools.berthing.layout import read_chart
    from rstools.berthing.xmlread import BerthingError, read_xml
    from rstools.stationbook import StationBookError, read_plan
    from rstools.statspack.attune import AttuneError, parse_attune_xml
    from rstools.statspack.compare import PackReadError, read_pack
    from rstools.statspack.trent import TrentFormatError, parse_vehicle_layout
    from rstools.timetable.parse import TimetableError, read_timetable
    from rstools.timetable.prints import PrintError, read_print
    from rstools.timetable.section4 import Section4Error, read_statement
    from rstools.timetable.tpr import TPRError, read_tpr
    from rstools.timetable.trainlist import TrainListError, read_train_list
    from openpyxl import Workbook

    def xlsx(path):
        tc.make(path, tc.BTN_ORIG, tc.VIC_ORIG)

    def docx(path):
        ts.write_docx(path, ts.plan_lines())
    return {
        "xml": (tsb.write_xml, ".xml", [("stationbook", read_plan, StationBookError),
                                        ("statspack", parse_attune_xml, AttuneError),
                                        ("berthing", read_xml, BerthingError)]),
        "xlsx": (xlsx, ".xlsx", [("CWN", load_any, LoadError), ("timetable", read_timetable, TimetableError),
                                 ("train list", read_train_list, TrainListError),
                                 ("berthing chart", read_chart, BerthingError),
                                 ("stats pack", read_pack, PackReadError)]),
        "docx": (docx, ".docx", [("TRENT print", parse_vehicle_layout, TrentFormatError),
                                 ("train print", read_print, PrintError)]),
        "pdf": (lambda p: tt.write_s4_pdf(p, tt.S4_ROWS, notes=tt.S4_NOTES), ".pdf",
                [("Section 4", lambda p: read_statement([p]), Section4Error),
                 ("TPR", lambda p: read_tpr([p]), TPRError), ("train print", read_print, PrintError)]),
    }, Workbook


def test_empty_files_are_reported_by_every_reader(tmp_path):
    kinds, _wb = hostile_and_cut(tmp_path)
    for kind, (_make, ext, readers) in kinds.items():
        empty = tmp_path / f"empty{ext}"
        empty.write_bytes(b"")
        for name, read, error in readers:
            with pytest.raises(error):
                read(str(empty))
            assert str(empty) not in {str(p) for p in tmp_path.iterdir() if p != empty}, (kind, name)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f"empty{ext}" for _m, ext, _r in kinds.values())


def test_cut_off_files_never_end_in_a_traceback(tmp_path):
    """A download or copy that stopped half way: XML, Excel and Word files are reported in the reader's own words;
    a cut-off PDF is either reported or read as far as it goes, and no reader writes anything."""
    kinds, _wb = hostile_and_cut(tmp_path)
    for kind, (make, ext, readers) in kinds.items():
        whole = tmp_path / f"whole{ext}"
        make(str(whole))
        cut = tmp_path / f"cut{ext}"
        cut.write_bytes(whole.read_bytes()[: whole.stat().st_size // 2])
        before = sorted(os.listdir(tmp_path))
        for name, read, error in readers:
            try:
                read(str(cut))
            except error as exc:
                assert str(exc), (kind, name)
            else:
                assert kind == "pdf", f"{name} read a cut-off {kind} file without complaint"
        assert sorted(os.listdir(tmp_path)) == before, kind               # nothing was written or left behind


def test_oversized_archives_are_refused_by_every_zip_based_reader(tmp_path, monkeypatch):
    from rstools import fsutil
    kinds, _wb = hostile_and_cut(tmp_path)
    monkeypatch.setattr(fsutil, "ZIP_PART_LIMIT", 1000)                   # a few KB stand in for hundreds of MB
    for kind in ("xlsx", "docx"):
        _make, ext, readers = kinds[kind]
        parts = {"[Content_Types].xml": "<Types/>", "xl/workbook.xml": os.urandom(4000),
                 "word/document.xml": os.urandom(4000)}
        path = make_zip(tmp_path / f"hostile{ext}", parts)
        for name, read, error in readers:
            with pytest.raises(error) as caught:
                read(path)
            assert "unrealistic size" in str(caught.value) or kind == "docx", (kind, name, str(caught.value))
