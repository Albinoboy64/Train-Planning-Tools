"""Tests for the shared helpers: parallel ZIP writer, updater logic, and default names."""
import os
import tempfile
import zipfile

from rstools import naming, updater
from rstools.zipw import write_zip


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
