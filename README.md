# 12th_Statistical_modeling
the 12th Statistical modeling competition

## Q1 年度版说明

更新时间：2026-04-21  
当前状态：Q1 已从旧的季度口径切换为 `2019-2023` 年度 RVRI 识别链路。

---

## 1. 当前结论

Q1 现在可以继续往下使用，不需要推翻原始思路重做。

但有一个关键前提：

当前夜间灯光虽然已经换成了正确的夜光数据，但时间粒度实际上是“年度夜光复制到季度表”，因此 Q1 的正式建模和验证口径必须统一改成年度版。

也就是说：

1. 第一问可以做，而且 `2019-2023` 五个年份都能进入建模。
2. 当前方法对 Q1 是奏效的。
3. 但后续步骤不能再沿用旧的季度验证逻辑。
4. 对 Q3 只能支撑年度状态转移，不支撑季度状态转移。

---

## 2. 当前正式链路

### 2.1 核心脚本

- `Q1/01b_Inject_TIF_to_CSV.py`
  负责把年度夜间灯光写入年度 CSV。

- `Q1/02_RVRI_Synthesis.py`
  当前正式 RVRI 合成入口。

- `Q1/02_RVRI_Synthesis_V5.py`
  兼容旧入口，内部已转发到新的年度版合成逻辑。

- `Q1/rvri_pipeline.py`
  年度 RVRI 的核心实现。

- `Q1/03_RVRI_Advanced_Validation.py`
  新的年度版后验验证脚本，不再依赖旧 notebook 的季度快照逻辑。

### 2.2 当前正式输出

- `Q1/output/Shaoguan_RVRI_Q1_Validated.csv`
  年度 RVRI 主结果表。

- `Q1/output/Q1_Data_Quality_Audit.json`
  年度灯光质量审计结果。

- `Q1/output/Q1_RVRI_Model_Metadata.json`
  PCA 特征、载荷和解释率。

- `Q1/output/Q1_Diagnostic_Full_Report.json`
  年度版综合诊断报告。

- `Q1/output/validation_report.json`
  关键指标摘要。

- `Q1/output/Q1_RVRI_Scientific_Check.png`
- `Q1/output/Q1_LISA_Map.png`
- `Q1/output/Q1_POI_Validation_Enhanced.png`
- `Q1/output/Q1_Step6_KDE_Coupling_Validation.png`

---

## 3. 当前方法是否奏效

结论：**奏效，但必须按“年度建模 + 建成区验证”来解释。**

### 3.1 为什么不能只看全样本

如果对全市全部格网直接看 `rvri-light` 相关性，结果并不好：

- 全样本 `corr_rvri_light = 0.0711`

这是因为韶关全域格网里存在大量山地、林地和低活跃区，零值夜光会严重稀释“房多灯暗”的住宅风险逻辑。

### 3.2 为什么方法仍然有效

把样本限制到建成区后，逻辑就恢复了：

- 建成区子样本（NDBI 前 25%）：
  - `corr_rvri_light = -0.3514`
  - `corr_rvri_mismatch = 0.5293`

- 核心建成区子样本（NDBI 前 10%）：
  - `corr_rvri_light = -0.6679`
  - `corr_rvri_mismatch = 0.7195`

因此，当前方法的有效性结论不是“在全市任意格网上都直接成立”，而是：

“在住宅/建成区相关样本上，RVRI 已经能够较好刻画建成强度高但夜间活力不足的风险结构。”

---

## 4. 年度版验证结果

当前最新年度诊断基于 `2023` 年快照完成。

### 4.1 方法有效性

- `works_for_q1 = true`

### 4.2 空间聚集性

- 全局 Moran's I：`0.7424`
- 置换检验 `p = 0.01`
- `HH` 高风险聚集格网数：`29122`

说明年度版 RVRI 具有显著的空间集聚性，能够支持后续空间分异和扩散分析。

### 4.3 POI 外部效度

在建成区且存在 POI 的格网中：

- Spearman(`rvri`, `poi_count`) = `-0.2316`
- Pearson(`rvri`, `log(1+poi_count)`) = `-0.2083`

说明商业/生活服务越活跃的区域，空置风险越低，方向是合理的。

### 4.4 耦合协调度

在建成区样本中：

- CCDM 均值：`0.1711`
- `corr_rvri_vs_ccdm = -0.2593`

说明建筑强度与夜间活力越不协调，RVRI 越高，方向符合研究设定。

---

## 5. 当前方法和旧版本的区别

旧版本的问题不是完全不能跑，而是后续验证和对外叙述还停留在季度口径：

1. 旧 `03_RVRI_Advanced_Validation.ipynb` 读取的是 `Shaoguan_RVRI_Long_Panel_Final.csv`
2. 旧逻辑默认选取 `2023Q4`
3. README 中曾写“已具备完整季度面板能力，直接赋能 Q3”

这些表述现在都不再适用。

当前新的正式口径是：

1. RVRI 是年度版。
2. 验证也是年度版。
3. Q2 可以直接使用。
4. Q3 只能使用年度状态序列。

---

## 6. 快速复现

### Step 1. 写入年度夜光

```bash
python Q1/01b_Inject_TIF_to_CSV.py
```

### Step 2. 生成年度 RVRI

```bash
python Q1/02_RVRI_Synthesis.py
```

### Step 3. 运行年度版验证

```bash
python Q1/03_RVRI_Advanced_Validation.py
```

---

## 7. 对 Q2 / Q3 的接口意义

### 对 Q2

当前 `2019-2023` 年度 RVRI 可以直接用于：

- 风险类型识别
- 老城衰退型 / 新区扩张型区分
- 空间聚集格局描述

### 对 Q3

当前不能再写“季度状态转移”。

现在能支撑的是：

- `2019-2023` 年度风险状态演化
- 年度空间扩散
- 年度状态转移概率

如果后续一定要做季度状态转移，必须重新拿到真正的季度夜间灯光数据。

---

## 8. Q3/output 图件说明

Q3 当前在 `Q3/output/` 下主要有 4 张 PNG 图。它们分别对应空间自相关、空间扩散机制和未来一年低转高预测，可以串起来理解为一条完整分析链。

### 8.1 `Q3_Moran_Trend.png`

这是年度全局空间自相关趋势图，展示 `2019-2023` 各年的 `Global Moran's I`。它由 `Q3/03_spatial_autocorr.py` 生成，对应结果表为 `Q3/output/annual_moran_report.csv`。

这张图主要回答“空置风险是否具有稳定的空间集聚”。当前五个年份的 Moran's I 分别为 `0.7227`、`0.7335`、`0.7413`、`0.7297`、`0.7401`，对应置换检验 `p = 0.005`。也就是说，Q3 不是只在某一年偶然出现集聚，而是在 `2019-2023` 连续五年都存在显著正向空间自相关。

阅读时重点看三点：整条线是否一直在 0 以上；年际波动是否剧烈；最新年份 `2023` 是否仍保持高位。当前图形的结论很明确：韶关住宅空置风险的空间集聚是长期稳定结构，不是短期噪声。

### 8.2 `Q3_LISA_Map.png`

这是 `2023` 年的局部空间自相关图，由 `Q3/03_spatial_autocorr.py` 生成，对应数据文件为 `Q3/output/q3_lisa_panel.csv`，最新年度图层为 `Q3/output/lisa_cluster_latest.geojson`。

图中 5 类含义如下：

- `HH`：高风险-高邻域，是高风险集聚核心区。
- `LL`：低风险-低邻域，是低风险稳定片区。
- `HL`：高风险-低邻域，是孤立的高风险异常点。
- `LH`：低风险-高邻域，是高风险片区边缘的过渡带，也是低转高的重要候选区域。
- `NS`：不显著，表示局部空间自相关不强。

`2023` 年的分类结果为：`HH = 13591`，`LL = 12358`，`HL = 44`，`LH = 27`，`NS = 53513`。这说明高风险和低风险都已经形成清晰片区，其中 `HH` 是后续治理和监测的重点，`LH` 则是扩散分析里最敏感的边缘地带。

### 8.3 `spatial_markov_comparison.png`

这是 Spatial Markov 升级概率对比图，由 `Q3/05_spatial_markov.py` 生成，对应结果文件为 `Q3/output/spatial_markov_matrix.csv` 和 `Q3/output/spatial_diffusion_summary.json`。

图中把邻域环境分为 `low / mid / high` 三档，并比较两类升级概率：

- `0->2`：低风险直接升到高风险。
- `1->2`：中风险升到高风险。

当前结果如下：

- `0->2` 概率：`low = 0.0067`，`mid = 0.0128`，`high = 0.0303`
- `1->2` 概率：`low = 0.0757`，`mid = 0.1241`，`high = 0.2101`

这张图要表达的核心不是某一个柱子高不高，而是从 `low` 到 `high` 的整体抬升趋势。它说明只要周边进入更高风险的邻域环境，本地格网升级为高风险的概率就会显著增加，因此 Q3 中存在明确的空间扩散机制。

### 8.4 `Q3_LowToHigh_Risk_Map.png`

这是 Q3 中唯一的未来预测图，由 `Q3/06_low_to_high_predict.py` 生成。对应表格为 `Q3/output/low_to_high_prob_next_year.csv`，空间图层为 `Q3/output/low_to_high_prob_next_year.geojson`，模型报告为 `Q3/output/q3_prediction_report.json`。

它表示的是：在 `2023` 年仍处于低风险状态的格网中，哪些最有可能在 `2024` 年发生 `0->2` 的跨级升级。也就是说，这是一张前瞻预测图，不是历史现状图。

当前模型回测结果为：`ROC-AUC = 0.7317`，`Lift@10% = 3.1086`，满足 Q3 设定的预测门槛。未来预测部分共对 `26420` 个格网打分，其中前 `10%` 的高概率格网共有 `2642` 个，阈值为 `0.0356`，整体平均预测概率为 `0.0157`。

阅读这张图时，要重点看高概率格网是否落在 `HH` 核心片区边缘、`LH` 过渡带或高风险邻域占比高的区域。如果这些空间位置和前面的 LISA、Spatial Markov 结论能够相互印证，就说明这张预测图不仅“算出来了”，而且“解释得通”。

### 8.5 四张图的关系

这四张图按逻辑顺序分别回答四个问题：

1. `Q3_Moran_Trend.png`：有没有稳定的全局空间集聚。
2. `Q3_LISA_Map.png`：集聚具体落在哪些片区。
3. `spatial_markov_comparison.png`：邻域高风险会不会推高升级概率。
4. `Q3_LowToHigh_Risk_Map.png`：未来一年哪些低风险格网最值得优先监测。
