from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from vineclim.data import load_csv
from vineclim.indices import ElevationCorrection, compute_indices


def make_frame(rows: list[tuple[str, float | None, float | None, float | None]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["date", "tmin_c", "tmax_c", "precip_mm"])
    frame["date"] = pd.to_datetime(frame["date"])
    for column in ("tmin_c", "tmax_c", "precip_mm"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("date").reset_index(drop=True)


def write_csv(path: Path, rows: list[tuple[str, float | None, float | None, float | None]]) -> Path:
    frame = make_frame(rows)
    frame.to_csv(path, index=False)
    return path


def compute(rows, latitude=45.0, years=None, correction=None):
    frame = make_frame(rows)
    return compute_indices(frame, latitude, years=years, correction=correction)


def entry(result, year: int, metric: str):
    for item in result["years"]:
        if item["year"] == year:
            return item["indices"][metric]
    raise KeyError(year)


@pytest.fixture
def three_day_rows():
    return [
        ("2024-04-01", 10.0, 16.0, 0.0),
        ("2024-04-02", 12.0, 20.0, 0.0),
        ("2024-04-03", 8.0, 12.0, 0.0),
    ]


@pytest.fixture
def synthetic_path(tmp_path: Path) -> Path:
    rows = [("2024-01-01", 0.0, 10.0, 0.0), ("2024-01-02", -2.0, 8.0, 1.0)]
    path = tmp_path / "station.csv"
    write_csv(path, rows)
    return path


@pytest.fixture
def correction() -> ElevationCorrection:
    return ElevationCorrection(station_elev_m=2000.0, grid_elev_m=3000.0, lapse_c_per_km=6.5)


def load(path: Path):
    return load_csv(path)
