"""Write the release's software bill of materials (SBOM) in CycloneDX 1.6 JSON.

    python packaging/make_sbom.py TrainPlanningTools.cdx.json

It lists what is inside TrainPlanningTools.exe: the app itself, the Python it is built with, and every package in
the '# the app' section of packaging/build-requirements.txt at its exact pinned version (with a pkg:pypi purl).
Test and build tools (pytest, ruff, PyInstaller...) are not shipped, so they are not listed. Only the requirements
file and the app's version are read: never settings, the data folder or any planning file. The output depends only
on those inputs, so the same commit always gives the same SBOM (apart from its timestamp and serial number)."""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import uuid
from typing import Dict, List, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REQUIREMENTS = os.path.join(ROOT, "packaging", "build-requirements.txt")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")
APP_SECTION = "# the app"


def runtime_pins(path: str = REQUIREMENTS) -> List[Tuple[str, str]]:
    """(name, version) of each package in the requirements file's '# the app' section, in file order."""
    pins: List[Tuple[str, str]] = []
    inside = False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("#"):
                inside = line.lower().startswith(APP_SECTION)
                continue
            if inside and line:
                m = re.match(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+!]+)$", line.split("#")[0].strip())
                if not m:
                    raise ValueError(f"'{line}' in {os.path.basename(path)} is not pinned as name==version")
                pins.append((m.group(1), m.group(2)))
    if not pins:
        raise ValueError(f"No '{APP_SECTION}' packages found in {path}")
    left_out = excluded_packages()
    return [(n, v) for n, v in pins if n.lower().replace("-", "_") not in left_out]


SPEC = os.path.join(ROOT, "packaging", "TrainPlanningTools.spec")


def excluded_packages(path: str = SPEC) -> set:
    """Top-level packages the spec leaves out of the exe (its EXCLUDES list, read as text: the spec needs
    PyInstaller to run). A package installed for the build but not bundled is not in the bill of materials."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return set()
    m = re.search(r"^EXCLUDES = \[(.*?)^\]", text, re.S | re.M)
    names = re.findall(r'"([A-Za-z0-9_.]+)"', m.group(1)) if m else []
    return {n.lower() for n in names if "." not in n}


def python_version(path: str = WORKFLOW) -> str:
    """The Python version the release is built with (the workflow's python-version)."""
    with open(path, encoding="utf-8") as fh:
        m = re.search(r'python-version:\s*"([\d.]+)"', fh.read())
    return m.group(1) if m else f"{sys.version_info.major}.{sys.version_info.minor}"


def app_version() -> str:
    with open(os.path.join(ROOT, "cwn_compare", "__init__.py"), encoding="utf-8") as fh:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', fh.read())
    if not m:
        raise ValueError("__version__ not found in cwn_compare/__init__.py")
    return m.group(1)


def purl_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()        # PEP 503 normalised, as the pypi purl type expects


def build(pins: List[Tuple[str, str]], python: str, version: str) -> Dict:
    components = [{"type": "framework", "bom-ref": f"python@{python}", "name": "python", "version": python,
                   "purl": f"pkg:generic/python@{python}", "description": "CPython, bundled by PyInstaller"}]
    for name, ver in pins:
        components.append({"type": "library", "bom-ref": f"pkg:pypi/{purl_name(name)}@{ver}", "name": name,
                           "version": ver, "purl": f"pkg:pypi/{purl_name(name)}@{ver}"})
    app_ref = f"TrainPlanningTools@{version}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": [{"type": "application", "name": "make_sbom.py",
                                      "description": "Train Planning Tools packaging script"}]},
            "component": {"type": "application", "bom-ref": app_ref, "name": "TrainPlanningTools",
                          "version": version, "description": "Train Planning Tools portable Windows app"},
        },
        "components": components,
        "dependencies": [{"ref": app_ref, "dependsOn": [c["bom-ref"] for c in components]}],
    }


def main(argv: List[str]) -> int:
    out = argv[0] if argv else "TrainPlanningTools.cdx.json"
    bom = build(runtime_pins(), python_version(), app_version())
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(bom, fh, indent=2)
        fh.write("\n")
    print(f"SBOM: {out} ({len(bom['components'])} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
