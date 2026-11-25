# Developer setup and validation

## Supported build environment

The supported release build uses Python 3.14.6 as configured in `.github/workflows/build-windows.yml` and the exact package versions in `packaging/build-requirements.txt`. Those pins are the tested release-build environment; `requirements.txt` contains minimum versions for running from source.

## Run the app from source

```powershell
python -m pip install -r requirements.txt
python TrainPlanningTools.py
```

## Run the same checks as CI

Install the exact packages from `packaging/build-requirements.txt` in a clean environment, then run:

```powershell
ruff check .
mypy
python -m pytest -q tests
```

The Windows GitHub Actions workflow additionally builds the portable executable and runs packaged-app smoke tests. For changes to packaging, CLI entry points, file readers, or output generation, check the workflow's smoke tests as well as the unit tests. Test data must be synthetic; do not commit real CWNs, XML exports, train prints, timetables, or other sensitive operational data.

## Repository settings for maintainers

Protect `main` in the repository's Branch protection rules or Rulesets settings. Require the Windows build workflow's checks before merging, disallow force pushes and branch deletion, and require review if there are additional maintainers. GitHub branch protection cannot be configured from repository files.

Keep Actions permissions least-privilege. The current build workflow also publishes GitHub Releases, so it needs `contents: write`; if the build is separated from release publishing, make the build job `contents: read` and grant `contents: write` only to the release job. Do not grant write access to jobs that only lint, type-check, test, or build.

## Dependency updates

Use a separate change for dependency updates. Update the tested pins in `packaging/build-requirements.txt` deliberately, run the full Windows workflow, and only then consider changing the source-install minimums in `requirements.txt`. Dependabot PRs for major GitHub Actions updates should be checked against the Windows runner and Node runtime requirements before merging.
