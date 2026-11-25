# Developer setup and validation

## Supported build environment

The supported release build uses the Python version configured in `.github/workflows/build-windows.yml` and the exact package versions in `packaging/build-requirements.txt`. Those pins are the tested release toolchain. `requirements.txt` intentionally contains minimum versions for installing the app from source; do not copy build-tool pins into it without checking the supported Python versions and running the full suite.

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

The Windows GitHub Actions workflow additionally builds the portable executable and runs packaged-app smoke tests. For changes to packaging, CLI entry points, file readers, or output generation, check that workflow as well as the unit tests before merging.

## Dependency updates

Use a separate change for dependency updates. Update the tested pins in `packaging/build-requirements.txt` deliberately, run the full Windows workflow, and only then consider changing the source-install requirements. Keep this distinction so a release-toolchain update does not silently change the install experience or supported Python versions.
