from __future__ import annotations

import json
from pathlib import Path

import pytest

from vineclim.indices import ElevationCorrection, compute_indices
from vineclim.report import (
    ReportContext,
    build_document,
    build_report,
    detect_source_type,
    write_indices_csv,
    write_indices_json,
    write_report,
)

from .conftest import make_frame


@pytest.fixture
def built(tmp_path: Path):
    rows = [(f"2024-04-{day:02d}", 10.0, 20.0, 0.0) for day in range(1, 11)]
    for day in (2, 5, 9):
        rows[day - 1] = (f"2024-04-{day:02d}", None, None, 0.0)
    frame = make_frame(rows)
    correction = ElevationCorrection(
        station_elev_m=2200.0, grid_elev_m=3879.61, lapse_c_per_km=6.5
    )
    result = compute_indices(frame, 28.55, years=[2024], correction=correction)
    context = ReportContext(
        input_path=tmp_path / "power_deqin.csv",
        latitude=28.55,
        longitude=98.86,
        source_type="power-grid",
        source_note="unit test payload",
        coverage=("2024-04-01", "2024-04-10"),
        n_rows=10,
        hemisphere="north",
        huglin_k=1.0,
        site_name="测试点",
    )
    return result, context


def test_report_has_both_caveats(built):
    result, context = built
    text = build_report(result, context)
    assert "POWER 网格值不是园地实测" in text
    assert "海拔订正是示意" in text


def test_report_contains_uncorrected_and_corrected_columns(built):
    result, context = built
    text = build_report(result, context)
    assert "未订正" in text
    assert "订正（示意）" in text
    assert "+10.92 °C" in text
    assert "insufficient_data" in text


def test_report_names_site_and_source(built):
    result, context = built
    text = build_report(result, context)
    assert "测试点" in text
    assert "unit test payload" in text
    assert "NASA POWER" in text


def test_document_is_machine_readable(built):
    result, context = built
    document = build_document(result, context)
    assert document["data_source"]["power_is_not_measured"] is True
    assert document["elevation_correction"]["enabled"] is True
    assert document["elevation_correction"]["illustrative"] is True
    assert document["elevation_correction"]["offset_c"] == pytest.approx(10.918, abs=0.001)
    assert "POWER 网格值不是园地实测" in document["disclaimers"]
    assert document["years"][0]["indices"]["gdd10"]["value_corrected"] is not None


def test_json_and_csv_writers(built, tmp_path: Path):
    result, context = built
    json_path = write_indices_json(result, context, tmp_path / "indices.json")
    csv_path = write_indices_csv(result, tmp_path / "indices.csv")
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["version"] == "0.1.0"
    header, first = csv_path.read_text(encoding="utf-8").splitlines()[:2]
    assert "value_corrected" in header
    assert first.split(",")[3] != ""


def test_report_writer_creates_file(built, tmp_path: Path):
    result, context = built
    path = write_report(result, context, tmp_path / "report.md")
    assert path.is_file()
    assert path.stat().st_size > 1000


def test_no_correction_document_marks_disabled():
    frame = make_frame([("2024-01-01", 1.0, 2.0, 0.0)])
    result = compute_indices(frame, 28.55, years=[2024])
    context = ReportContext(
        input_path=Path("station.csv"),
        latitude=28.55,
        longitude=None,
        source_type="station",
        source_note="",
        coverage=("2024-01-01", "2024-01-01"),
        n_rows=1,
        hemisphere="north",
        huglin_k=1.0,
    )
    document = build_document(result, context)
    assert document["elevation_correction"] == {"enabled": False}
    assert document["data_source"]["power_is_not_measured"] is False


def test_detect_source_type():
    assert detect_source_type(Path("deqin_power.csv")) == "power-grid"
    assert detect_source_type(Path("synthetic_station.csv")) == "synthetic"
    assert detect_source_type(Path("my_station.csv")) == "station"
