"""Release checks that run with the tests: the SBOM lists the pinned runtime packages, the exe bundles no planning
data or personal files, and every place that names the Python version agrees."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packaging"))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_sbom_lists_every_pinned_runtime_package(tmp_path):
    import check_sbom
    import make_sbom
    pins = make_sbom.runtime_pins()
    names = {n for n, _v in pins}
    assert {"openpyxl", "pypdf", "pypdfium2", "reportlab", "tkinterdnd2"} <= names
    assert not names & {"pytest", "ruff", "mypy", "pyinstaller", "pytest-cov", "coverage"}    # not shipped
    out = str(tmp_path / "sbom.cdx.json")
    assert make_sbom.main([out]) == 0
    bom = json.load(open(out, encoding="utf-8"))
    assert bom["bomFormat"] == "CycloneDX" and bom["specVersion"] == "1.6"
    assert bom["metadata"]["component"]["version"] == make_sbom.app_version()
    for name, ver in pins:
        purl = f"pkg:pypi/{make_sbom.purl_name(name)}@{ver}"
        assert any(c["name"] == name and c["version"] == ver and c["purl"] == purl for c in bom["components"]), name
    python = next(c for c in bom["components"] if c["name"] == "python")
    assert python["version"] == make_sbom.python_version()
    assert check_sbom.main([out]) == 0
    assert check_sbom.problems(bom) == []


def test_sbom_check_fails_on_a_missing_or_wrong_pin(tmp_path):
    import check_sbom
    import make_sbom
    bom = make_sbom.build(make_sbom.runtime_pins(), "3.14.6", make_sbom.app_version())
    wrong = json.loads(json.dumps(bom))
    c = next(c for c in wrong["components"] if c["name"] == "openpyxl")
    c["version"] = "0.0.1"
    assert any("openpyxl" in p for p in check_sbom.problems(wrong))
    missing = json.loads(json.dumps(bom))
    missing["components"] = [c for c in missing["components"] if c["name"] != "pypdf"]
    assert any("pypdf" in p for p in check_sbom.problems(missing))
    other = json.loads(json.dumps(bom))
    other["metadata"]["component"]["version"] = "0.0"
    assert check_sbom.problems(other)
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    assert check_sbom.main([str(path)]) == 1


def test_sbom_refuses_an_unpinned_runtime_package(tmp_path):
    import pytest
    import make_sbom
    req = tmp_path / "req.txt"
    req.write_text("# the app\nopenpyxl>=3\n# tests and checks\npytest==9\n")
    with pytest.raises(ValueError, match="not pinned"):
        make_sbom.runtime_pins(str(req))
    req.write_text("# tests and checks\npytest==9\n")
    with pytest.raises(ValueError, match="No"):
        make_sbom.runtime_pins(str(req))


SHIPPED_OK = (".png", ".csv", ".json", ".json.gz", ".ico")
SHIPPED_NAMES = {"THIRD_PARTY_NOTICES.txt", "template.xlsx"}      # licences; the empty TT Comparison template
NEVER = (".xml", ".xls", ".xlsx", ".xlsm", ".xlsb", ".docx", ".doc", ".pdf", ".vpt", ".pif", ".log", ".txt", ".zip")


def test_exe_bundles_no_planning_data_or_personal_files():
    """The spec bundles every non-Python file under rstools/: each must be a known kind of built-in asset, so a
    real CWN, XML, print, VPT, settings file or log left in the source tree can never be shipped."""
    spec = _read("packaging", "TrainPlanningTools.spec")
    assert 'os.walk(os.path.join(ROOT, "rstools"))' in spec        # what the check below mirrors
    shipped = []
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "rstools")):
        if "__pycache__" in folder:
            continue
        shipped += [os.path.relpath(os.path.join(folder, n), ROOT) for n in files if not n.endswith((".py", ".pyc"))]
    assert shipped
    for rel in shipped:
        name = os.path.basename(rel)
        assert "TrainPlanningTools-data" not in rel and not name.lower().startswith(("settings", "error")), rel
        if name in SHIPPED_NAMES:
            continue
        assert name.lower().endswith(SHIPPED_OK) and not name.lower().endswith(NEVER), rel
    datas = re.findall(r"datas=([^\n]+)", spec)
    assert datas and "TrainPlanningTools-data" not in spec and "settings_dir" not in spec


def test_python_version_is_the_same_everywhere():
    """ruff, mypy, the release workflow and build_windows.bat all target the same Python (3.14)."""
    py = _read("pyproject.toml")
    wf = _read(".github", "workflows", "build-windows.yml")
    bat = _read("build_windows.bat")
    ruff = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', py)
    mypy = re.search(r'python_version\s*=\s*"(\d+\.\d+)"', py)
    pins = set(re.findall(r'python-version:\s*"(\d+\.\d+)(?:\.\d+)?"', wf))
    bat_ver = re.search(r"sys\.version_info\[:2\] == \((\d+), (\d+)\)", bat)
    assert ruff and mypy and pins and bat_ver
    target = f"{ruff.group(1)}.{ruff.group(2)}"
    assert target == "3.14"
    assert mypy.group(1) == target and pins == {target} and f"{bat_ver.group(1)}.{bat_ver.group(2)}" == target


def test_audit_and_build_pins_are_separate():
    build = _read("packaging", "build-requirements.txt")
    audit = _read("packaging", "audit-requirements.txt")
    assert "pip-audit" not in build and re.search(r"^pip-audit==[\d.]+$", audit, re.M)
    for line in build.splitlines():
        line = line.split("#")[0].strip()
        assert not line or re.match(r"^[A-Za-z0-9_.\-]+==[\w.\-+!]+$", line), line    # every build package pinned


def test_promote_checks_the_merge_and_skips_dependabot():
    """Any account's branch is merged into main after a green build; a merge commit is checked before it is pushed."""
    wf = _read(".github", "workflows", "build-windows.yml")
    job = wf[wf.index("\n  promote:"):]
    cond = job[job.index("if: >-"):job.index("runs-on:")]
    assert "refs/heads/main" in cond and "dependabot[bot]" in cond
    assert "claude/" not in cond                            # every branch, from any account, not only claude/**
    assert "ruff check . && mypy && python -m pytest -q tests" in job
    assert job.index("check_merge") < job.index('git push origin "$target:refs/heads/main"')
    assert "back to" in job and "for attempt in 1 2" in job
