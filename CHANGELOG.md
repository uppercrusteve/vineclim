# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Missing-day fractions are computed against the calendar window instead of
  the rows that happen to exist, so a file with whole months missing is now
  flagged `insufficient_data` instead of passing as complete.
- Years without a single row between the first and last date are evaluated
  and reported as insufficient rather than silently skipped.
- Non-UTF-8 input now exits with a readable message instead of a traceback.

## [0.1.0] - 2026-11-17

### Added

- `vineclim compute` / `vineclim report` commands for daily minimum/maximum
  temperature CSV input, with JSON, CSV, Markdown report and PNG outputs.
- Indices: GDD10 (base 10 °C), Huglin heliothermal index with latitude
  coefficient, cool night index, frost days (annual, spring, autumn), hot
  days above 35 °C, growing-season length and growing-season diurnal range.
- Hemisphere-aware evaluation windows; southern-hemisphere sites use
  October–March for Huglin, March for the cool night index and mirrored
  frost windows.
- Missing-data handling: gaps are skipped and counted, and any metric/year
  with more than 20 % missing days is flagged `insufficient_data`.
- Optional, paired elevation correction (`--station-elev` / `--grid-elev`)
  using a configurable lapse rate. Uncorrected values are always retained.
- NASA POWER daily download command with retries, payload validation,
  fill-value mapping and optional metadata export.
- Publication-style figures: annual GDD, monthly frost calendar and monthly
  climatology, with explicit data-source notes.
- Example data: a NASA POWER grid extract for Deqin (2015–2025) and a
  synthetic station series with deliberate gaps.
- Validation of malformed input (missing columns, invalid dates, duplicate
  dates, Tmin above Tmax) and non-zero exit codes for errors.
- Test suite covering indices, input validation, POWER parsing/reporting and
  CLI behaviour; GitHub Actions CI for Linux and Windows on Python 3.11/3.12.

[0.1.0]: https://github.com/uppercrusteve/vineclim/releases/tag/v0.1.0
