"""Bioclimatic index calculations.

All indices are computed from daily minimum/maximum temperature. The
implementations follow the definitions compiled in the project brief, with
explicit hemisphere handling and a missing-data threshold of 20 %.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .data import available_years

MISSING_THRESHOLD = 0.20

# Huglin latitude coefficient k (Huglin, 1978). Lower bound inclusive.
_HUGLIN_K_TABLE: tuple[tuple[float, float], ...] = (
    (40.0, 1.02),
    (42.0, 1.03),
    (44.0, 1.04),
    (46.0, 1.05),
    (48.0, 1.06),
)


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label_zh: str
    label_en: str
    unit: str
    description_zh: str
    required: tuple[str, ...]
    kind: str


METRICS: dict[str, MetricDefinition] = {
    "gdd10": MetricDefinition(
        key="gdd10",
        label_zh="生长度日 GDD10",
        label_en="Growing degree days (base 10 °C)",
        unit="°C·d",
        description_zh="年内 Σ max(0, Tmean − 10)，非生长季日贡献为 0，等价于生长季累计。",
        required=("tmin_c", "tmax_c"),
        kind="gdd",
    ),
    "huglin_hi": MetricDefinition(
        key="huglin_hi",
        label_zh="Huglin 热指数 HI",
        label_en="Huglin heliothermal index",
        unit="°C·d",
        description_zh="北半球 4–9 月、南半球 10–3 月，Σ max(0, ((Tmean−10)+(Tmax−10))/2) × k。",
        required=("tmin_c", "tmax_c"),
        kind="huglin",
    ),
    "cold_night_index": MetricDefinition(
        key="cold_night_index",
        label_zh="冷夜指数 CI",
        label_en="Cool night index",
        unit="°C",
        description_zh="北半球 9 月、南半球 3 月的平均 Tmin（成熟期夜温）。",
        required=("tmin_c",),
        kind="mean",
    ),
    "frost_days": MetricDefinition(
        key="frost_days",
        label_zh="全年霜冻日",
        label_en="Frost days",
        unit="d",
        description_zh="全年 Tmin < 0 °C 的天数。",
        required=("tmin_c",),
        kind="count",
    ),
    "spring_frost_days": MetricDefinition(
        key="spring_frost_days",
        label_zh="春霜日",
        label_en="Spring frost days",
        unit="d",
        description_zh="北半球 4–5 月、南半球 9–11 月 Tmin < 0 °C 的天数。",
        required=("tmin_c",),
        kind="count",
    ),
    "autumn_frost_days": MetricDefinition(
        key="autumn_frost_days",
        label_zh="秋霜日",
        label_en="Autumn frost days",
        unit="d",
        description_zh="北半球 10 月、南半球 4–5 月 Tmin < 0 °C 的天数。",
        required=("tmin_c",),
        kind="count",
    ),
    "hot_days_35c": MetricDefinition(
        key="hot_days_35c",
        label_zh="高温日",
        label_en="Hot days (Tmax > 35 °C)",
        unit="d",
        description_zh="全年 Tmax > 35 °C 的天数。",
        required=("tmax_c",),
        kind="count",
    ),
    "growing_season_length": MetricDefinition(
        key="growing_season_length",
        label_zh="生长季长度",
        label_en="Growing-season length",
        unit="d",
        description_zh="全年 Tmean ≥ 10 °C 的累计天数（非连续计数）。",
        required=("tmin_c", "tmax_c"),
        kind="gsl",
    ),
    "diurnal_range_gs": MetricDefinition(
        key="diurnal_range_gs",
        label_zh="生长季昼夜温差",
        label_en="Growing-season diurnal range",
        unit="°C",
        description_zh="Tmean ≥ 10 °C 的日内 Tmax − Tmin 的平均值。",
        required=("tmin_c", "tmax_c"),
        kind="mean",
    ),
}

METRIC_ORDER: tuple[str, ...] = tuple(METRICS)

# Reference classes. They come from temperate wine regions and are indicative
# only when applied to high-altitude sites.
HUGLIN_CLASSES: tuple[tuple[float, str], ...] = (
    (1200.0, "过冷（too cold）"),
    (1500.0, "很凉（very cool）"),
    (1800.0, "凉（cool）"),
    (2100.0, "温（temperate）"),
    (2400.0, "暖（warm）"),
    (3000.0, "很暖（very warm）"),
    (math.inf, "过热（too hot）"),
)

COOL_NIGHT_CLASSES: tuple[tuple[float, str], ...] = (
    (14.0, "夜很冷（very cool nights）"),
    (16.0, "夜冷（cool nights）"),
    (18.0, "夜温适中（temperate nights）"),
    (20.0, "夜暖（warm nights）"),
    (math.inf, "夜很暖（very warm nights）"),
)


@dataclass(frozen=True)
class ElevationCorrection:
    """Lapse-rate correction from grid elevation to station elevation."""

    station_elev_m: float
    grid_elev_m: float
    lapse_c_per_km: float = 6.5

    def __post_init__(self) -> None:
        for name, value in (
            ("station_elev_m", self.station_elev_m),
            ("grid_elev_m", self.grid_elev_m),
            ("lapse_c_per_km", self.lapse_c_per_km),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} 必须是有限数值")
        if self.lapse_c_per_km <= 0:
            raise ValueError("lapse 必须大于 0")

    @property
    def offset_c(self) -> float:
        """Temperature offset added to every grid temperature, in °C."""
        return self.lapse_c_per_km * (self.grid_elev_m - self.station_elev_m) / 1000.0


def huglin_k(latitude: float) -> float:
    """Return the Huglin latitude coefficient for a latitude in degrees.

    Below 40° the coefficient is 1.00 (documented simplification). The
    published table ends at 50°; higher latitudes also use 1.06.
    """
    if not math.isfinite(latitude) or abs(latitude) > 90:
        raise ValueError("纬度必须在 -90 到 90 之间")
    magnitude = abs(latitude)
    if magnitude < 40.0:
        return 1.00
    coefficient = 1.06
    for lower, value in _HUGLIN_K_TABLE:
        if lower <= magnitude < lower + 2.0:
            coefficient = value
            break
    return coefficient


def hemisphere(latitude: float) -> str:
    return "south" if latitude < 0 else "north"


def _month_window(year: int, months: set[int]) -> pd.Series:
    dates = pd.to_datetime(
        [f"{year:04d}-{month:02d}-01" for month in sorted(months)]
    )
    starts = dates
    # Build a boolean mask later from the frame; this helper returns the
    # calendar month/year pairs for the requested year.
    del starts
    return pd.Series(sorted(months))


def _window_mask(dates: pd.Series, year: int, metric: str, lat_hemisphere: str) -> pd.Series:
    """Boolean mask for the evaluation window of one metric/year."""
    years = dates.dt.year
    months = dates.dt.month
    south = lat_hemisphere == "south"
    if metric == "huglin_hi":
        if south:
            return ((years == year - 1) & (months >= 10)) | ((years == year) & (months <= 3))
        return (years == year) & months.between(4, 9)
    if metric == "cold_night_index":
        return (years == year) & (months == (3 if south else 9))
    if metric == "spring_frost_days":
        if south:
            return (years == year) & months.between(9, 11)
        return (years == year) & months.between(4, 5)
    if metric == "autumn_frost_days":
        if south:
            return (years == year) & months.between(4, 5)
        return (years == year) & (months == 10)
    return years == year


def _daily_series(metric: str, frame: pd.DataFrame, latitude: float) -> pd.Series:
    tmin = frame["tmin_c"]
    tmax = frame["tmax_c"]
    tmean = (tmin + tmax) / 2.0
    if metric == "gdd10":
        return (tmean - 10.0).clip(lower=0.0).fillna(0.0)
    if metric == "huglin_hi":
        contribution = ((tmean - 10.0) + (tmax - 10.0)) / 2.0
        return (contribution.clip(lower=0.0) * huglin_k(latitude)).fillna(0.0)
    if metric == "cold_night_index":
        return tmin
    if metric == "friost_days":  # pragma: no cover - alias guard
        return (tmin < 0.0).where(tmin.notna())
    if metric == "frost_days" or metric == "spring_frost_days" or metric == "autumn_frost_days":
        return (tmin < 0.0).where(tmin.notna()).astype(float)
    if metric == "hot_days_35c":
        return (tmax > 35.0).where(tmax.notna()).astype(float)
    if metric == "growing_season_length":
        return (tmean >= 10.0).where(tmean.notna()).astype(float)
    if metric == "diurnal_range_gs":
        return (tmax - tmin).where((tmean >= 10.0) & tmean.notna())
    raise KeyError(f"未知指标: {metric}")


def _evaluate(
    values: pd.Series,
    valid: pd.Series,
    used: pd.Series,
    n_window: int,
    kind: str,
) -> dict[str, Any]:
    """Summarise one metric series with quality flags.

    ``valid`` marks usable input days and drives the missing fraction;
    ``used`` marks days that contribute to the statistic.
    """
    n_valid = int(valid.sum())
    n_used = int(used.sum())
    n_missing = n_window - n_valid
    missing_fraction = (n_missing / n_window) if n_window else 1.0
    insufficient = n_window == 0 or missing_fraction > MISSING_THRESHOLD

    value: float | None
    if kind == "mean":
        value = float(values[used].mean()) if n_used else None
    elif kind == "count":
        value = float(values[used].sum()) if n_used else None
    else:
        value = float(np.nansum(values[used].to_numpy(dtype=float))) if n_used else None

    return {
        "value": value,
        "n_days": n_used,
        "n_missing": n_missing,
        "missing_fraction": round(missing_fraction, 4),
        "status": "insufficient_data" if insufficient else "ok",
    }


def _compute_for_frame(
    frame: pd.DataFrame,
    latitude: float,
    years: list[int],
    suffix: str,
) -> dict[int, dict[str, dict[str, Any]]]:
    results: dict[int, dict[str, dict[str, Any]]] = {}
    lat_hemisphere = hemisphere(latitude)
    dates = frame["date"]
    for year in years:
        yearly: dict[str, dict[str, Any]] = {}
        for key in METRIC_ORDER:
            definition = METRICS[key]
            window = _window_mask(dates, year, key, lat_hemisphere)
            sub = frame.loc[window]
            values = _daily_series(key, sub, latitude)
            if key in ("hot_days_35c",):
                valid = sub["tmax_c"].notna()
            elif key in ("cold_night_index", "frost_days", "spring_frost_days", "autumn_frost_days"):
                valid = sub["tmin_c"].notna()
            else:
                valid = sub["tmin_c"].notna() & sub["tmax_c"].notna()
            if key in ("diurnal_range_gs", "growing_season_length"):
                used = valid & ((sub["tmin_c"] + sub["tmax_c"]) / 2.0 >= 10.0)
            else:
                used = valid

            entry = _evaluate(values, valid, used, int(window.sum()), definition.kind)
            if suffix:
                entry = {f"{name}{suffix}": item for name, item in entry.items()}
            yearly[key] = entry
        results[year] = yearly
    return results


def _merge_corrected(
    raw: dict[str, Any], corrected: dict[str, Any] | None
) -> dict[str, Any]:
    merged = dict(raw)
    if corrected is not None:
        merged["value_corrected"] = corrected["value"]
        merged["n_days_corrected"] = corrected["n_days"]
        merged["n_missing_corrected"] = corrected["n_missing"]
        merged["missing_fraction_corrected"] = corrected["missing_fraction"]
        merged["status_corrected"] = corrected["status"]
    return merged


def correction_frame(frame: pd.DataFrame, correction: ElevationCorrection) -> pd.DataFrame:
    """Return a copy with the lapse-rate offset applied to both temperatures."""
    adjusted = frame.copy()
    adjusted["tmin_c"] = adjusted["tmin_c"] + correction.offset_c
    adjusted["tmax_c"] = adjusted["tmax_c"] + correction.offset_c
    return adjusted


def compute_indices(
    frame: pd.DataFrame,
    latitude: float,
    years: list[int] | None = None,
    correction: ElevationCorrection | None = None,
) -> dict[str, Any]:
    """Compute annual indices, optionally with a paired elevation correction.

    The uncorrected values are always retained. When a correction is given,
    corrected values are stored next to them.
    """
    if not math.isfinite(latitude) or abs(latitude) > 90:
        raise ValueError("纬度必须在 -90 到 90 之间")
    if years is None:
        years = available_years(frame)
    years = sorted(dict.fromkeys(int(year) for year in years))
    if not years:
        raise ValueError("没有可计算的年份")

    raw = _compute_for_frame(frame, latitude, years, suffix="")
    corrected: dict[int, dict[str, dict[str, Any]]] | None = None
    if correction is not None:
        corrected = _compute_for_frame(
            correction_frame(frame, correction), latitude, years, suffix=""
        )

    rows: list[dict[str, Any]] = []
    per_year: list[dict[str, Any]] = []
    for year in years:
        merged_metrics: dict[str, Any] = {}
        for key in METRIC_ORDER:
            merged = _merge_corrected(raw[year][key], corrected[year][key] if corrected else None)
            merged_metrics[key] = merged
            rows.append({"year": year, "metric": key, **merged})
        per_year.append({"year": year, "indices": merged_metrics})

    climatology: dict[str, Any] = {}
    for key in METRIC_ORDER:
        usable = [
            raw[year][key]["value"]
            for year in years
            if raw[year][key]["status"] == "ok" and raw[year][key]["value"] is not None
        ]
        usable_corrected = (
            [
                corrected[year][key]["value"]
                for year in years
                if corrected[year][key]["status"] == "ok"
                and corrected[year][key]["value"] is not None
            ]
            if corrected
            else []
        )
        climatology[key] = {
            "mean": round(float(np.mean(usable)), 2) if usable else None,
            "mean_corrected": (
                round(float(np.mean(usable_corrected)), 2) if usable_corrected else None
            ),
            "n_years_used": len(usable),
            "n_years_insufficient": sum(
                1 for year in years if raw[year][key]["status"] == "insufficient_data"
            ),
            "classification": classify(key, climatology_value(usable)) if usable else None,
        }

    return {
        "years": per_year,
        "rows": rows,
        "climatology": climatology,
        "correction": correction,
        "hemisphere": hemisphere(latitude),
        "huglin_k": huglin_k(latitude),
    }


def climatology_value(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def classify(metric: str, value: float | None) -> str | None:
    """Give an indicative class label; temperate-zone references only."""
    if value is None or not math.isfinite(value):
        return None
    if metric == "huglin_hi":
        for upper, label in HUGLIN_CLASSES:
            if value < upper:
                return label
    if metric == "cold_night_index":
        for upper, label in COOL_NIGHT_CLASSES:
            if value < upper:
                return label
    if metric == "gdd10":
        if value < 850:
            return "冷凉（很短的成熟窗口）"
        if value < 1111:
            return "冷凉"
        if value < 1389:
            return "中等偏凉"
        if value < 1667:
            return "中等"
        if value < 1944:
            return "温暖"
        return "很暖"
    if metric == "frost_days":
        if value < 20:
            return "霜冻风险较低"
        if value < 60:
            return "霜冻风险中等"
        return "霜冻风险较高"
    if metric == "hot_days_35c":
        if value < 1:
            return "几乎无高温胁迫"
        if value < 10:
            return "偶有高温"
        return "高温频繁"
    if metric == "growing_season_length":
        if value < 150:
            return "生长季短"
        if value < 210:
            return "生长季中等"
        return "生长季长"
    if metric == "diurnal_range_gs":
        if value < 10:
            return "昼夜温差小"
        if value < 14:
            return "昼夜温差中等"
        return "昼夜温差大"
    return None
