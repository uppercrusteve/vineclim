"""NASA POWER daily-data download and conversion.

The network is only touched by :func:`fetch_power`; parsing is pure and can be
tested offline with a saved payload.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMETERS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR")
DEFAULT_FILL = -999.0


class FetchError(RuntimeError):
    """Raised when a POWER request or payload is unusable."""


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise FetchError("纬度必须在 -90 到 90 之间")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise FetchError("经度必须在 -180 到 180 之间")


def year_bounds(start_year: int, end_year: int) -> tuple[str, str]:
    """Convert inclusive years to POWER ``YYYYMMDD`` bounds."""
    if start_year > end_year:
        raise FetchError("起始年份不能晚于结束年份")
    if start_year < 1981 or end_year > 2030:
        raise FetchError("POWER 日值仅支持 1981–2030 年")
    return f"{start_year:04d}0101", f"{end_year:04d}1231"


def build_params(latitude: float, longitude: float, start: str, end: str) -> dict[str, str]:
    _validate_coordinates(latitude, longitude)
    return {
        "parameters": ",".join(POWER_PARAMETERS),
        "community": "AG",
        "longitude": f"{longitude:.4f}",
        "latitude": f"{latitude:.4f}",
        "start": start,
        "end": end,
        "format": "JSON",
        "time-standard": "LST",
    }


def parse_power_json(payload: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convert a POWER JSON payload into a validated daily frame plus metadata.

    POWER fill values become empty cells. The payload is untrusted input and is
    checked structurally before use.
    """
    if not isinstance(payload, dict):
        raise FetchError("POWER 响应不是 JSON 对象")
    properties = payload.get("properties")
    parameters = properties.get("parameter") if isinstance(properties, dict) else None
    if not isinstance(parameters, dict):
        raise FetchError("POWER 响应缺少 properties.parameter")
    missing = [name for name in POWER_PARAMETERS if name not in parameters]
    if missing:
        raise FetchError("POWER 响应缺少参数: " + ", ".join(missing))

    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    fill_value = float(header.get("fill_value", DEFAULT_FILL))
    dates = sorted(parameters[POWER_PARAMETERS[0]].keys())
    if not dates:
        raise FetchError("POWER 响应没有日期记录")
    for name in POWER_PARAMETERS[1:]:
        if sorted(parameters[name].keys()) != dates:
            raise FetchError("POWER 参数日期不一致")

    records: list[dict[str, Any]] = []
    for raw_date in dates:
        try:
            date = dt.datetime.strptime(raw_date, "%Y%m%d").date()
        except ValueError as exc:
            raise FetchError(f"POWER 日期格式异常: {raw_date}") from exc
        record: dict[str, Any] = {"date": date}
        for source, target in zip(POWER_PARAMETERS, ("tmax_c", "tmin_c", "precip_mm"), strict=True):
            value = parameters[source][raw_date]
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = float("nan")
            record[target] = float("nan") if numeric == fill_value else numeric
        records.append(record)

    frame = pd.DataFrame.from_records(records).sort_values("date").reset_index(drop=True)
    geometry = payload.get("geometry") if isinstance(payload.get("geometry"), dict) else {}
    coordinates = geometry.get("coordinates") or []
    elevation = None
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 3:
        try:
            elevation = float(coordinates[2])
        except (TypeError, ValueError):
            elevation = None
    metadata = {
        "api_version": (header.get("api") or {}).get("version"),
        "sources": header.get("sources", []),
        "fill_value": fill_value,
        "grid_elevation_m": elevation,
        "start": dates[0],
        "end": dates[-1],
        "n_days": len(dates),
    }
    return frame, metadata


def fetch_power(
    latitude: float,
    longitude: float,
    start_year: int,
    end_year: int,
    timeout: float = 90.0,
    attempts: int = 3,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Download daily POWER data, retrying transient failures."""
    start, end = year_bounds(start_year, end_year)
    params = build_params(latitude, longitude, start, end)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                POWER_URL,
                params=params,
                timeout=timeout,
                headers={"User-Agent": "vineclim/0.1.0 (+https://github.com/YilongXiao/vineclim)"},
            )
            response.raise_for_status()
            payload = response.json()
            frame, metadata = parse_power_json(payload)
            frame.attrs.update(metadata)
            return frame, metadata
        except (requests.RequestException, ValueError, FetchError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise FetchError(f"POWER 下载失败（{attempts} 次尝试）: {last_error}")


def _format_number(value: Any) -> str:
    return "" if value is None or pd.isna(value) else f"{float(value):.2f}"


def write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write the canonical CSV schema, using empty cells for missing values."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,tmin_c,tmax_c,precip_mm"]
    for row in frame.itertuples(index=False):
        lines.append(
            ",".join(
                (
                    row.date.isoformat(),
                    _format_number(row.tmin_c),
                    _format_number(row.tmax_c),
                    _format_number(row.precip_mm),
                )
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_metadata(metadata: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
