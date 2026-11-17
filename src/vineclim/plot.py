"""Figure generation (Agg backend, Chinese labels).

All figures are drawn from the same computed result that feeds the JSON/CSV
files, so the screenshots cannot drift from the numbers.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from .indices import ElevationCorrection  # noqa: E402

_CJK_CANDIDATES = (
    "Microsoft YaHei",
    "Noto Sans SC",
    "SimHei",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "Arial Unicode MS",
)
_FALLBACK_FILES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)
MONTHS = tuple(f"{month}月" for month in range(1, 13))


def setup_chinese_font() -> str:
    """Select an available CJK font and configure matplotlib."""
    available = {entry.name for entry in font_manager.fontManager.ttflist}
    chosen = next((name for name in _CJK_CANDIDATES if name in available), None)
    if chosen is None:
        for path in _FALLBACK_FILES:
            if Path(path).is_file():
                font_manager.fontManager.addfont(path)
                chosen = font_manager.FontProperties(fname=path).get_name()
                break
    if chosen is None:
        chosen = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 110
    return chosen


def _finish(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _style(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="y", color="#dddddd", linewidth=0.6)
    axis.set_axisbelow(True)


def plot_annual_gdd(
    result: dict,
    correction: ElevationCorrection | None,
    path: Path,
    data_note: str = "NASA POWER 网格值，非园地实测",
) -> Path:
    years = [entry["year"] for entry in result["years"]]
    raw = [entry["indices"]["gdd10"].get("value") for entry in result["years"]]
    corrected = (
        [entry["indices"]["gdd10"].get("value_corrected") for entry in result["years"]]
        if correction
        else None
    )
    positions = np.arange(len(years))
    width = 0.38 if correction else 0.62

    fig, axis = plt.subplots(figsize=(max(7.0, len(years) * 0.62), 4.4))
    raw_values = [value if value is not None else 0.0 for value in raw]
    axis.bar(
        positions - (width / 2 if correction else 0),
        raw_values,
        width=width,
        color="#b2182b",
        label="未订正（网格值）",
    )
    if corrected is not None:
        corrected_values = [value if value is not None else 0.0 for value in corrected]
        axis.bar(
            positions + width / 2,
            corrected_values,
            width=width,
            color="#ef8a62",
            hatch="//",
            edgecolor="white",
            label="海拔订正（示意）",
        )
    for index, (raw_value, entry) in enumerate(zip(raw, result["years"], strict=True)):
        gdd = entry["indices"]["gdd10"]
        if gdd.get("status") == "insufficient_data" or raw_value is None:
            top = max(raw_value or 0.0, (corrected[index] if corrected else 0.0) or 0.0)
            axis.text(index, top + 8, "*", ha="center", va="bottom", color="#333333")
        elif raw_value is not None:
            axis.text(index, raw_value + 8, f"{raw_value:.0f}", ha="center", va="bottom", fontsize=7)

    axis.set_xticks(positions, [str(year) for year in years], rotation=45, ha="right")
    axis.set_ylabel("GDD10（°C·d）")
    axis.set_title("逐年生长度日 GDD10（Tmean 基准 10 °C）", loc="left", fontsize=12, pad=24)
    axis.text(
        0.0,
        1.012,
        f"{data_note}；* 表示缺测 >20%",
        transform=axis.transAxes,
        fontsize=8,
        color="#555555",
    )
    axis.legend(frameon=False, loc="upper left")
    _style(axis)
    fig.tight_layout()
    return _finish(fig, path)


def plot_frost_calendar(
    frame: pd.DataFrame, path: Path, data_note: str = "POWER 网格值，非园地实测"
) -> Path:
    data = frame.copy()
    data["year"] = data["date"].dt.year
    data["month"] = data["date"].dt.month
    frost = data.assign(frost=(data["tmin_c"] < 0).astype(float)).dropna(subset=["tmin_c"])
    counts = frost.pivot_table(
        index="year", columns="month", values="frost", aggfunc="sum", fill_value=np.nan
    )
    years = sorted(counts.index.tolist())
    matrix = counts.reindex(index=years, columns=range(1, 13)).to_numpy(dtype=float)
    known = counts.reindex(index=years, columns=range(1, 13)).notna().to_numpy()

    fig, axis = plt.subplots(figsize=(10.5, max(4.0, len(years) * 0.42)))
    masked = np.ma.masked_where(~known, matrix)
    image = axis.imshow(masked, aspect="auto", cmap="YlGnBu", interpolation="nearest")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            if known[row, column] and matrix[row, column] > 0:
                value = matrix[row, column]
                axis.text(
                    column,
                    row,
                    f"{value:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if value > matrix[known].max() * 0.55 else "#08306b",
                )
    axis.set_xticks(range(12), MONTHS, rotation=0)
    axis.set_yticks(range(len(years)), [str(year) for year in years])
    axis.set_title("逐月霜冻日日历（Tmin < 0 °C）", loc="left", fontsize=12, pad=24)
    axis.text(
        0.0,
        1.012,
        f"数字为该月霜冻日数；空格为缺测或未覆盖。{data_note}。",
        transform=axis.transAxes,
        fontsize=8,
        color="#555555",
    )
    colorbar = fig.colorbar(image, ax=axis, pad=0.015)
    colorbar.set_label("霜冻日数（d）")
    fig.tight_layout()
    return _finish(fig, path)


def _monthly_mean(frame: pd.DataFrame, column: str) -> pd.Series:
    data = frame.dropna(subset=[column]).copy()
    data["month"] = data["date"].dt.month
    return data.groupby("month")[column].mean().reindex(range(1, 13))


def plot_climatology(
    frame: pd.DataFrame,
    corrected_frame: pd.DataFrame | None,
    latitude: float,
    path: Path,
    site_name: str = "研究站点",
    correction: ElevationCorrection | None = None,
    data_note: str = "NASA POWER 网格值不是园地实测",
) -> Path:
    """Three-panel monthly climatology with raw and corrected temperature."""
    n_years = max(frame["date"].dt.year.nunique(), 1)
    raw_tmin = _monthly_mean(frame, "tmin_c")
    raw_tmax = _monthly_mean(frame, "tmax_c")
    precip = _monthly_mean(frame, "precip_mm")

    fig, axes = plt.subplots(3, 1, figsize=(9.2, 9.0), sharex=True)
    ax_temp, ax_rain, ax_events = axes
    x = np.arange(1, 13)

    ax_temp.fill_between(x, raw_tmin, raw_tmax, color="#f4a582", alpha=0.28, label="未订正日较差带")
    ax_temp.plot(x, raw_tmax, color="#b2182b", marker="o", markersize=3, label="未订正 Tmax")
    ax_temp.plot(x, raw_tmin, color="#2166ac", marker="o", markersize=3, label="未订正 Tmin")
    if corrected_frame is not None:
        corrected_tmin = _monthly_mean(corrected_frame, "tmin_c")
        corrected_tmax = _monthly_mean(corrected_frame, "tmax_c")
        ax_temp.plot(
            x, corrected_tmax, color="#b2182b", linestyle="--", linewidth=1.2, label="订正 Tmax（示意）"
        )
        ax_temp.plot(
            x, corrected_tmin, color="#2166ac", linestyle="--", linewidth=1.2, label="订正 Tmin（示意）"
        )
    ax_temp.axhline(0, color="#777777", linewidth=0.7)
    ax_temp.set_ylabel("月平均气温（°C）")
    ax_temp.set_title(
        f"月气候概况 · 纬度 {latitude:.2f}° · {n_years} 年", loc="left", fontsize=12
    )
    ax_temp.legend(frameon=False, ncol=2, fontsize=7, loc="upper left")
    _style(ax_temp)

    ax_rain.bar(x, precip, color="#4d9221", width=0.7)
    ax_rain.set_ylabel("平均降水量（mm/d）")
    ax_rain.text(0.0, 1.01, "月中平均日降水（POWER 校正降水）", transform=ax_rain.transAxes,
                 fontsize=8, color="#555555")
    _style(ax_rain)

    frost = frame.assign(f=(frame["tmin_c"] < 0).astype(float)).dropna(subset=["tmin_c"])
    frost["month"] = frost["date"].dt.month
    frost_month = frost.groupby("month")["f"].sum().reindex(range(1, 13), fill_value=0) / n_years
    hot = frame.assign(h=(frame["tmax_c"] > 35).astype(float)).dropna(subset=["tmax_c"])
    hot["month"] = hot["date"].dt.month
    hot_month = hot.groupby("month")["h"].sum().reindex(range(1, 13), fill_value=0) / n_years
    ax_events.bar(x - 0.19, frost_month, width=0.36, color="#4575b4", label="霜冻日（Tmin < 0 °C）")
    ax_events.bar(x + 0.19, hot_month, width=0.36, color="#d73027", label="高温日（Tmax > 35 °C）")
    ax_events.set_ylabel("年平均日数（d）")
    ax_events.set_xlabel("月份")
    ax_events.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax_events)

    ax_events.set_xticks(x, MONTHS)
    first_year = int(frame["date"].dt.year.min())
    last_year = int(frame["date"].dt.year.max())
    fig.suptitle(
        f"高海拔葡萄园气候指标 · {site_name}（{first_year}–{last_year}）",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    if correction is not None:
        note = (
            f"{data_note}；虚线为示意性海拔订正"
            f"（lapse {correction.lapse_c_per_km:g} °C/km，偏移 {correction.offset_c:+.1f} °C），仅作比较。"
        )
    else:
        note = f"{data_note}；未启用海拔订正。"
    fig.text(0.01, 0.945, note, fontsize=8.5, color="#b2182b")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _finish(fig, path)


def make_all_plots(
    result: dict,
    frame: pd.DataFrame,
    corrected_frame: pd.DataFrame | None,
    latitude: float,
    correction: ElevationCorrection | None,
    outdir: Path,
    site_name: str = "研究站点",
    data_note: str = "NASA POWER 网格值不是园地实测",
) -> list[Path]:
    setup_chinese_font()
    outdir.mkdir(parents=True, exist_ok=True)
    return [
        plot_annual_gdd(result, correction, outdir / "annual-gdd.png", data_note),
        plot_frost_calendar(frame, outdir / "frost-calendar.png", data_note),
        plot_climatology(
            frame,
            corrected_frame,
            latitude,
            outdir / "climatology.png",
            site_name=site_name,
            correction=correction,
            data_note=data_note,
        ),
    ]
