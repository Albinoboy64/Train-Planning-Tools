\# Train Planning Tools — Project Rules



\## Stack \& Verification

\- \*\*Target runtime:\*\* Python 3.14 on Windows (`pyproject.toml`, `.github/workflows/build-windows.yml`, `build\_windows.bat`).

\- \*\*Required checks before finishing any task:\*\*

&#x20; 1. `ruff check .`

&#x20; 2. `mypy`

&#x20; 3. `pytest -q tests`



\## Security \& File-Safety Invariants

\- \*\*Local outputs only:\*\* Never write outputs to network or UNC paths (`\\\\server\\share` or mapped network drives). Always resolve output folders through `rstools.fsutil.output\_folder()` and validate `--out` with `\_local\_out()` in `TrainPlanningTools.py`.

\- \*\*Formula \& XML safety:\*\* All text copied from CWNs, XMLs, train lists, or PDFs must pass through `rstools.fsutil.clean\_cell()` and `rstools.fsutil.plain\_text()` so strings starting with `=`, `+`, `-`, or `@` are never stored as live Excel formulas.

\- \*\*Archive guards:\*\* Validate zipped Office inputs (`.xlsx`, `.xlsm`, `.xlsb`, `.docx`) with `rstools.fsutil.check\_office\_file()` or `rstools.fsutil.check\_zip()` before unpacking.

\- \*\*Atomic writes \& no overwrites:\*\* Never overwrite existing user outputs; use `unique\_stem()` and `atomic\_path()` / `write\_zip()`.



\## Architecture \& Consistency Rules

\- Keep all parsing, matching, calculation, and export logic inside `cwn\_compare/` and `rstools/`—never inside `gui.py` or `gui\_tab.py` modules.

\- \*\*CLI subcommands (`TrainPlanningTools.py`):\*\*

&#x20; - Raise domain errors (e.g., `RunError`, `ReorderError`, `StatsPackError`, `StationBookError`, `BerthingError`, `TimetableRunError`) inside helpers rather than calling `sys.exit()` directly.

&#x20; - Validate invalid flag combinations up front before reading large input files.

&#x20; - Add matching `.exe` smoke tests in both `.github/workflows/build-windows.yml` and `build\_windows.bat` for every new subcommand or major mode.

&#x20; - Document new subcommands and flags in `README.md`.

\- \*\*Live View parity:\*\* Expose any new comparison mode in `rstools/live/adapters.py` and `rstools/live/gui\_tab.py` using the same underlying matching engine as the reports.

\- \*\*Portable data:\*\* Keep user-editable files, settings, rule sets, and `error.log` inside `TrainPlanningTools-data` beside the executable (via `rstools.branding.settings\_dir()`), falling back to `%LOCALAPPDATA%\\TrainPlanningTools` when read-only.



\## Maintenance Commands (Timetable \& Rule Updates)

\- \*\*Rebuild built-in Section 4 rules\*\* (writes `rstools/timetable/section4\_builtin.json.gz` and its `.info.json` summary):

&#x20; `python -m rstools.rules SECTION4.pdf \[SECTION4.pdf ...]`

\- \*\*Rebuild built-in berthing chart layout\*\* (strips all train/unit data, keeping only sheets, berths, capacities, and notes in `rstools/berthing/default\_layout.json.gz`):

&#x20; `python -m rstools.berthing.layout CHART.xlsx`

\- \*\*Generate app icons\*\* (writes `.ico` and sized header/window PNGs):

&#x20; `python packaging/make\_icon.py`



\## Debloat \& Bugfix Pass Checklist

When asked for a cleanup, audit, or debloat pass:

1\. Check for duplicated helpers across `cwn\_compare/` and `rstools/` (especially Attune XML parsing in `statspack/attune.py`, `stationbook.py`, and `berthing/xmlread.py`, and workbook saving/path wrappers).

2\. Remove unused imports, dead parameters, unreachable branches, and stale references left behind by renamed flags or modes.

3\. Verify `pyproject.toml`, `build\_windows.bat`, `.github/workflows/build-windows.yml`, `packaging/TrainPlanningTools.spec`, and `README.md` are aligned on Python version, bundled data files, and CLI usage.

