# Pull request

## What does this change do?

<!-- Summarize the change and its motivation. -->

## How was it tested?

- [ ] `ruff check .`
- [ ] `mypy`
- [ ] `python -m pytest -q tests`
- [ ] Windows executable build/smoke test, if applicable

## Data and security checklist

- [ ] Tests and examples use synthetic data; no real train plans, CWNs, timetables, or customer data are included.
- [ ] Input-derived text remains plain text in generated workbooks/documents (not executable formulas or markup).
- [ ] File handling and output paths are covered for relevant edge cases.
- [ ] Dependency or GitHub Actions updates were reviewed for compatibility and permissions.
