from __future__ import annotations

import math

import pandas as pd
import pytest

from vineclim.indices import (
    ElevationCorrection,
    classify,
    compute_indices,
    correction_frame,
    hemisphere,
    huglin_k,
)

from .conftest import compute, entry, make_frame


def test_gdd_hand_computed(three_day_rows):
    result = compute(three_day_rows, latitude=45.0)
    gdd = entry(result, 2024, "gdd10")
    assert gdd["value"] == pytest.approx(9.0)
    assert gdd["n_days"] == 3
    # Only three days are present, so the rest of the calendar year counts as missing.
    assert gdd["n_missing"] == 363
    assert gdd["status"] == "insufficient_data"


def test_huglin_hand_computed_with_k(three_day_rows):
    result = compute(three_day_rows, latitude=45.0)
    huglin = entry(result, 2024, "huglin_hi")
    assert huglin["value"] == pytest.approx(14.04)
    assert huglin["n_days"] == 3


def test_cold_night_index_is_september_mean():
    rows = [
        ("2024-09-01", 5.0, 20.0, 0.0),
        ("2024-09-02", 7.0, 21.0, 0.0),
        ("2024-09-03", 9.0, 22.0, 0.0),
        ("2024-08-31", -4.0, 18.0, 0.0),
        ("2024-10-01", 99.0, 100.0, 0.0),
    ]
    result = compute(rows, latitude=45.0)
    ci = entry(result, 2024, "cold_night_index")
    assert ci["value"] == pytest.approx(7.0)
    assert ci["n_days"] == 3


def test_leap_day_is_included():
    rows = [
        ("2024-02-28", 10.0, 20.0, 0.0),
        ("2024-02-29", 12.0, 18.0, 0.0),
        ("2024-03-01", 5.0, 9.0, 0.0),
    ]
    result = compute(rows, latitude=45.0, years=[2024])
    gdd = entry(result, 2024, "gdd10")
    assert gdd["n_days"] == 3
    assert gdd["value"] == pytest.approx(10.0)


def _full_year(year: int, skip_days: int = 0):
    dates = list(pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D"))
    rows = [(d.strftime("%Y-%m-%d"), 10.0, 20.0, 0.0) for d in dates]
    for index in range(skip_days):
        day = rows[index][0]
        rows[index] = (day, None, None, 0.0)
    return rows


def test_missing_values_are_skipped_and_counted():
    rows = _full_year(2023, skip_days=3)
    result = compute(rows, latitude=45.0)
    gdd = entry(result, 2023, "gdd10")
    assert gdd["n_days"] == 362
    assert gdd["n_missing"] == 3
    assert gdd["missing_fraction"] == pytest.approx(3 / 365, abs=1e-4)
    assert gdd["status"] == "ok"
    assert gdd["value"] == pytest.approx(1810.0)


def test_missing_month_still_counts_against_the_calendar_window():
    dates = [d for d in pd.date_range("2024-01-01", "2024-12-31", freq="D") if d.month != 4]
    rows = [(d.strftime("%Y-%m-%d"), 10.0, 20.0, 0.0) for d in dates]
    result = compute(rows, latitude=45.0)
    gdd = entry(result, 2024, "gdd10")
    assert gdd["n_missing"] == 30
    assert gdd["missing_fraction"] == pytest.approx(30 / 366, abs=1e-4)
    # April alone is 8 % of the year, below the 20 % threshold.
    assert gdd["status"] == "ok"


def test_absent_months_mark_the_year_insufficient():
    dates = [d for d in pd.date_range("2024-01-01", "2024-12-31", freq="D") if d.month not in (4, 5, 6)]
    rows = [(d.strftime("%Y-%m-%d"), 10.0, 20.0, 0.0) for d in dates]
    result = compute(rows, latitude=45.0)
    gdd = entry(result, 2024, "gdd10")
    assert gdd["n_missing"] == 91
    assert gdd["status"] == "insufficient_data"


def test_exactly_twenty_percent_is_not_insufficient():
    rows = _full_year(2023, skip_days=73)
    result = compute(rows, latitude=45.0)
    gdd = entry(result, 2023, "gdd10")
    assert gdd["missing_fraction"] == pytest.approx(0.2)
    assert gdd["status"] == "ok"
    assert gdd["value"] == pytest.approx(1460.0)


def test_southern_hemisphere_huglin_uses_october_to_march():
    rows = [
        ("2023-04-15", 10.0, 20.0, 0.0),
        ("2023-05-15", 10.0, 20.0, 0.0),
        ("2023-06-15", 10.0, 20.0, 0.0),
        ("2023-07-15", 10.0, 20.0, 0.0),
        ("2023-08-15", 10.0, 20.0, 0.0),
        ("2023-09-15", 10.0, 20.0, 0.0),
        ("2023-10-15", 10.0, 20.0, 0.0),
        ("2023-11-15", 10.0, 20.0, 0.0),
        ("2023-12-15", 10.0, 20.0, 0.0),
        ("2024-01-15", 10.0, 20.0, 0.0),
        ("2024-02-15", 10.0, 20.0, 0.0),
        ("2024-03-15", 10.0, 20.0, 0.0),
        ("2024-04-15", 10.0, 20.0, 0.0),
        ("2024-05-15", 10.0, 20.0, 0.0),
        ("2024-06-15", 10.0, 20.0, 0.0),
        ("2024-07-15", 10.0, 20.0, 0.0),
        ("2024-08-15", 10.0, 20.0, 0.0),
        ("2024-09-15", 10.0, 20.0, 0.0),
    ]
    result = compute(rows, latitude=-33.0, years=[2024])
    huglin = entry(result, 2024, "huglin_hi")
    assert huglin["n_days"] == 6
    assert huglin["value"] == pytest.approx(45.0)


def test_southern_cold_night_index_uses_march():
    rows = [
        ("2024-03-10", 3.0, 18.0, 0.0),
        ("2024-03-11", 5.0, 19.0, 0.0),
        ("2024-09-10", -8.0, 12.0, 0.0),
    ]
    result = compute(rows, latitude=-33.0)
    ci = entry(result, 2024, "cold_night_index")
    assert ci["value"] == pytest.approx(4.0)
    assert ci["n_days"] == 2


def test_correction_applies_in_expected_direction_and_reports_both(correction):
    rows = [("2024-01-01", 0.0, 20.0, 0.0)]
    result = compute(rows, latitude=45.0, correction=correction)
    gdd = entry(result, 2024, "gdd10")
    assert correction.offset_c == pytest.approx(6.5)
    assert gdd["value"] == pytest.approx(0.0)
    assert gdd["value_corrected"] == pytest.approx(6.5)
    assert gdd["value"] != gdd["value_corrected"]
    diurnal = entry(result, 2024, "diurnal_range_gs")
    assert diurnal["value"] == pytest.approx(20.0)
    assert diurnal["value_corrected"] == pytest.approx(20.0)


def test_correction_frame_shifts_both_temperatures(correction):
    frame = make_frame([("2024-01-01", 0.0, 10.0, 0.0)])
    adjusted = correction_frame(frame, correction)
    assert adjusted.loc[0, "tmin_c"] == pytest.approx(6.5)
    assert adjusted.loc[0, "tmax_c"] == pytest.approx(16.5)
    assert frame.loc[0, "tmin_c"] == pytest.approx(0.0)


def test_correction_validation():
    with pytest.raises(ValueError):
        ElevationCorrection(station_elev_m=2000.0, grid_elev_m=3000.0, lapse_c_per_km=0)
    with pytest.raises(ValueError):
        ElevationCorrection(station_elev_m=math.nan, grid_elev_m=3000.0)


def test_huglin_k_boundaries():
    assert huglin_k(39.99) == pytest.approx(1.00)
    assert huglin_k(28.55) == pytest.approx(1.00)
    assert huglin_k(40.0) == pytest.approx(1.02)
    assert huglin_k(41.999) == pytest.approx(1.02)
    assert huglin_k(42.0) == pytest.approx(1.03)
    assert huglin_k(44.0) == pytest.approx(1.04)
    assert huglin_k(46.0) == pytest.approx(1.05)
    assert huglin_k(48.0) == pytest.approx(1.06)
    assert huglin_k(50.0) == pytest.approx(1.06)
    assert huglin_k(55.0) == pytest.approx(1.06)


def test_huglin_k_rejects_invalid_latitude():
    with pytest.raises(ValueError):
        huglin_k(91)
    with pytest.raises(ValueError):
        huglin_k(math.nan)


def test_growing_season_and_diurnal_range():
    rows = [
        ("2024-05-01", 10.0, 20.0, 0.0),
        ("2024-05-02", 5.0, 9.0, 0.0),
        ("2024-05-03", 12.0, 22.0, 0.0),
    ]
    result = compute(rows, latitude=45.0)
    gsl = entry(result, 2024, "growing_season_length")
    diurnal = entry(result, 2024, "diurnal_range_gs")
    assert gsl["value"] == pytest.approx(2.0)
    assert gsl["n_days"] == 2
    assert diurnal["value"] == pytest.approx(10.0)
    assert diurnal["n_days"] == 2


def test_temperature_only_metrics_accept_missing_tmax():
    rows = [
        ("2024-04-01", -3.0, None, 0.0),
        ("2024-04-02", 2.0, None, 0.0),
    ]
    result = compute(rows, latitude=45.0)
    frost = entry(result, 2024, "spring_frost_days")
    assert frost["value"] == pytest.approx(1.0)
    assert frost["n_days"] == 2


def test_all_missing_window_marks_insufficient():
    rows = [("2024-01-01", None, None, 0.0), ("2024-01-02", None, None, 0.0)]
    result = compute(rows, latitude=45.0)
    gdd = entry(result, 2024, "gdd10")
    assert gdd["value"] is None
    assert gdd["missing_fraction"] == pytest.approx(1.0)
    assert gdd["status"] == "insufficient_data"


def test_climatology_ignores_insufficient_years():
    rows = _full_year(2023)
    rows += [(f"2024-01-{day:02d}", None, None, 0.0) for day in range(1, 11)]
    result = compute(rows, latitude=45.0, years=[2023, 2024])
    summary = result["climatology"]["gdd10"]
    assert summary["mean"] == pytest.approx(1825.0)
    assert summary["n_years_used"] == 1
    assert summary["n_years_insufficient"] == 1


def test_repeated_year_is_deduplicated():
    rows = [("2024-01-01", 10.0, 20.0, 0.0)]
    result = compute(rows, latitude=45.0, years=[2024, 2024])
    assert len(result["years"]) == 1


def test_hemisphere_and_classification():
    assert hemisphere(-33) == "south"
    assert hemisphere(0) == "north"
    assert "too hot" in classify("huglin_hi", 3200)
    assert classify("huglin_hi", None) is None


def test_compute_rejects_bad_latitude():
    frame: pd.DataFrame = make_frame([("2024-01-01", 1.0, 2.0, 0.0)])
    with pytest.raises(ValueError):
        compute_indices(frame, 120)
