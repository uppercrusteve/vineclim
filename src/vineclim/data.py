"""Input loading and validation.

Only the documented CSV schema is accepted. Rows are sorted by date, duplicate
dates are rejected, and non-numeric temperatures are treated as missing.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ("date", "tmin_c", "tmax_c", "precip_mm")
VALUE_COLUMNS = ("tmin_c", "tmax_c", "precip_mm")
MISSING_SENTINELS = (-999.0, -9999.0)


class DataError(ValueError):
    """Raised for malformed input data."""


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load and validate a daily climate CSV.

    Expected columns: ``date,tmin_c,tmax_c,precip_mm``. Missing values are
    allowed as empty cells or POWER fill values (-999).
    """
    path = Path(path)
    if not path.is_file():
        raise DataError(f"输入文件不存在: {path}")

    try:
        frame = pd.read_csv(path, dtype={"date": "string"})
    except pd.errors.EmptyDataError as exc:
        raise DataError(f"输入文件为空: {path}") from exc
    except (OSError, pd.errors.ParserError) as exc:
        raise DataError(f"无法读取 CSV: {exc}") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise DataError(
            "缺少必需列: " + ", ".join(missing_columns) + "。CSV 列必须为 date,tmin_c,tmax_c,precip_mm"
        )

    if frame.empty:
        raise DataError("输入文件没有数据行")

    frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    parsed_dates: list[dt.date] = []
    invalid_rows: list[str] = []
    for position, raw in enumerate(frame["date"].tolist()):
        try:
            parsed_dates.append(dt.datetime.strptime(str(raw).strip(), "%Y-%m-%d").date())
        except (TypeError, ValueError):
            parsed_dates.append(dt.date.min)
            invalid_rows.append(str(position + 2))
    if invalid_rows:
        raise DataError(
            f"无法解析日期（应为 YYYY-MM-DD；行号从表头后计）: {', '.join(invalid_rows[:5])}"
        )
    frame["date"] = pd.to_datetime(pd.Series(parsed_dates, index=frame.index))

    for column in VALUE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame[column] = frame[column].replace(list(MISSING_SENTINELS), float("nan"))

    duplicates = frame["date"].duplicated(keep=False)
    if duplicates.any():
        dates = ", ".join(sorted({value.strftime("%Y-%m-%d") for value in frame.loc[duplicates, "date"]})[:5])
        raise DataError(f"存在重复日期: {dates}")

    both = frame["tmin_c"].notna() & frame["tmax_c"].notna()
    inverted = both & (frame["tmin_c"] > frame["tmax_c"])
    if inverted.any():
        dates = ", ".join(frame.loc[inverted, "date"].dt.strftime("%Y-%m-%d").head(5))
        raise DataError(f"tmin_c 高于 tmax_c: {dates}")

    frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    return frame


def available_years(frame: pd.DataFrame) -> list[int]:
    """Return sorted years present in the data."""
    return sorted(frame["date"].dt.year.unique().tolist())


def coverage(frame: pd.DataFrame) -> tuple[str, str]:
    """Return ISO start and end dates of the input."""
    return frame["date"].min().date().isoformat(), frame["date"].max().date().isoformat()
