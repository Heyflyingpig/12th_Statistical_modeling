# 韶关市住宅空置风险识别、分型与转移预测项目说明

本项目面向第十二届统计建模竞赛，研究对象为广东省韶关市，目标是在统一的 500m 格网尺度上，利用遥感、夜间灯光、POI、行政区划和空间统计方法识别住宅空置风险，进一步区分空置形成机制，并分析风险的空间集聚、状态转移和下一年非高风险格网转为高风险的概率。

当前 README 根据根目录 `Agent.md`、`Q1/Q1_Agent.md`、`Q2/Q2_Agent.md`、根目录 `Q3_Agent.md` 以及当前代码与输出文件核对整理。`Q3/Q3_Agent.md` 当前为空文件，不作为本文档依据。

## 1. 研究主线

项目主线是：

`统一格网底座 -> 年度 RVRI 指数构建 -> 空置类型识别 -> 空间自相关与状态转移预测`

三个问题之间的关系如下：

1. **Q1 识别问题**：在 2019-2023 年年度尺度上构建住宅空置风险复合指数 `RVRI`，识别“建成强度较高但夜间活力不足”的风险格网。
2. **Q2 区分问题**：继承 Q1 的年度风险面板，不重新构造 RVRI，而是将风险格网划分为稳定占用型、老城衰退型空置、新区扩张型空置和过渡混合型。
3. **Q3 预测问题**：在统一空间样本层上检验 RVRI 的空间自相关、状态转移和邻域扩散效应，并输出下一年非高风险格网转为高风险格网的概率，同时给出未来 10 年低/中/高三类风险状态占比的 Markov 趋势外推。

## 2. 统一空间样本层

当前代码中统一空间分析样本由 `analysis_domain.py` 管理：

- 样本名称：`loose_builtup`
- 建成强度条件：按年度取 `ndbi` 的 60% 分位阈值
- 非裸地/非极端背景条件：`ndvi >= 0.05`
- 不强制要求 POI 或夜间灯光上下文

该规则已被 Q1、Q2、Q3 共同使用：

- Q1：`Q1/03_RVRI_Advanced_Validation.py` 调用 `attach_unified_analysis_domain`
- Q2：`Q2/04_screen_builtup_and_candidates.py` 使用相同的 NDBI 分位和 NDVI 下限生成 `in_analysis_domain`
- Q3：`Q3/q3_utils.py` 在准备年度面板时统一附加 `in_analysis_domain`，`Q3/03_spatial_autocorr.py` 在该样本层内计算 Moran/LISA

当前 Q3 输出显示统一样本层共 `158092` 条年度记录，2023 年样本为 `31637` 个格网。

## 3. Q1：年度 RVRI 构建与验证

Q1 当前正式口径为 **2019-2023 年度 RVRI**，不再采用季度状态转移口径。核心输入是：

- `Q1/data/Shaoguan_RVRI_2019.csv`
- `Q1/data/Shaoguan_RVRI_2020.csv`
- `Q1/data/Shaoguan_RVRI_2021.csv`
- `Q1/data/Shaoguan_RVRI_2022.csv`
- `Q1/data/Shaoguan_RVRI_2023.csv`

主要脚本：

- `Q1/02_RVRI_Synthesis.py`：合成年度 RVRI 主表
- `Q1/03_RVRI_Advanced_Validation.py`：年度后验验证、空间自相关、POI 外部效度与耦合检验
- `Q1/04_RVRI_ByYear_Batch.py`：逐年验证批处理
- `Q1/05_Q1_Paper_Figures.py`：论文用 Q1 图件

已核验的关键结果来自 `Q1/output/validation_report.json`：

- 年度样本数：`396302`
- 建成区子样本 `corr_rvri_light = -0.3514`
- 核心建成区 `corr_rvri_light = -0.6679`
- 2023 年 `Moran's I = 0.5839817461`

因此，当前 RVRI 更适合解释为“在建成区样本中识别房多灯暗错配风险”，而不是在全市所有背景格网上直接解释空置。

## 4. Q2：空置风险类型识别

Q2 不重建 RVRI，而是继承 `Q1/output/Shaoguan_RVRI_Q1_Validated.csv`，围绕 2023 当前状态、2019-2023 趋势特征、空间区位和 POI 密度进行规则型分型。

主要脚本：

- `Q2/01_build_q2_basepanel.py`：抽取 Q1 年度面板字段
- `Q2/02_enrich_spatial_context.py`：补充 geometry、POI 与本地核心距离，完整重跑该步仍需要 `geopandas`
- `Q2/03_engineer_temporal_features.py`：构造趋势和机制特征
- `Q2/04_screen_builtup_and_candidates.py`：统一样本层与候选格网筛选
- `Q2/05_classify_vacancy_types.py`：双得分规则分类
- `Q2/06_validate_q2_typology.py`：分型后验验证
- `Q2/07_export_q2_deliverables.py`：导出最终表和地图
- `Q2/08_plot_q2_figures.py`：不依赖 geopandas 的轻量绘图脚本

已核验的 Q2 最终分类结果来自 `Q2/output/Q2_Typology_Summary_Overall.csv`：

| 类型 | 含义 | 样本数 | 占比 |
|---|---|---:|---:|
| 0 | 稳定占用型 | 47855 | 60.31% |
| 1 | 老城衰退型空置 | 11384 | 14.35% |
| 2 | 新区扩张型空置 | 10817 | 13.63% |
| 3 | 过渡混合型 | 9297 | 11.72% |

Q2 图件脚本当前直接读取 `Q2/output/final/Q2_Type_Map.geojson` 和 `Q1/data/shaoguan_districts_official.json`，通过 `json + pandas + matplotlib` 绘图，不依赖 geopandas。地图中已加入区县边界黑线。

## 5. Q3：空间自相关、转移与预测

Q3 当前正式口径为年度状态转移。核心输入来自 Q1 年度主表和 500m 格网底图：

- `Q1/output/Shaoguan_RVRI_Q1_Validated.csv`
- `Q1/data/scientific_grid_500m.geojson`

主要脚本：

- `Q3/01_prepare_q3_panel.py`：构造 Q3 年度面板和相邻年度转移样本
- `Q3/02_build_spatial_weights.py`：构建格网邻接权重
- `Q3/03_spatial_autocorr.py`：逐年 Moran's I 与最新年度 LISA
- `Q3/04_markov_transition.py`：总体和区县状态转移矩阵
- `Q3/05_spatial_markov.py`：邻域风险条件下的空间 Markov 对比
- `Q3/06_low_to_high_predict.py`：下一年非高风险转高风险概率预测，并输出 10 年风险状态占比趋势外推

已核验的 Q3 空间自相关结果来自 `Q3/output/annual_moran_report.csv`：

| 年份 | Moran's I | p-value | 分析样本数 |
|---:|---:|---:|---:|
| 2019 | 0.5517 | 0.005 | 31630 |
| 2020 | 0.5624 | 0.005 | 31605 |
| 2021 | 0.5916 | 0.005 | 31622 |
| 2022 | 0.5374 | 0.005 | 31598 |
| 2023 | 0.5840 | 0.005 | 31637 |

其中 2023 年 Moran's I 与 Q1 后验验证报告中的 `0.5839817461` 一致，说明 Q1/Q3 已对齐到同一空间样本层和同一年度 RVRI 口径。

最新一次 `Q3/06_low_to_high_predict.py` 重跑后，预测目标已经从旧的“低风险 -> 高风险”调整为 **“非高风险 -> 高风险”**，即同时对 2023 年的低风险和中风险格网进行下一年升级概率识别。当前输出显示：

- 预测基准年：`2023`
- 预测目标年：`2024`
- 格网级评分样本数：`6373`
- `ROC-AUC = 0.6483`
- `Top 10% hit rate = 40.29%`
- `Lift@10% = 1.5872`
- `AUC >= 0.70` 和 `Lift@10% >= 2.0` 两个原设强筛查门槛尚未同时达到

因此，下一年格网级概率图应表述为“非高风险格网升级为高风险的重点筛查图”，而不是高精度预测图。长期部分采用 Markov 状态转移矩阵做 **10 年低/中/高风险占比趋势外推**，输出 `Q3/output/q3_risk_state_projection_10yr.csv`、`Q3/output/q3_risk_state_projection_10yr.json` 和 `Q3/output/Q3_Risk_State_Projection_10yr.png`。这一部分适合作为趋势情景分析，不应写成精确到格网的 10 年预测。

## 6. 图件约定

当前论文图件统一遵循：

- 输出图不设置主标题，论文或 Word 中另行添加图题。
- LISA 颜色沿用 Q1 LISA 配色：
  - `HH`: `#e31a1c`
  - `LL`: `#1f78b4`
  - `HL`: `#fb9a99`
  - `LH`: `#a6cee3`
  - `NS`: `#d9d9d9`，仅用于显著性 LISA 图中的非显著格网
- Q2/Q3 空间图均叠加 `Q1/data/shaoguan_districts_official.json` 的区县边界黑线。

主要图件：

- Q1：`Q1/output/Q1_LISA_Map.png`、`Q1/output/Q1_Annual_Evolution_Summary.png`
- Q2：`Q2/output/Q2_Typology_Map_Overall.png`、`Q2/output/Q2_Typology_Map_Focus.png`、`Q2/output/Q2_Typology_Share_By_District.png`
- Q3：`Q3/output/Q3_LISA_Map.png`、`Q3/output/Q3_Moran_Trend.png`、`Q3/output/Q3_NonHighToHigh_Risk_Map.png`、`Q3/output/Q3_Risk_State_Projection_10yr.png`

## 7. 推荐运行顺序

若从当前已有输出继续生成论文图和交付文件，推荐顺序为：

```powershell
python Q1/05_Q1_Paper_Figures.py
python Q2/08_plot_q2_figures.py
python Q3/03_spatial_autocorr.py --permutations 199
python Q3/06_low_to_high_predict.py
```

若从 Q2 中间表重跑到最终图件：

```powershell
python Q2/04_screen_builtup_and_candidates.py
python Q2/05_classify_vacancy_types.py
python Q2/06_validate_q2_typology.py
python Q2/07_export_q2_deliverables.py
python Q2/08_plot_q2_figures.py
```

完整从空间上下文重建 Q2 时，`Q2/02_enrich_spatial_context.py` 仍需要安装并可用的 `geopandas` 环境。

## 8. 当前交付判断

截至当前代码与输出核验：

- Q1 已完成年度 RVRI 指数构建、建成区有效性检验和 2023 空间自相关验证。
- Q2 已完成四类型分型、区县汇总、最终表与轻量绘图输出。
- Q3 已完成年度 Moran/LISA、状态转移、空间 Markov、非高风险转高风险概率预测和 10 年状态占比趋势外推；其中格网级预测模块尚未达到原设强预测门槛，应审慎表述为“重点筛查与趋势情景分析”。
- 根目录 README 已从原先单一 Q3 说明调整为项目级说明，并将 Agent.md 中的规划性表述与当前代码/输出结果分开说明。
