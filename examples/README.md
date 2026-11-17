# 示例数据

## `deqin_power_2015_2025.csv` — 公开网格数据

- 来源：NASA POWER Daily API，`T2M_MAX,T2M_MIN,PRECTOTCORR`，社区 `AG`。
- 坐标：98.86°E, 28.55°N（云南德钦附近），POWER 网格分辨率 0.5° × 0.625°。
- 网格海拔：3879.61 m（POWER 响应 `geometry.coordinates[2]`）。
- 时间：2015-01-01 至 2025-12-31，共 4018 天，无填充值。
- 检索日期：2026-11-17。
- 转换：`scripts/fetch_power.py --input-json ... --retrieved 2026-11-17`。
- **这不是园地实测**；网格海拔比德钦河谷园地高约 1600–1900 m。

请求 URL：

```
https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MAX,T2M_MIN,PRECTOTCORR&community=AG&longitude=98.86&latitude=28.55&start=20150101&end=20251231&format=JSON&time-standard=LST
```

同目录 `deqin_power_metadata.json` 保存了 API 版本、来源与网格海拔等响应元数据。

## `synthetic_station.csv` — 合成演示

- 2024 年逐日，虚构站点，正弦季节循环 + 随机噪声。
- 故意包含三段连续缺测（4 月 10–14 日、9 月 5–12 日、12 月 20–23 日），用于演示缺测与 `insufficient_data`。
- **合成数据，不是观测**，不可用于科研结论。

## 快速试跑

```bash
vineclim compute examples/synthetic_station.csv --lat 28.5 --year 2024 --source-type synthetic -o out/synthetic
```
