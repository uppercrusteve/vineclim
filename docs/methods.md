# 方法与局限

本文档给出 vineclim 0.1.0 的全部指标定义、单位、缺测规则、海拔订正假设
与文献出处。README 只做摘要，正式引用或复算时以本文档和源码为准。

## 0. 输入与基本量

输入为逐日表：`date,tmin_c,tmax_c,precip_mm`。

- `date`：`YYYY-MM-DD`，重复日期报错。
- `tmin_c` / `tmax_c`：日最低 / 最高气温，单位 °C；`tmin_c > tmax_c` 报错。
- `precip_mm`：日降水量，单位 mm，当前版本只用于气候概况图，不参与指标计算。
- 缺失：空单元格，或 POWER 填充值 `-999` / `-9999`，读入后转为 NaN。
- `Tmean = (Tmin + Tmax) / 2`，单位 °C。

所有指标按日值计算，不做月插值，也不做时间聚合以外的平滑。

## 1. 指标公式与单位

### 1.1 生长度日 GDD10

```
GDD10(year) = Σ_days max(0, Tmean − 10 °C)
```

- 基温：10 °C。
- 单位：°C·d（度日）。
- 求和窗口：日历年全年；非生长季日贡献为 0，因此等价于生长季累计。
- 出处：通用度日定义；葡萄物候常用基温见 Gladstones (1992)。

### 1.2 Huglin 热指数 HI

```
HI(year) = Σ_window max(0, ((Tmean − 10) + (Tmax − 10)) / 2) × k
```

- 北半球窗口：4 月 1 日–9 月 30 日；南半球窗口：上年 10 月 1 日–当年 3 月 31 日。
- `k` 为纬度系数，按 Huglin (1978) 的分段表（取纬度绝对值）：

| 纬度 | k |
|---|---:|
| < 40° | 1.00 |
| 40°–41.99° | 1.02 |
| 42°–43.99° | 1.03 |
| 44°–45.99° | 1.04 |
| 46°–47.99° | 1.05 |
| ≥ 48° | 1.06 |

- 单位：°C·d。
- 出处：Huglin (1978)。低于 40° 取 1.00 是项目简化；原表在 50° 结束，
  更高纬度沿用 1.06。
- 分级来自温带产区，仅作横向参考，见第 5 节。

### 1.3 冷夜指数 CI

```
CI(year) = mean(Tmin over September)        # 北半球
CI(year) = mean(Tmin over March)            # 南半球
```

- 单位：°C。
- 出处：Tonietto & Carbonneau (2004)，原定义用于成熟期夜温。

### 1.4 霜冻日

```
frost_days(year)         = count(Tmin < 0 °C, 全年)
spring_frost_days(year)  = count(Tmin < 0 °C, 北半球 4–5 月 / 南半球 9–11 月)
autumn_frost_days(year)  = count(Tmin < 0 °C, 北半球 10 月 / 南半球 4–5 月)
```

- 单位：d（天）。
- 0 °C 为日最低气温阈值，未区分辐射霜与平流霜，也未结合芽期物候。

### 1.5 高温日

```
hot_days_35c(year) = count(Tmax > 35 °C, 全年)
```

- 单位：d。
- 35 °C 为通用阈值，不是品种特异阈值。

### 1.6 生长季长度

```
growing_season_length(year) = count(Tmean ≥ 10 °C, 全年)
```

- 单位：d。
- 是全年满足条件的累计天数，不是最长连续段；孤立暖日也会计入。

### 1.7 生长季昼夜温差

```
diurnal_range_gs(year) = mean(Tmax − Tmin | Tmean ≥ 10 °C)
```

- 单位：°C。
- 只在 Tmean ≥ 10 °C 的日子上取平均；昼夜温差本身不受恒定海拔偏移影响。

## 2. 缺测规则

- 每个指标的评估窗口独立计算缺测比例：`n_missing / n_window`。
- 缺测比例 **> 20 %** 时，该指标/年份标记为 `insufficient_data`；
  恰好 20 % 仍为 `ok`（阈值比较用严格大于）。
- 缺测日不参与累计或平均，但保留在缺测计数与缺测比例中。
- 整个窗口都缺测时值为 `null`，状态为 `insufficient_data`。
- 累计型指标（GDD、Huglin、霜冻日、高温日、生长季长度）在缺测日直接跳过，
  因此即使未超过 20 %，累计值仍可能偏低；阈值不修复缺口。
- 20 % 是项目约定，不是法规或 WMO 标准。
- 多年均值只使用状态为 `ok` 的年份；缺测年数一并报告。

## 3. 海拔订正

命令同时给出 `--station-elev` 与 `--grid-elev` 时启用：

```
T'(d) = T(d) + lapse_c_per_km × (grid_elev_m − station_elev_m) / 1000
```

- 默认 `lapse_c_per_km = 6.5`，允许范围 (0, 20] °C/km。
- 同一偏移逐日加到 Tmin 与 Tmax 上，因此 Tmean、日较差和以温度为唯一
  输入的分级会改变；日较差本身平移后不变。
- 未订正值始终保留；JSON、CSV 与报告同时给出订正值，订正状态单独标记。
- 订正是**示意**：恒定递减率不模拟逆温、坡向、冷空气沉积、植被与水体。
  德钦示例的 −10.92 °C 偏移（3879.6 m → 2200 m，6.5 °C/km）只用于演示
  方向与量级，不是园地实测温度。

## 4. 数据来源与尺度

- `examples/deqin_power_2015_2025.csv` 来自 NASA POWER Daily API
  （`T2M_MAX,T2M_MIN,PRECTOTCORR`，社区 `AG`，坐标 98.86°E、28.55°N，
  2015-01-01–2025-12-31，检索日期 2026-11-17）。
- POWER 是 0.5° × 0.625° 的网格产品，一个格点覆盖数十公里。
  响应中的格点海拔为 3879.61 m，明显高于德钦河谷园地（示例假定 2200 m，
  仅作订正演示）。**网格值不是园地实测。**
- 网格值适合区域气候背景与年际比较，不能替代园地气象站，也不能据此
  判定地块适宜性。
- 示例中的 2200 m 是示意海拔，不是实测地块坐标或实测海拔。

## 5. 分级

- Huglin 分级阈值：1200 / 1500 / 1800 / 2100 / 2400 / 3000 °C·d；
- 冷夜指数分级阈值：14 / 16 / 18 / 20 °C；
- GDD、霜冻日、高温日、生长季长度与昼夜温差的分级为项目内约定。

这些分级源自温带葡萄产区（Huglin 1978；Tonietto & Carbonneau 2004），
在高海拔纵向河谷只用于横向比较，**不作绝对适宜性结论**。

## 6. 单位与符号约定

| 指标 | 单位 |
|---|---|
| GDD10、Huglin HI | °C·d |
| 冷夜指数、昼夜温差、温度偏移 | °C |
| 霜冻日、春霜日、秋霜日、高温日、生长季长度 | d |
| 海拔、格点海拔 | m |
| 递减率 | °C/km |

南半球由负纬度触发窗口镜像；赤道（0°）按北半球处理。

## 7. 局限

- 网格尺度不匹配：格点代表数十公里平均，海拔为格点平均海拔。
- 线性递减率订正忽略逆温、坡位、冷空气沉积与局地增温。
- 只使用 Tmin/Tmax；没有辐射、湿度、风、土壤水分与水分胁迫指标。
- 霜冻只看日最低温，未使用芽期/物候，也未区分霜冻类型与持续时间。
- 累计指标对缺测敏感，缺口会低估累积量；`insufficient_data` 只是标记。
- 昼夜温差与生长季长度在恒定温度偏移下对订正不敏感或部分不敏感，
  不能单独用作订正效果的证据。
- Huglin `k` 在高海拔的实际适用性未经本地率定；> 50° 与 < 40° 的取值
  是简化。
- 日值来自 POWER 的再分析/卫星融合产品，本身已有模型误差。
- 输出为年度指标与多年均值，不含趋势检验、显著性检验或空间插值。

## 8. 参考文献

- Huglin, P. (1978). Nouveau mode d'évaluation des possibilités
  héliothermiques d'un milieu viticole. *Comptes Rendus de l'Académie
  d'Agriculture de France*, 64, 1117–1126.
- Tonietto, J., & Carbonneau, A. (2004). A multicriteria climatic
  classification system for grape-growing regions worldwide.
  *Agricultural and Forest Meteorology*, 124(1–2), 81–97.
  <https://doi.org/10.1016/j.agrformet.2003.06.001>
- Gladstones, J. (1992). *Viticulture and Environment*. Winetitles,
  Adelaide.
- OIV (2012). *OIV Guidelines for Vitiviniculture Zoning*.
- NASA POWER Daily API: <https://power.larc.nasa.gov/>
