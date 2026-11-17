# Contributing

Thanks for taking an interest in vineclim. This is a small scientific tool,
so correctness, explicit assumptions and honest data labelling matter more
than feature count.

## Development setup

Requires Python 3.10 or newer (CI runs 3.11 and 3.12).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
ruff check .
```

All commands must pass before a pull request is reviewed.

## What to run

```bash
pytest -q          # full test suite
ruff check .       # lint
ruff format --check .   # optional, formatting only
```

New behaviour needs a test that would fail without the change. Blanket
`assert result` checks are not enough: assert concrete values, statuses or
error messages. Boundary cases (exactly 20 % missing, hemisphere windows,
leap days, invalid coordinates) are explicitly covered today; keep them
covered.

## Data conventions

- Input CSV columns are exactly `date,tmin_c,tmax_c,precip_mm`.
  Dates use `YYYY-MM-DD`; temperatures are °C.
- Empty cells and the POWER fill values `-999` / `-9999` mean missing.
- Never present grid data as a vineyard measurement. New examples must say
  whether they are station observations, public grid data or synthetic.
- Synthetic series must be reproducible and documented as synthetic.
- Accumulated indices are in °C·d; threshold counts are in days. Do not
  silently change units or base temperatures.

## Scientific changes

A change to a formula, evaluation window, missing-data rule or
classification must update `docs/methods.md` with the definition, unit,
source and effect on comparability. If a published definition is ambiguous,
state the interpretation chosen rather than silently picking one.

## Reporting issues

Please include:

- operating system and Python version;
- the exact command;
- a minimal CSV excerpt that reproduces the problem (remove sensitive
  station data if needed);
- the full error output and exit code.

Feature requests should describe the research workflow they support. Broad
platform additions (web UI, databases) are welcome if they do not add heavy
dependencies.

## Pull requests

- One topic per pull request; keep diffs reviewable.
- Do not commit generated `out/` directories or caches.
- Update `CHANGELOG.md` under an "Unreleased" heading for user-visible
  changes.
- By contributing you agree that your contribution is licensed under the
  MIT License.
