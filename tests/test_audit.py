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
