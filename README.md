# 12th_Statistical_modeling
the 12th Statistical modeling competition

## Q1 审查回复版 README（对应 `Q1/Q1_review.md`）

更新时间：2026-04-20  
范围：Q1 住宅空置风险指数（RVRI）构建与底座数据质量整改

---

## 1. 当前可复跑链路

### 1.1 依赖环境
- 依赖文件：`requirements.txt`
- 关键库：`geopandas`, `pandas`, `numpy`, `scikit_learn`, `matplotlib`, `seaborn`, `shapely`

### 1.2 核心脚本
- 格网构建：`Q1/01_Grid_Generator.py`
- RVRI 合成与审计：`Q1/02_RVRI_Synthesis_V4.py`
- 高级校验（开发中）：`Q1/03_RVRI_Advanced_Validation.py`

### 1.3 关键产物（最新）
- 面板 CSV：`Q1/output/Shaoguan_RVRI_Long_Panel_Final.csv`
- 空间快照：`Q1/output/Shaoguan_RVRI_Long_Panel_Final.geojson`
- 审计报告：`Q1/output/validation_report.json`
- 可视化：
  - `Q1/output/Q1_RVRI_Scientific_Check.png`
  - `Q1/output/Q1_RVRI_Light_Binned_Trend.png`

---

## 1.4 开发状态说明（03 仍在开发中）

`Q1/03_RVRI_Advanced_Validation.py` / `Q1/03_RVRI_Advanced_Validation.ipynb` 当前为**持续开发版本**，用于承接：
- Step 7：空间自相关诊断（Global Moran's I / LISA）
- Step 5：社会生态效度校验（RVRI vs POI 密度）
- Step 6：珞珈一号与降尺度夜光一致性校验

当前状态：
- Step 7 / Step 5：已完成代码骨架与输出接口，受运行环境与在线数据访问影响。
- Step 6：已完成模板，待补充 2018 年珞珈一号与 VIIRS 降尺度栅格后执行。
- 因此 03 相关结果应视为“开发中验证结果”，不作为最终定稿结论。

---

## 2. 对 `Q1_review.md` 的逐条整改回应

### 2.1 RVRI 合成不可复现（高风险）
- 审查问题：缺少标准化、PCA 载荷、方向调整、缺失处理、最终代码。
- 已整改：
  - 在 `Q1/02_RVRI_Synthesis_V4.py` 明确了缺失值处理、标准化、PCA、方向校准、指标落盘流程。
  - 输出 `validation_report.json`，包含解释率、相关性、时间覆盖、载荷信息。
- 结论：**已完成整改**。

### 2.2 “房多灯暗”逻辑不一致（高风险）
- 审查问题：此前风险更像建筑强度主导，且与灯光关系弱或方向不稳定。
- 已整改：
  - 引入 `mismatch_gap = ndbi_n - light_n`。
  - 使用风险同向特征（`mismatch_gap`, `light_neg`, `ndvi_neg`）。
  - 采用单调载荷重构（`pca_monotonic_abs`）稳定方向。
  - 最新审计：`corr_rvri_light = -0.0495`，方向已改为负。
- 结论：**方向已修正，强度仍偏弱（后续可继续增强）**。

### 2.3 非时间面板（高风险）
- 审查问题：旧数据仅 Q1/Q3，不满足状态转移分析。
- 已整改：
  - 当前输出覆盖 `2019Q1-2025Q4`，共 28 个季度（见 `validation_report.json`）。
  - 已包含 `rvri` 与 `risk_state`，可供 Q2/Q3 使用。
- 结论：**已具备季度面板能力**。
- 备注：若严格按更早文档目标 `2016-2026`，目前仍是 `2019-2025` 覆盖。

### 2.4 区县字段命名与缺失（中高风险）
- 审查问题：`district_name_x/y` 混乱，且存在大量空值。
- 已整改：
  - 在 V4 中统一为 `district_name`，并按 `Shaoguan_RVRI_2019.csv` 字典回填。
  - 输出结果中 `district_name` 已可用。
- 结论：**已完成整改**。

### 2.5 格网非米制投影（中风险）
- 审查问题：旧版经纬度步长近似 500m，不是严格米制网格。
- 已整改：
  - `Q1/01_Grid_Generator.py` 使用米制投影（EPSG:4511）构建 500m 网格后再导出。
- 结论：**已完成整改**。

### 2.6 环境不可复跑（中风险）
- 审查问题：缺少依赖声明，脚本运行失败。
- 已整改：
  - 已补 `requirements.txt`。
  - Q1 主流程已固化为可执行脚本。
- 结论：**已完成整改**。

---

## 3. 最新审计摘要（来自 `validation_report.json`）

- `pca_explained_variance`: `60.39%`
- `corr_rvri_mismatch`: `0.9224`
- `corr_rvri_ndbi`: `0.8814`
- `corr_rvri_light`: `-0.0495`
- `time_coverage`: `2019Q1` 至 `2025Q4`（28期）

说明：当前版本已经从“不可复现”升级为“可复现+可审计”。灯光方向已修正为负相关，但负相关幅度仍较弱，后续可继续优化指标权重与变量体系。

---

## 4. 给 Q2 / Q3 的接口字段

`Q1/output/Shaoguan_RVRI_Long_Panel_Final.csv` 主要字段：
- `grid_id`
- `district_name`
- `time`
- `ndbi`, `ndvi`, `light`
- `mismatch_gap`
- `rvri`
- `risk_state`

可直接用于：
- Q2 类型识别（按 `risk_state` / `rvri` 分层）
- Q3 状态转移与扩散分析（按 `grid_id + time` 构建时序）
