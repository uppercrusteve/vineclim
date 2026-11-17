"""Command-line interface.

Exit codes: 0 success, 2 invalid input or data error, 3 network failure.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from . import __version__
from .data import DataError, available_years, coverage, load_csv
from .fetch import FetchError, fetch_power, write_csv, write_metadata
from .indices import ElevationCorrection, compute_indices, correction_frame
from .plot import make_all_plots
from .report import (
    ReportContext,
    detect_source_type,
    write_indices_csv,
    write_indices_json,
    write_report,
)

DESCRIPTION = """\
vineclim —— 高海拔葡萄园气候指标计算与可复现报告。

计算 GDD10、Huglin 热指数、冷夜指数、霜冻日、高温日、生长季长度与昼夜温差。
支持台站 CSV 与 NASA POWER 下载；缺测 >20% 自动标记 insufficient_data。
"""


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="输入 CSV（date,tmin_c,tmax_c,precip_mm）")
    parser.add_argument("--lat", type=float, required=True, help="站点纬度（-90…90，南半球为负）")
    parser.add_argument("--lon", type=float, default=None, help="站点经度（写入报告，可选）")
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        default=None,
        help="只计算指定年份，可重复；缺省为数据中的全部年份",
    )
    parser.add_argument("--start-year", type=int, default=None, help="起始年（与 --end-year 同用）")
    parser.add_argument("--end-year", type=int, default=None, help="结束年（含）")
    parser.add_argument(
        "--station-elev",
        type=float,
        default=None,
        help="园地海拔 m；与 --grid-elev 同时给出才启用订正",
    )
    parser.add_argument("--grid-elev", type=float, default=None, help="数据网格海拔 m")
    parser.add_argument("--lapse", type=float, default=6.5, help="温度递减率 °C/km，默认 6.5")
    parser.add_argument(
        "--source-type",
        choices=("auto", "power-grid", "station", "synthetic"),
        default="auto",
        help="数据性质，写入报告（默认按文件名推断）",
    )
    parser.add_argument("--source-note", default="", help="额外来源说明，写入报告")
    parser.add_argument("--site-name", default="研究站点", help="站点名，写入报告与图标题")
    parser.add_argument("--no-plots", action="store_true", help="不生成 PNG 图")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vineclim",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"vineclim {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="命令")

    compute = subparsers.add_parser("compute", help="计算指标并输出 JSON/CSV/报告/图")
    _add_common_arguments(compute)
    compute.add_argument("-o", "--outdir", type=Path, required=True, help="输出目录")

    report = subparsers.add_parser("report", help="与 compute 相同，便于语义化调用")
    _add_common_arguments(report)
    report.add_argument("-o", "--outdir", type=Path, default=Path("vineclim-report"), help="输出目录")

    fetch = subparsers.add_parser("fetch", help="下载 NASA POWER 日值并转为 CSV")
    fetch.add_argument("--lat", type=float, required=True, help="纬度")
    fetch.add_argument("--lon", type=float, required=True, help="经度")
    fetch.add_argument("--start", type=int, required=True, help="起始年（含）")
    fetch.add_argument("--end", type=int, required=True, help="结束年（含）")
    fetch.add_argument("-o", "--output", type=Path, required=True, help="输出 CSV")
    fetch.add_argument("--metadata", type=Path, default=None, help="另存响应元数据 JSON")
    fetch.add_argument("--force", action="store_true", help="覆盖已存在的输出文件")
    return parser


def _validate_years(args: argparse.Namespace) -> list[int] | None:
    if args.year and (args.start_year or args.end_year):
        raise DataError("--year 不能与 --start-year/--end-year 同时使用")
    if args.year:
        years = sorted(set(args.year))
    elif args.start_year is not None or args.end_year is not None:
        if args.start_year is None or args.end_year is None:
            raise DataError("--start-year 与 --end-year 必须同时给出")
        if args.start_year > args.end_year:
            raise DataError("--start-year 不能晚于 --end-year")
        years = list(range(args.start_year, args.end_year + 1))
    else:
        return None
    for year in years:
        if not 1800 <= year <= 2200:
            raise DataError(f"年份超出范围: {year}")
    return years


def _build_correction(args: argparse.Namespace) -> ElevationCorrection | None:
    if (args.station_elev is None) != (args.grid_elev is None):
        raise DataError("--station-elev 与 --grid-elev 必须同时提供")
    if args.station_elev is None:
        return None
    if not math.isfinite(args.lapse) or not 0 < args.lapse <= 20:
        raise DataError("--lapse 必须在 (0, 20] °C/km 内")
    for name, value in (("--station-elev", args.station_elev), ("--grid-elev", args.grid_elev)):
        if not math.isfinite(value) or not -500 <= value <= 9000:
            raise DataError(f"{name} 必须在 -500 到 9000 m 之间")
    return ElevationCorrection(
        station_elev_m=args.station_elev,
        grid_elev_m=args.grid_elev,
        lapse_c_per_km=args.lapse,
    )


def _run_analysis(args: argparse.Namespace) -> int:
    if not math.isfinite(args.lat) or abs(args.lat) > 90:
        raise DataError("--lat（纬度）必须在 -90 到 90 之间")
    if args.lon is not None and (not math.isfinite(args.lon) or abs(args.lon) > 180):
        raise DataError("--lon 必须在 -180 到 180 之间")

    years = _validate_years(args)
    frame = load_csv(args.input)
    data_years = available_years(frame)
    if years is None:
        years = data_years
    correction = _build_correction(args)

    result = compute_indices(frame, args.lat, years, correction)
    source_type = detect_source_type(args.input) if args.source_type == "auto" else args.source_type
    context = ReportContext(
        input_path=args.input,
        latitude=args.lat,
        longitude=args.lon,
        source_type=source_type,
        source_note=args.source_note,
        coverage=coverage(frame),
        n_rows=len(frame),
        hemisphere=result["hemisphere"],
        huglin_k=result["huglin_k"],
        site_name=args.site_name,
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = [
        write_indices_json(result, context, outdir / "indices.json"),
        write_indices_csv(result, outdir / "indices.csv"),
        write_report(result, context, outdir / "report.md"),
    ]
    if not args.no_plots:
        corrected = correction_frame(frame, correction) if correction else None
        data_note = {
            "power-grid": "NASA POWER 网格值不是园地实测",
            "synthetic": "合成演示数据，不是观测",
            "station": "台站数据，需核对观测质量",
        }[source_type]
        written += make_all_plots(
            result,
            frame,
            corrected,
            args.lat,
            correction,
            outdir,
            site_name=args.site_name,
            data_note=data_note,
        )

    print("vineclim 完成。")
    print(f"年份: {years[0]}–{years[-1]} | 半球: {result['hemisphere']} | 纬度: {args.lat:.3f}")
    print(f"数据性质: {source_type}")
    if source_type == "power-grid":
        print("注意: POWER 网格值不是园地实测。")
    if correction:
        print(
            f"海拔订正（示意）: {correction.offset_c:+.2f} °C；"
            "报告同时保留未订正与订正值。"
        )
    elif source_type == "power-grid":
        print("提示: 未启用海拔订正；可加 --station-elev/--grid-elev 查看订正前后值。")
    for path in written:
        print(f"  -> {path}")
    insufficient = sum(
        1
        for row in result["rows"]
        if row["status"] == "insufficient_data"
    )
    print(f"insufficient_data 条目: {insufficient}/{len(result['rows'])}")
    return 0


def _run_fetch(args: argparse.Namespace) -> int:
    if args.output.exists() and not args.force:
        raise FetchError(f"输出已存在: {args.output}（加 --force 覆盖）")
    frame, metadata = fetch_power(args.lat, args.lon, args.start, args.end)
    write_csv(frame, args.output)
    if args.metadata:
        write_metadata(metadata, args.metadata)
    print(f"已下载 {len(frame)} 天 -> {args.output}")
    if metadata.get("grid_elevation_m") is not None:
        print(f"网格海拔: {metadata['grid_elevation_m']:.1f} m（计算时可用 --grid-elev 传入）")
    print("提醒: POWER 是网格产品，不是园地实测。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            return _run_fetch(args)
        return _run_analysis(args)
    except (DataError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except FetchError as exc:
        print(f"下载错误: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"文件错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
