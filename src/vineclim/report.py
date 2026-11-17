"""Report, JSON and CSV writers.

The report always separates uncorrected and corrected values and carries the
two project-wide caveats: gridded POWER values are not vineyard measurements,
and lapse-rate correction is illustrative.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .indices import METRIC_ORDER, METRICS, ElevationCorrection

POWER_CAVEAT = "POWER 网格值不是园地实测"
CORRECTION_CAVEAT = "海拔订正是示意"

SOURCE_LABELS = {
    "power-grid": "NASA POWER 网格日值（网格产品，非园地实测）",
    "station": "台站 CSV（需自行确认观测质量）",
    "synthetic": "合成演示数据（非观测）",
}


@dataclass(frozen=True)
class ReportContext:
    input_path: Path
    latitude: float
    longitude: float | None
    source_type: str
    source_note: str
    coverage: tuple[str, str]
    n_rows: int
    hemisphere: str
    huglin_k: float
    site_name: str = "研究站点"

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source_type, self.source_type)


def detect_source_type(path: Path) -> str:
    name = path.name.lower()
    if "power" in name:
        return "power-grid"
    if "synthetic" in name or "synth" in name:
        return "synthetic"
    return "station"


def _value(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _status(value: str) -> str:
    return "`insufficient_data`" if value == "insufficient_data" else "ok"


def _metric_table(result: dict[str, Any], key: str, corrected: bool) -> list[str]:
    header = "| 年 | 未订正 | 有效天 n | 缺测 | 缺测比例 | 状态 |"
    separator = "|---:|---:|---:|---:|---:|---|"
    if corrected:
        header = "| 年 | 未订正 | 订正（示意） | 有效天 n | 缺测 | 缺测比例 | 未订正状态 | 订正状态 |"
        separator = "|---:|---:|---:|---:|---:|---:|---|---|"
    lines = [header, separator]
    for year_entry in result["years"]:
        entry = year_entry["indices"][key]
        cells = [_value(entry.get("value")), _value(entry.get("n_days"), 0), _value(entry.get("n_missing"), 0),
                 _value(entry.get("missing_fraction"), 2), _status(entry.get("status", "ok"))]
        if corrected:
            cells.insert(1, _value(entry.get("value_corrected")))
            cells.append(_status(entry.get("status_corrected", "ok")))
        lines.append("| " + " | ".join((str(year_entry["year"]), *cells)) + " |")
    return lines


def _climatology_table(result: dict[str, Any], corrected: bool) -> list[str]:
    header = "| 指标 | 单位 | 多年均值（未订正） | 多年均值（订正） | 可用年数 | 缺测年数 | 指示性分级 |"
    separator = "|---|---:|---:|---:|---:|---:|---|"
    if not corrected:
        header = "| 指标 | 单位 | 多年均值（未订正） | 可用年数 | 缺测年数 | 指示性分级 |"
        separator = "|---|---:|---:|---:|---:|---|"
    lines = [header, separator]
    for key in METRIC_ORDER:
        definition = METRICS[key]
        summary = result["climatology"][key]
        cells = [
            f"{definition.label_zh} ({definition.label_en})",
            definition.unit,
            _value(summary["mean"]),
            _value(summary["n_years_used"], 0),
            _value(summary["n_years_insufficient"], 0),
            summary["classification"] or "—",
        ]
        if corrected:
            cells.insert(3, _value(summary["mean_corrected"]))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _interpretation(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    notes = {
        "gdd10": "GDD 仅表示热量累积，未考虑品种需求、霜冻发生时间与水分。",
        "huglin_hi": "Huglin 分级来自温带产区，用于高海拔产区只作横向比较。",
        "cold_night_index": "冷夜指数反映成熟期夜间降温，过高会削弱花色苷积累。",
        "frost_days": "霜冻日按 Tmin < 0 °C 计数，未区分辐射霜与平流霜，也未考虑芽期。",
        "hot_days_35c": "35 °C 为通用阈值，不同品种的耐受上限不同。",
        "growing_season_length": "生长季长度为累计天数（非最长连续段），可被孤立的暖日拉长。",
        "diurnal_range_gs": "昼夜温差大通常有利香气，但极端日较差也意味着夜间低温风险。",
    }
    for key in METRIC_ORDER:
        definition = METRICS[key]
        summary = result["climatology"][key]
        value = summary["mean"]
        text = _value(value) + " " + definition.unit if value is not None else "无足够数据"
        classification = summary["classification"]
        line = f"- **{definition.label_zh}**：多年均值（未订正）{text}"
        corrected_mean = summary.get("mean_corrected")
        if corrected_mean is not None:
            line += f"，订正（示意）后 {_value(corrected_mean)} {definition.unit}"
        if classification:
            line += f"，指示性分级为“{classification}”"
        line += "。" + notes.get(key, "")
        if summary["n_years_insufficient"]:
            line += f" 有 {summary['n_years_insufficient']} 年因缺测 >20% 被标记。"
        lines.append(line)
    return lines


def build_report(result: dict[str, Any], context: ReportContext) -> str:
    correction: ElevationCorrection | None = result["correction"]
    corrected = correction is not None
    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    site_lon = f"{context.longitude:.3f}°" if context.longitude is not None else "未提供"

    lines = [
        f"# 高海拔葡萄园气候指标报告 —— {context.site_name}",
        "",
        f"- 生成时间：{now}",
        f"- 工具：vineclim {__version__}",
        f"- 输入：`{context.input_path.name}`（{context.n_rows} 行，覆盖 {context.coverage[0]} 至 {context.coverage[1]}）",
        f"- 站点：纬度 {context.latitude:.4f}°（{context.hemisphere}），经度 {site_lon}",
        f"- 数据性质：**{context.source_label}**",
        f"- Huglin 纬度系数 k = {context.huglin_k:.2f}",
        "",
        "## 1. 重要提示",
        "",
    ]

    if context.source_type == "power-grid":
        lines += [
            f"> **{POWER_CAVEAT}。** POWER 是 0.5° × 0.625° 的网格产品，一个格点覆盖数十公里，",
            "> 海拔为格点平均海拔。它适合做区域气候背景比较，不能代替园地气象站，",
            "> 也不能据此判定某个地块的适宜性。",
            "",
        ]
    elif context.source_type == "synthetic":
        lines += ["> **这是合成数据，不是观测。** 仅用于演示流程与边界条件。", ""]
    else:
        lines += [
            "> 输入按台站观测处理。请自行核对传感器校准、遮挡、海拔与坐标；",
            "> 若文件实际来自网格产品，其代表性受格点分辨率限制。",
            "",
        ]

    if context.source_note:
        lines += [f"- 来源备注：{context.source_note}", ""]

    lines += ["## 2. 海拔订正", ""]
    if correction is not None:
        lines += [
            "启用订正：`T' = T + lapse × (grid_elev − station_elev) / 1000`。",
            "",
            f"- 格点海拔：{correction.grid_elev_m:.1f} m",
            f"- 假定园地海拔：{correction.station_elev_m:.1f} m",
            f"- 递减率：{correction.lapse_c_per_km:.2f} °C/km",
            f"- 温度偏移：**{correction.offset_c:+.2f} °C**（逐日加到 Tmin 与 Tmax）",
            "",
            f"> **{CORRECTION_CAVEAT}。** 恒定递减率忽略逆温、坡向、冷空气沉积与植被；",
            "> 下表同时保留未订正与订正值，请勿只引用订正值。",
            "",
        ]
    else:
        lines += [
            "未启用海拔订正。若输入为网格值且格点海拔显著高于园地，应提供",
            "`--station-elev` 与 `--grid-elev`，并同时查看订正前后值。",
            "",
        ]

    lines += [
        "## 3. 指标定义",
        "",
        "Tmean = (Tmax + Tmin) / 2，全部按日值计算。缺测 >20% 的指标/年份标记为",
        "`insufficient_data`；缺测值不参与累计，但计入缺测比例。",
        "",
    ]
    for key in METRIC_ORDER:
        definition = METRICS[key]
        lines.append(
            f"- **{definition.label_zh}**（{definition.label_en}，{definition.unit}）：{definition.description_zh}"
        )
    lines += [
        "",
        "## 4. 逐年结果",
        "",
        "表格中的有效天数是实际参与计算的天数；缺测为评估窗口内缺测天数。",
        "",
    ]
    for key in METRIC_ORDER:
        lines += [f"### {METRICS[key].label_zh}（{METRICS[key].unit}）", ""]
        lines += _metric_table(result, key, corrected)
        lines.append("")

    lines += ["## 5. 多年气候概况", ""]
    lines += _climatology_table(result, corrected)
    lines += [
        "",
        "多年均值只使用状态为 `ok` 的年份。缺测年数包含数据未覆盖的年份。",
        "",
        "## 6. 解释", "",
    ]
    lines += _interpretation(result)
    lines += [
        "",
        "高海拔产区的辐射、紫外与日较差条件常优于同纬平原，但热量与霜冻窗口更紧。",
        "上述分级来自温带葡萄区（Huglin 1978；Tonietto & Carbonneau 2004），",
        "在德钦这类纵向河谷只用于比较，**不作绝对适宜性结论**。",
        "",
        "## 7. 局限",
        "",
        "- POWER 网格值不是园地实测，存在尺度不匹配与海拔偏差。",
        "- 线性递减率订正为示意，未模拟逆温与坡位。",
        "- 累计型指标对缺测敏感；即使缺测比例未超阈值，插补缺口仍会低估累积量。",
        "- 霜冻按日最低温 < 0 °C 计数，未使用芽期物候，也不区分霜冻类型。",
        "- 未计算辐射、湿度、风与土壤水分；水分胁迫需另行观测。",
        "- `insufficient_data` 阈值 20% 是项目约定，不是法规标准。",
        "",
        "## 8. 参考",
        "",
        "- Huglin, P. (1978). *Nouveau mode d'évaluation des possibilités héliothermiques d'un milieu viticole.*",
        "- Tonietto, J., & Carbonneau, A. (2004). A multicriteria climatic classification system for grape-growing regions worldwide. *Agricultural and Forest Meteorology*, 124, 81–97.",
        "- Gladstones, J. (1992). Viticulture and environment. Winetitles.",
        "- OIV (2012). *OIV Guidelines for Vitiviniculture Zoning.*",
        "- NASA POWER daily API: https://power.larc.nasa.gov/",
        "",
        "公式、单位与完整假设见仓库 `docs/methods.md`。",
        "",
        "## English summary",
        "",
        "vineclim computes heat accumulation (GDD10, Huglin), cool-night, frost,",
        "hot-day, growing-season and diurnal-range indices from daily temperature.",
        "Values are shown uncorrected and, optionally, after a documented lapse-rate",
        "correction. NASA POWER grid values are not vineyard measurements; the",
        "correction is illustrative, and the temperate-zone classes are comparative.",
        "",
    ]
    return "\n".join(lines)


def build_document(result: dict[str, Any], context: ReportContext) -> dict[str, Any]:
    correction: ElevationCorrection | None = result["correction"]
    years = []
    for year_entry in result["years"]:
        indices = {}
        for key, entry in year_entry["indices"].items():
            indices[key] = {
                name: (round(item, 4) if isinstance(item, float) else item)
                for name, item in entry.items()
            }
        years.append({"year": year_entry["year"], "indices": indices})
    return {
        "tool": "vineclim",
        "version": __version__,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "input": {
            "file": context.input_path.name,
            "rows": context.n_rows,
            "coverage": {"start": context.coverage[0], "end": context.coverage[1]},
        },
        "site": {
            "name": context.site_name,
            "latitude": context.latitude,
            "longitude": context.longitude,
            "hemisphere": context.hemisphere,
            "huglin_k": context.huglin_k,
        },
        "data_source": {
            "type": context.source_type,
            "label": context.source_label,
            "note": context.source_note,
            "power_is_not_measured": context.source_type == "power-grid",
        },
        "elevation_correction": (
            {
                "enabled": True,
                "station_elev_m": correction.station_elev_m,
                "grid_elev_m": correction.grid_elev_m,
                "lapse_c_per_km": correction.lapse_c_per_km,
                "offset_c": round(correction.offset_c, 3),
                "illustrative": True,
            }
            if correction
            else {"enabled": False}
        ),
        "missing_threshold": 0.2,
        "metric_definitions": {
            key: {
                "label_zh": METRICS[key].label_zh,
                "label_en": METRICS[key].label_en,
                "unit": METRICS[key].unit,
                "description_zh": METRICS[key].description_zh,
            }
            for key in METRIC_ORDER
        },
        "years": years,
        "climatology": result["climatology"],
        "disclaimers": [POWER_CAVEAT, CORRECTION_CAVEAT] if correction else [POWER_CAVEAT],
    }


def write_indices_json(
    result: dict[str, Any], context: ReportContext, path: str | Path
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = build_document(result, context)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_indices_csv(result: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    correction = result["correction"] is not None
    fieldnames = [
        "year",
        "metric",
        "value",
        "value_corrected",
        "n_days",
        "n_missing",
        "missing_fraction",
        "status",
        "status_corrected",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in result["rows"]:
            out = {name: row.get(name, "") for name in fieldnames}
            if not correction:
                out["value_corrected"] = ""
                out["status_corrected"] = ""
            for name in ("value", "value_corrected"):
                if out[name] not in ("", None):
                    out[name] = f"{float(out[name]):.2f}"
            if out["missing_fraction"] not in ("", None):
                out["missing_fraction"] = f"{float(out['missing_fraction']):.4f}"
            writer.writerow(out)
    return path


def write_report(
    result: dict[str, Any], context: ReportContext, path: str | Path
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(result, context), encoding="utf-8")
    return path
