#!/usr/bin/env python3
"""Download NASA POWER daily data, or convert a saved POWER JSON payload.

Examples
--------
Convert the archived Deqin payload::

    python scripts/fetch_power.py --input-json ../_research/power_deqin.json \
        --output examples/deqin_power_2015_2025.csv --retrieved 2026-11-17

Download anew::

    python scripts/fetch_power.py --lat 28.55 --lon 98.86 --start 2015 --end 2025 \
        --output examples/deqin_power_2015_2025.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vineclim.fetch import fetch_power, parse_power_json, write_csv, write_metadata  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="下载或转换 NASA POWER 日值")
    parser.add_argument("--input-json", type=Path, default=None, help="转换已保存的 POWER JSON")
    parser.add_argument("--lat", type=float, default=28.55)
    parser.add_argument("--lon", type=float, default=98.86)
    parser.add_argument("--start", type=int, default=2015)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, default=None, help="元数据 JSON 输出路径")
    parser.add_argument("--retrieved", default=dt.date.today().isoformat(), help="检索日期 YYYY-MM-DD")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output.exists() and not args.force:
        print(f"输出已存在: {args.output}（加 --force 覆盖）", file=sys.stderr)
        return 2

    if args.input_json:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        frame, metadata = parse_power_json(payload)
        metadata["retrieved"] = args.retrieved
        metadata["input_json"] = str(args.input_json)
        geometry = payload.get("geometry", {}).get("coordinates", [])
        if len(geometry) >= 2:
            metadata["grid_longitude"] = geometry[0]
            metadata["grid_latitude"] = geometry[1]
        start = str(frame["date"].min())
        end = str(frame["date"].max())
        print(f"转换 {len(frame)} 天（{start} 至 {end}）")
    else:
        frame, metadata = fetch_power(args.lat, args.lon, args.start, args.end)
        metadata["retrieved"] = args.retrieved
        start = str(frame["date"].min())
        end = str(frame["date"].max())
        print(f"下载 {len(frame)} 天（{start} 至 {end}）")

    write_csv(frame, args.output)
    print(f"已写入 {args.output}")
    if metadata.get("grid_elevation_m") is not None:
        print(f"网格海拔: {metadata['grid_elevation_m']:.2f} m")
    metadata["warning"] = "NASA POWER grid values are not vineyard measurements."
    metadata["generated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    if args.metadata:
        write_metadata(metadata, args.metadata)
        print(f"元数据 -> {args.metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
