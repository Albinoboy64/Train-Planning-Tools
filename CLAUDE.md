# Train Planning Tools — Project Rules

## Stack and verification

- **Target runtime:** Python 3.14 on Windows (`pyproject.toml`, `.github/workflows/build-windows.yml`, `build_windows.bat`).
- **Required checks before finishing any task:**
  1. `ruff check .`
  2. `mypy`
  3. `pytest -q tests`

## Security and file-safety invariants

- **Local outputs only:** never write outputs to network or UNC paths (`\\server\share` or mapped network drives). Resolve output folders through `rstools.fsutil.output_folder()` and support the app's portable Downloads behaviour.
- **Formula and XML safety:** all text copied from CWNs, XMLs, train lists, or PDFs must pass through `rstools.fsutil.clean_cell()` and `rstools.fsutil.plain_text()` so strings beginning with `=`, `+`, `-`, or `@` remain text. Strip control characters that could make output files invalid.
- **Archive guards:** validate zipped Office inputs (`.xlsx`, `.xlsm`, `.xlsb`, `.docx`) with `rstools.fsutil.check_office_file()` or `rstools.fsutil.check_zip()` before unpacking.
- **Atomic writes and no overwrites:** never overwrite existing user outputs. Use `unique_stem()` and `atomic_path()` / `write_zip()`.
- **Unique temporary files:** temporary probe and write files must be created securely and uniquely. Never open or overwrite a predictable filename, and always remove it afterwards.
- **Real planning data:** never commit real CWNs, TRENT prints, Attune XML, or other sensitive timetable data. Use synthetic fixtures only. Repository ignore rules must cover relevant Office and XML files in all directories, not only the repository root.

## Architecture and consistency rules

- Keep parsing, matching, calculation, and export logic in `cwn_compare/` and `rstools/`, never in `gui.py` or `gui_tab.py` modules.
- **CLI subcommands (`TrainPlanningTools.py`):**
  - Raise domain errors (for example `RunError`, `ReorderError`, `StatsPackError`, `StationBookError`, `BerthingError`, or `TimetableRunError`) inside helpers rather than calling `sys.exit()` directly.
  - Validate invalid flag combinations up front before reading large input files.
  - Add matching `.exe` smoke tests to both `.github/workflows/build-windows.yml` and `build_windows.bat` for every new subcommand or major mode.
  - Document new subcommands and flags in `README.md`.
- **Live View parity:** expose any new comparison mode in `rstools/live/adapters.py` and `rstools/live/gui_tab.py`, using the same underlying matching engine as the reports.
- **Portable data:** keep user-editable files, settings, rule sets, and `error.log` inside `TrainPlanningTools-data` beside the executable (via `rstools.branding.settings_dir()`), falling back to an app-local or platform-appropriate location when needed.

## Maintenance commands

- Rebuild built-in Section 4 rules (writes `rstools/timetable/section4_builtin.json.gz` and `rstools/timetable/section4_builtin.info.json`):
  `python -m rstools.rules SECTION4.pdf [SECTION4.pdf ...]`
- Rebuild the built-in berthing chart layout (keeps sheets, berths, capacities, and notes, but removes train/unit data):
  `python -m rstools.berthing.layout CHART.xlsx`
- Generate app icons:
  `python packaging/make_icon.py`

## Audit follow-up checklist

Before finishing a bugfix or audit pass:

1. For any writable-folder check, use a uniquely named temporary file, and cover it with a synthetic test that places an unrelated file at the probe path and confirms it is left unchanged.
2. Review `.gitignore` for repository-wide coverage of real timetable data, especially `*.xml`, `*.xlsx`, `*.xls*`, `*.docx`, and portable data directories.
3. Test ignore-rule coverage using sample nested XML and Office files, ensuring real planning fixtures stay untracked while synthetic test fixtures remain in `tests/`.
4. Check that the packaged executable and source build use the same pinned dependencies (`packaging/build-requirements.txt`).

## Cleanup and bugfix checklist

When asked for a cleanup, audit, or debloat pass:

1. Check for duplicated helpers across `cwn_compare/` and `rstools/`, especially Attune XML parsing, workbook saving, and path helpers.
2. Remove dead parameters, unreachable branches, and stale references left behind by renamed flags or modes.
3. Verify `pyproject.toml`, `build_windows.bat`, `.github/workflows/build-windows.yml`, `packaging/TrainPlanningTools.spec`, and `README.md` agree on the Python version (checked by `tests/test_release.py`), bundled data files, and packaging steps.
4. Preserve synthetic test coverage for parsing and output behaviour; real CWN, TRENT, or Attune data must not be committed.
