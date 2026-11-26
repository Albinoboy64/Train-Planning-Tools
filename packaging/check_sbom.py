"""Check the release SBOM: valid CycloneDX JSON listing every runtime package pinned in
packaging/build-requirements.txt at exactly its pinned version, and the app at its current version.

    python packaging/check_sbom.py TrainPlanningTools.cdx.json

Exits with 1 (and says what is wrong) if anything is missing or different."""
from __future__ import annotations

import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_sbom import app_version, purl_name, runtime_pins  # noqa: E402


def problems(bom: dict, pins=None, version: str = "") -> List[str]:
    out: List[str] = []
    if bom.get("bomFormat") != "CycloneDX" or not str(bom.get("specVersion", "")).startswith("1."):
        out.append("not a CycloneDX 1.x document")
    have = {(purl_name(c.get("name", "")), c.get("version", "")) for c in bom.get("components", [])}
    purls = {c.get("purl", "") for c in bom.get("components", [])}
    for name, ver in pins if pins is not None else runtime_pins():
        if (purl_name(name), ver) not in have:
            out.append(f"{name}=={ver} is not in the SBOM at that version")
        if f"pkg:pypi/{purl_name(name)}@{ver}" not in purls:
            out.append(f"{name}=={ver} has no matching pkg:pypi purl")
    app = bom.get("metadata", {}).get("component", {})
    want = version or app_version()
    if app.get("name") != "TrainPlanningTools" or app.get("version") != want:
        out.append(f"the SBOM is not for TrainPlanningTools {want}")
    return out


def main(argv: List[str]) -> int:
    path = argv[0] if argv else "TrainPlanningTools.cdx.json"
    try:
        with open(path, encoding="utf-8") as fh:
            bom = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"SBOM check failed: {path} could not be read ({exc})")
        return 1
    found = problems(bom)
    for p in found:
        print("SBOM check failed:", p)
    if not found:
        print(f"SBOM check passed: {len(bom.get('components', []))} components, every runtime pin present")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
