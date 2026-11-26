# Developer setup and validation

## Supported build environment

The supported release build uses Python 3.14.6 as configured in `.github/workflows/build-windows.yml` and the exact package versions in `packaging/build-requirements.txt`. Those pins are the tested release-build environment; `requirements.txt` contains minimum versions for running from source.

## Run the app from source

```powershell
python -m pip install -r requirements.txt
python TrainPlanningTools.py
```

## Run the same checks as CI

Install the exact packages from `packaging/build-requirements.txt` in a clean environment (`pip install --no-deps -r packaging/build-requirements.txt`), then run:

```powershell
ruff check .
mypy
python -m pytest -q tests --cov --cov-report=term-missing
```

The coverage run fails under the floor set in `pyproject.toml`; raise the floor as coverage grows. The dependency audit uses its own pins:

```powershell
python -m pip install -r packaging/audit-requirements.txt
pip-audit --strict --disable-pip --no-deps -r packaging/build-requirements.txt
```

CI (`.github/workflows/build-windows.yml`) runs these as separate jobs: **lint**, **typecheck**, **test** (with coverage) and **audit**. Only when all four pass does the **build** job make the portable executable, run the packaged-app smoke tests, make the CycloneDX SBOM and checksums and, for a new version, publish the release; the **promote** job then merges a green `claude/**` branch into `main`. `.github/workflows/codeql.yml` runs CodeQL code scanning separately. `build_windows.bat` runs the same checks and smoke tests locally (Python 3.14 needed). For changes to packaging, CLI entry points, file readers, or output generation, add or check the smoke tests in both the workflow and `build_windows.bat` as well as the unit tests. Test data must be synthetic; do not commit real CWNs, XML exports, train prints, timetables, or other sensitive operational data.

## Repository settings for maintainers

Protect `main` in the repository's Branch protection rules or Rulesets settings. Require the Windows build workflow's checks before merging, disallow force pushes and branch deletion, and require review if there are additional maintainers. GitHub branch protection cannot be configured from repository files.

Keep Actions permissions least-privilege. The workflow's default is `contents: write` because the `build` job publishes GitHub Releases (it also needs `id-token: write` and `attestations: write` for the build provenance attestation) and `promote` merges into `main`. The `lint`, `typecheck`, `test` and `audit` jobs only read the repository; if the build and the release are ever split into separate jobs, give `contents: write` to the release job only. The `build` job of `main` uses a concurrency group so two builds can never publish a version at the same time. Releases carry `TrainPlanningTools.cdx.json` (SBOM) and `SHA256SUMS.txt`; a new runtime package must be pinned in the `# the app` section of `packaging/build-requirements.txt` so it appears in the SBOM (`tests/test_release.py` checks this).

## Dependency updates

Use a separate change for dependency updates. Update the tested pins in `packaging/build-requirements.txt` deliberately, run the full Windows workflow, and only then consider changing the source-install minimums in `requirements.txt`. Dependabot (`.github/dependabot.yml`) proposes updates for the pinned packages and the GitHub Actions; its PRs for major Actions updates should be checked against the Windows runner and Node runtime requirements before merging, and a bumped package must pass the audit job.
