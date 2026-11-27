"""Fixes from the 3.38.6 audit: formula text, XML declarations in any encoding, outputs never written over,
atomic rule sets, batch names, settings that are not a dict. Synthetic data only."""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_save_workbook_keeps_formula_like_text_as_text(tmp_path):
    import zipfile
    from openpyxl import Workbook
    from rstools.xlsave import save_workbook
    wb = Workbook()
    wb.active["A1"] = '=HYPERLINK("http://example.invalid","x")'
    assert wb.active["A1"].data_type == "f"
    out = tmp_path / "out.xlsx"
    save_workbook(wb, str(out))
    with zipfile.ZipFile(out) as z:
        text = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/") and n.endswith(".xml"))
    assert "<f>" not in text and "HYPERLINK" in text


@pytest.mark.parametrize("enc", ["utf-8", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"])
def test_declarations_refused_in_every_encoding(enc):
    from rstools import safexml
    x = '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "boom">]><a>&e;</a>'
    with pytest.raises(safexml.UnsafeXMLError):
        safexml.fromstring(x.encode(enc))


@pytest.mark.parametrize("enc", ["utf-8", "utf-16-le", "utf-16-be", "utf-16"])
def test_plain_xml_still_read_in_every_encoding(enc):
    from rstools import safexml
    assert safexml.fromstring("<a>x</a>".encode(enc)).text == "x"


def test_write_zip_never_replaces_a_file_already_there(tmp_path):
    from rstools.zipw import write_zip
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"someone else's file")
    with pytest.raises(FileExistsError):
        write_zip(str(target), [("a.xml", b"<a/>")])
    assert target.read_bytes() == b"someone else's file"
    assert [p.name for p in tmp_path.iterdir()] == ["out.xlsx"]        # the temporary file was removed


def test_rule_set_write_is_atomic(tmp_path, monkeypatch):
    from rstools import rules
    path = tmp_path / "set.json.gz"
    rules._write_gz(str(path), {"a": 1})

    class Boom(Exception):
        pass

    def bad_dump(*_a, **_k):
        raise Boom()
    monkeypatch.setattr(rules.json, "dump", bad_dump)
    with pytest.raises(Boom):
        rules._write_gz(str(path), {"a": 2})
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        assert json.load(fh) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["set.json.gz"]


def test_batch_pairs_with_the_same_name_get_distinct_names():
    from cwn_compare.batch import _distinct_names
    pairs = [("a/CWN 1.xlsx", "b/CWN 1.xlsx"), ("c/CWN 1.xlsx", "d/CWN 1.xlsx"), ("e/X.xlsx", "f/Y.xlsx")]
    names = _distinct_names(pairs)
    assert names[0] == "" and names[1].endswith(" (2)") and names[2] == ""


@pytest.mark.parametrize("text", ["null", "[]", '"x"', '{"categories": [1, 2]}', '{"categories": {"A": 3}}'])
def test_options_load_survives_odd_settings(tmp_path, monkeypatch, text):
    from cwn_compare.options import Options
    p = tmp_path / "settings.json"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setattr(Options, "settings_path", staticmethod(lambda: str(p)))
    opts = Options.load()
    assert isinstance(opts, Options) and isinstance(opts.categories, dict)


def test_live_confirmation_survives_a_view_option_change():
    """Ticking 'check header/timing differences' or error checking on / off changes how a train is marked,
    not its details: its confirmation stays. A corrected detail still takes the tick off."""
    from rstools.live import progress as P
    from rstools.live.model import LiveItem, LiveResult, LiveRow, view
    it = LiveItem("k", "G", "1A01", "changed", "Time changed", [LiveRow(["Time", "0600", "0610"], "changed")])
    confirmed = {"k": P.fingerprint(it)}
    marked_other_way = LiveItem("k", "G", "1A01", "same", "No change", [LiveRow(["Time", "0600", "0610"])])
    assert P.reconcile(confirmed, [marked_other_way]) == (confirmed, set())
    paired = view(LiveResult("t", ["F", "A", "B"], [it]), check=False).items[0]
    assert P.reconcile(confirmed, [paired]) == (confirmed, set())
    fixed = LiveItem("k", "G", "1A01", "same", "No change", [LiveRow(["Time", "0610", "0610"])])
    assert P.reconcile(confirmed, [fixed]) == ({}, {"k"})


def test_live_confirmation_saved_before_3_38_6_still_accepted():
    from rstools.live import progress as P
    from rstools.live.model import LiveItem, LiveRow
    it = LiveItem("k", "G", "1A01", "same", "No change", [LiveRow(["Time", "0600", "0600"])])
    kept, changed = P.reconcile({"k": P._legacy_fingerprint(it)}, [it])
    assert kept == {"k": P.fingerprint(it)} and not changed


def test_wheel_over_a_task_box_does_not_change_the_task():
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from rstools.widgets import ScrollPage
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        page = ScrollPage(root)
        page.pack(fill="both", expand=True)
        box = ttk.Combobox(page.body, values=["compare", "batch", "reorder"], state="readonly")
        box.set("compare")
        box.pack()
        root.update()
        for seq, kw in (("<MouseWheel>", {"delta": -120}), ("<Button-5>", {})):
            try:
                box.event_generate(seq, x=5, y=5, **kw)
            except tk.TclError:
                continue
            root.update()
            assert box.get() == "compare"
    finally:
        root.destroy()


@pytest.mark.parametrize("cmd,args", [
    ("statspack", ["--xml", "missing.xml", "--unit-reports", "washes,nonsense"]),
    ("statspack", ["--xml", "missing.xml", "--unit-reports", ","]),
    ("statspack", ["--xml", "missing.xml", "--capacity-group", "1F", "--capacity-corridor", "X"]),
    ("statspack", ["--xml", "missing.xml", "--capacity-from", "Brighton"]),
    ("statspack", ["--xml", "missing.xml", "--capacity-group", "1F", "--unit-reports", "washes"]),
    ("statspack", ["--xml", "missing.xml", "--capacity-group", "1F", "--no-seating", "--no-standing"]),
    ("statspack", ["--xml", "missing.xml", "--no-summary"]),
    ("statspack", ["--xml", "missing.xml", "--corridor-direction", "reverse"]),
    ("statspack", ["--old-pack", "a.xlsx", "--new-pack", "b.xlsx", "--old-xml", "c.xml"]),
    ("statspack", ["--xml", "missing.xml", "--capacity-group", "1F", "--between", "07:00-07:00", "--at", "X"]),
    ("stationbook", ["--xml", "missing.xml", "--station", "Alpha", "--sheets", "SX,XX"]),
    ("timetable", ["--gtr", "a.xlsx", "--nr", "b.xlsx", "--check", "c.xlsx"]),
    ("timetable", ["--prints", "a.pdf", "--vs", "b.pdf", "--nr", "c.xlsx"]),
    ("timetable", ["--gtr", "a.xlsx", "--nr", "b.xlsx", "--vs", "c.pdf"]),
    ("", ["--original-folder", "a", "--updated", "b", "--name", "x"]),
])
def test_cli_refuses_flags_that_do_not_go_together(cmd, args, capsys):
    """Refused up front (exit code 2, before any file is read: none of these files exists)."""
    import TrainPlanningTools as cli
    with pytest.raises(SystemExit) as exc:
        cli.main(([cmd] if cmd else []) + args)
    assert exc.value.code == 2, capsys.readouterr()


def test_cli_unknown_corridor_refused_before_the_plan_is_read(capsys):
    import TrainPlanningTools as cli
    with pytest.raises(SystemExit) as exc:
        cli.main(["statspack", "--xml", "missing.xml", "--trent", "missing.docx",
                  "--capacity-corridor", "No Such Corridor Anywhere"])
    out = capsys.readouterr().out
    assert exc.value.code == 1 and "is not known" in out and "missing" not in out.lower().split("error:")[0]


def test_every_command_line_flag_is_in_the_readme():
    """The README's command-line section names every option of every command (hidden ones aside)."""
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "TrainPlanningTools.py"), encoding="utf-8") as fh:
        src = fh.read()
    with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    start = readme.index("## Command line (optional)")
    section = readme[start:readme.index("\n## ", start + 5)]
    hidden = set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"[^)]*SUPPRESS', src))
    flags = set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', src)) - hidden
    assert flags and not sorted(f for f in flags if f not in section)
    for command in re.search(r"COMMANDS = \(([^)]*)\)", src).group(1).replace('"', "").replace("\n", " ").split(","):
        assert command.strip() in section


def test_gitignore_covers_planning_data_in_any_letter_case():
    """Real planning data is ignored in every folder and letter case; the app's own tables and the synthetic
    fixtures stay tracked."""
    import shutil
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if shutil.which("git") is None or not os.path.isdir(os.path.join(root, ".git")):
        pytest.skip("not a git checkout")

    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=root).returncode == 0
    for path in ("a.xml", "deep/x/b.XML", "c.XLSX", "d.xltx", "e.xlsm", "f.docx", "g.DOCM", "h.pdf", "i.PDF",
                 "j.vpt", "k.CIF", "trains.csv", "nested/list.CSV", "TrainPlanningTools-data/settings.json",
                 "x/TrainPlanningTools-data/error.log"):
        assert ignored(path), path
    for path in ("rstools/statspack/fleet_default.csv", "rstools/timetable/template.xlsx",
                 "tests/fixtures/synthetic_cwn.xls", "packaging/TrainPlanningTools.spec", "README.md"):
        assert not ignored(path), path
