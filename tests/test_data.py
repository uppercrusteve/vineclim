from __future__ import annotations

from pathlib import Path

import pytest

from vineclim.data import DataError, available_years, coverage, load_csv

from .conftest import write_csv


def test_missing_column_raises(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("date,tmin_c,tmax_c\n2024-01-01,1,2\n", encoding="utf-8")
    with pytest.raises(DataError, match="缺少必需列"):
        load_csv(path)


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(DataError, match="不存在"):
        load_csv(tmp_path / "nope.csv")


def test_empty_file_raises(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DataError):
        load_csv(path)


def test_duplicate_date_raises(tmp_path: Path):
    path = write_csv(
        tmp_path / "dup.csv",
        [("2024-01-01", 1.0, 2.0, 0.0), ("2024-01-01", 3.0, 4.0, 0.0)],
    )
    with pytest.raises(DataError, match="重复日期"):
        load_csv(path)


def test_invalid_date_raises(tmp_path: Path):
    path = tmp_path / "bad-date.csv"
    path.write_text("date,tmin_c,tmax_c,precip_mm\n2024-02-31,1,2,0\n", encoding="utf-8")
    with pytest.raises(DataError, match="无法解析日期"):
        load_csv(path)


def test_tmin_above_tmax_raises(tmp_path: Path):
    path = write_csv(tmp_path / "inverted.csv", [("2024-01-01", 9.0, 2.0, 0.0)])
    with pytest.raises(DataError, match="tmin_c 高于 tmax_c"):
        load_csv(path)


def test_unsorted_input_is_sorted(tmp_path: Path):
    path = write_csv(
        tmp_path / "unsorted.csv",
        [("2024-01-03", 1.0, 2.0, 0.0), ("2024-01-01", 3.0, 4.0, 0.0), ("2024-01-02", 5.0, 6.0, 0.0)],
    )
    frame = load_csv(path)
    assert list(frame["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-02", "2024-01-03"]


def test_power_fill_values_become_nan(tmp_path: Path):
    path = tmp_path / "fill.csv"
    path.write_text("date,tmin_c,tmax_c,precip_mm\n2024-01-01,-999,10,0\n", encoding="utf-8")
    frame = load_csv(path)
    assert frame.loc[0, "tmin_c"] != frame.loc[0, "tmin_c"]
    assert frame.loc[0, "tmax_c"] == pytest.approx(10.0)


def test_helpers_report_years_and_coverage(tmp_path: Path):
    path = write_csv(
        tmp_path / "years.csv",
        [("2023-06-01", 1.0, 2.0, 0.0), ("2024-06-01", 1.0, 2.0, 0.0)],
    )
    frame = load_csv(path)
    assert available_years(frame) == [2023, 2024]
    assert coverage(frame) == ("2023-06-01", "2024-06-01")


def test_available_years_fills_gap_years(tmp_path: Path):
    path = write_csv(
        tmp_path / "gap.csv",
        [("2023-06-01", 1.0, 2.0, 0.0), ("2025-06-01", 1.0, 2.0, 0.0)],
    )
    frame = load_csv(path)
    assert available_years(frame) == [2023, 2024, 2025]


def test_extra_columns_are_dropped(tmp_path: Path):
    path = tmp_path / "extra.csv"
    path.write_text("date,tmin_c,tmax_c,precip_mm,note\n2024-01-01,1,2,0,x\n", encoding="utf-8")
    frame = load_csv(path)
    assert list(frame.columns) == ["date", "tmin_c", "tmax_c", "precip_mm"]
