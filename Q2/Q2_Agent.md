# Q2_Agent.md

## 1. 文档目的

本文件用于指导 **Q2：区分“老城衰退型空置”与“新区扩张型空置”** 的实现。

本问的核心不是重新构建 Q1 的住宅空置风险指数，而是：

1. 直接继承 Q1 已完成的年度格网风险面板；
2. 在“是否存在住宅空置风险”的基础上，进一步识别空置的形成机制；
3. 将高风险格网区分为 **老城衰退型空置**、**新区扩张型空置**，并保留 **稳定占用型** 与 **过渡混合型** 作为辅助类别。

换句话说，Q2 做的是 **“风险类型识别”**，不是 **“风险重建”**。

---

## 2. Q2 的研究目标

Q2 要回答的问题是：

> 在 2019-2023 年、500m 格网尺度上，哪些住宅空置风险格网更可能属于老城存量衰退导致的空置，哪些更可能属于新区建设扩张快于人口与功能导入导致的空置？

因此，Q2 的目标可以拆分为两层：

- **第一层：识别空置风险候选格网**
  - 判断一个格网是否属于值得进入“空置类型识别”的风险样本。
- **第二层：识别空置形成机制**
  - 对候选格网进一步区分为：
    - 老城衰退型空置
    - 新区扩张型空置
    - 过渡混合型空置

低风险、建成与活力匹配较好的格网，归为 **稳定占用型**，作为对照组。

---

## 3. Q1 已提供给 Q2 的基础

### 3.1 可直接使用的主底表

Q2 不需要重做 Q1，可直接使用：

- `Q1/output/Shaoguan_RVRI_Q1_Validated.csv`

这张表已经是 **2019-2023 年、500m 格网尺度的年度面板底表**。

### 3.2 主底表中优先调用的字段

Q2 首先从 `Shaoguan_RVRI_Q1_Validated.csv` 提取以下字段：

- `grid_id`
- `district_name`
- `source_year`
- `rvri`
- `risk_state`
- `stock_pressure`
- `mismatch_gap`
- `ndbi`
- `light`
- `ndvi`

可选保留：

- `rvri_raw`

### 3.3 Q1 已经提供的核心信息

Q1 已经为 Q2 提供了三类最重要的分型基础：

1. **风险强度基础**
   - `rvri`
   - `risk_state`

2. **空置机制基础**
   - `stock_pressure`
   - `mismatch_gap`
   - `light`
   - `ndbi`
   - `ndvi`

3. **空间底图基础**
   - `scientific_grid_500m.geojson`
   - `shaoguan_districts_official.json`
   - `pois_cache.geojson`

因此，Q2 的重点不是重新构造指数，而是 **把 Q1 的风险面板转化为空置类型面板**。

---

## 4. Q2 的总体框架

Q2 推荐采用 **“两阶段四分类”** 框架。

### 4.1 两阶段

#### 阶段 A：识别“空置风险候选格网”

先从全部格网中筛出：

- 已开发或已建成的格网；
- 且具备一定住宅空置风险的格网。

#### 阶段 B：识别“空置形成机制”

仅在候选格网中，区分其更接近：

- 老城衰退型空置
- 新区扩张型空置
- 过渡混合型空置

### 4.2 四分类

Q2 的推荐输出类别如下：

| 类别代码 | 类别名称 | 含义 |
|---|---|---|
| 0 | 稳定占用型 | 有建成、有活力、空置风险低，作为对照组 |
| 1 | 老城衰退型空置 | 老城区存量较大，但活力下降、功能外流，形成存量空心化 |
| 2 | 新区扩张型空置 | 新区或外围片区建设扩张较快，但入住与活力导入滞后 |
| 3 | 过渡混合型 | 同时具有部分老城与新区特征，或处于更新/扩张交界地带 |

> 说明：如果比赛最终只要求报告两类空置，则 1、2 为主结果，0、3 作为辅助类别或边界样本处理。

---

## 5. Q2 的指标体系

Q2 的指标体系分为三组：

1. **风险强度变量**：判断“风险强不强”
2. **时序机制变量**：判断“是存量衰退还是增量扩张”
3. **空间区位变量**：判断“更像老城还是更像新区”

### 5.1 风险强度变量

这些变量主要用于判断一个格网是否值得进入 Q2 类型识别。

| 变量 | 含义 | 用途 |
|---|---|---|
| `rvri` | 住宅空置风险复合指数 | 判断综合风险强度 |
| `risk_state` | 年度风险状态标签 | 快速分层高/中/低风险 |
| `mismatch_gap` | 建成强但活力弱的错配程度 | 判断“建了但没活起来” |
| `stock_pressure` | 建成存量或开发压力 | 判断建成盘子和开发强度 |

### 5.2 机制辅助变量

这些变量主要用于区分空置是“老城衰退”还是“新区扩张”。

| 变量 | 含义 | 用途 |
|---|---|---|
| `light` | 夜间活力/使用强度代理 | 识别入住和活动是否不足 |
| `ndbi` | 建成强度代理 | 识别开发扩张是否明显 |
| `ndvi` | 生态/低开发背景代理 | 排除未开发或绿地格网 |

### 5.3 空间区位变量（需在 Q2 新增）

这些变量不在 `Validated.csv` 中直接给出，需要在 Q2 中补充。

| 变量 | 来源 | 作用 |
|---|---|---|
| `dist_to_local_core` | 格网 geometry + 本地老城核心 | 判断格网距传统中心的远近 |
| `poi_density` | `pois_cache.geojson` | 判断功能活跃度与中心性 |
| `core_fringe_flag` | 本地核心分区结果 | 判断属于核心区、过渡区还是外围扩张区 |

---

## 6. Q2 的特征工程设计

Q2 不应只看单年状态，而应使用 **“2023 当前状态 + 2019-2023 变化趋势 + 空间区位背景”** 的组合特征。

### 6.1 当前状态特征（建议以 2023 年为主判别年）

以 2023 年为最终分类参照年，提取：

- `rvri_2023`
- `risk_state_2023`
- `stock_2023`
- `mismatch_2023`
- `light_2023`
- `ndbi_2023`
- `ndvi_2023`

### 6.2 时序特征（2019-2023）

对每个 `grid_id`，基于 2019-2023 的年序列构造：

- `rvri_mean`
- `rvri_slope`
- `risk_high_freq`：高风险年份数 / 5
- `stock_mean`
- `stock_slope`
- `mismatch_mean`
- `mismatch_slope`
- `light_mean`
- `light_slope`
- `ndbi_slope`

### 6.3 机制派生特征

建议额外构造以下机制变量：

- `build_lag = stock_slope - light_slope`
  - 含义：建设增长是否快于活力增长
  - 典型指向：新区扩张型空置

- `persist_gap = mismatch_mean * risk_high_freq`
  - 含义：建成-活力错配是否长期持续
  - 典型指向：老城衰退型空置

### 6.4 空间区位特征

建议为每个格网补充：

- `district_name`
- `dist_to_local_core`
- `poi_density`
- `core_fringe_flag`

> 注意：不要简单使用“距全市单一中心点距离”替代本地核心距离。对县城或区级建成区，应优先按 `district_name` 或本地建成片区分别识别老城核心。

---

## 7. Q2 的分类逻辑

### 7.1 第一步：建成区筛选

Q2 讨论的是住宅空置，不是山地、绿地或未开发地。

因此，首先要做 **建成区筛选**：

- 保留：`ndbi` 不低、`stock_pressure` 不低的格网
- 剔除：`ndvi` 高且 `ndbi` 低的生态/低开发格网

这一层的目的是避免把“本来就没开发”的区域误判为空置。

### 7.2 第二步：识别空置风险候选格网

在建成区基础上，识别哪些格网属于空置风险候选。

建议使用以下信息：

- `rvri_2023`
- `risk_state_2023`
- `risk_high_freq`
- `mismatch_mean`

推荐逻辑：

- `risk_state_2023 = low` 且长期风险不显著：归入 **稳定占用型**
- `risk_state_2023 = medium/high`，或 `risk_high_freq` 较高：进入候选样本

### 7.3 第三步：在候选样本中区分“老城衰退”与“新区扩张”

推荐使用 **双得分判别法**，分别构造：

- `OldDeclineScore`（老城衰退得分）
- `NewExpansionScore`（新区扩张得分）

#### 老城衰退得分的构成建议

老城衰退型应满足：

- 风险高
- 存量大
- 错配持续
- 扩张不强或趋稳
- 活力下降
- 更接近老城核心

建议主要调用：

- `rvri_2023`
- `stock_mean`
- `mismatch_mean`
- `persist_gap`
- `risk_high_freq`
- `-stock_slope`
- `-light_slope`
- `-dist_to_local_core`
- `poi_density`（作为传统中心活跃背景的辅助判断）

#### 新区扩张得分的构成建议

新区扩张型应满足：

- 风险存在
- 开发扩张明显
- 建设速度高于活力导入速度
- 错配正在形成或加深
- 更接近外围扩张带

建议主要调用：

- `rvri_2023`
- `stock_slope`
- `ndbi_slope`
- `build_lag`
- `mismatch_mean` 或 `mismatch_slope`
- `dist_to_local_core`
- `core_fringe_flag`
- `poi_density`（外围区通常低于传统中心）

### 7.4 第四步：最终分类规则

建议按以下逻辑输出最终类别：

- 非候选样本：`q2_type = 0`（稳定占用型）
- 候选样本中：
  - 若 `OldDeclineScore` 显著高于 `NewExpansionScore`：`q2_type = 1`
  - 若 `NewExpansionScore` 显著高于 `OldDeclineScore`：`q2_type = 2`
  - 若两者接近：`q2_type = 3`

> 推荐先采用规则型或标准化加权得分法，不急于一开始就上复杂模型。Q2 的关键是类型解释清晰、机制链条完整、地图结果可信。

---

## 8. 四类样本的定义标准

### 8.1 稳定占用型（q2_type = 0）

**定义：**
有建成、有活力、建成与活力匹配较好，住宅空置风险低。

**主要识别特征：**

- `rvri` 低
- `risk_state` 低风险为主
- `mismatch_gap` 低
- `light` 与 `stock_pressure` 较匹配

**角色：**

- 作为对照组
- 用于与两类空置格网作结构差异分析

### 8.2 老城衰退型空置（q2_type = 1）

**定义：**
位于老城核心或传统中心附近，既有建成存量较大，但人口、居住与商业活力减弱，形成持续性的存量空心化。

**主要识别特征：**

- `rvri_2023` 高或持续偏高
- `stock_mean` 高
- `stock_slope` 低或为负
- `mismatch_mean` 高
- `light_slope` 低或为负
- `dist_to_local_core` 小
- `poi_density` 具有传统中心背景

**核心机制：**

> 建得早、存量大、位置在核心附近，但活力掉下去了。

### 8.3 新区扩张型空置（q2_type = 2）

**定义：**
位于新区或外围扩张带，建设推进较快，但人口导入、入住水平和功能活力未同步跟进，形成增量型空置。

**主要识别特征：**

- `rvri_2023` 中高或高
- `stock_slope` 高
- `ndbi_slope` 高
- `build_lag` 高
- `mismatch_slope` 为正或 `mismatch_mean` 高
- `dist_to_local_core` 大
- `core_fringe_flag` 指向外围或新区

**核心机制：**

> 建得快、扩得猛、位置在外围，但人和活力还没跟上。

### 8.4 过渡混合型（q2_type = 3）

**定义：**
处于老城更新区、新旧交界区或外围成熟片区等边界地带，同时呈现部分老城特征与部分新区特征，无法稳定归入单一类型。

**主要识别特征：**

- `OldDeclineScore` 与 `NewExpansionScore` 接近
- 可能位于核心-边缘过渡区
- 风险存在，但形成机制不单一

**角色：**

- 作为边界样本与缓冲层
- 避免为了二分类而硬性误判

---

## 9. 本地老城核心的识别原则

Q2 需要补充“老城/新区背景”标签，但 Q1 不能直接提供该标签，因此需要在 Q2 中自行构建。

### 9.1 优先方案

若存在明确规划边界、官方老城/新区范围、历史建成区边界，则优先采用官方边界。

### 9.2 备选方案

若无官方边界，则按本地建成格局识别“老城核心”：

1. 按 `district_name` 分组，避免全市只设一个中心；
2. 在每个区县或主要建成片区内部，优先识别 2019 年：
   - `light` 高
   - `ndbi` 高
   - `poi_density` 高
3. 将满足条件的格网聚成连片区域；
4. 选择其中最稳定、最集中的区域定义为 `local_core`；
5. 对所有格网计算 `dist_to_local_core`；
6. 进一步划分 `core_fringe_flag`：核心区 / 过渡区 / 外围扩张区。

---

## 10. 推荐的实现方法

Q2 的主方法建议采用：

### 10.1 主方法：规则型双得分判别

推荐原因：

- 可解释性强；
- 便于写清楚“为何是老城衰退型 / 为何是新区扩张型”；
- 便于在比赛答辩中展示机制链条；
- 对样本量、噪声和边界样本更稳健。

典型做法：

1. 对关键特征标准化；
2. 构造 `OldDeclineScore`；
3. 构造 `NewExpansionScore`；
4. 基于得分差异进行分类；
5. 将低风险样本直接归入稳定占用型；
6. 将得分接近样本归入过渡混合型。

### 10.2 辅助方法：聚类稳健性检验

可作为附加分析或稳健性验证：

- `KMeans`
- `Gaussian Mixture Model`
- 层次聚类

聚类不作为主标签生成方式，而作为检验：

- 规则型标签与数据驱动聚类是否大体一致；
- 老城衰退型与新区扩张型在特征空间中是否可分；
- 过渡混合型是否天然落在边界区。

### 10.3 空间结果验证

建议增加以下验证：

- 地图上是否形成连续片区，而非随机散点；
- 老城衰退型是否更集中在传统中心附近；
- 新区扩张型是否更集中于外围扩张廊道；
- 各区县类型占比是否符合实际城市发展逻辑。

---

## 11. 推荐的程序拆分

以下程序命名仅为建议，目的是让 Q2 的实现结构清楚、职责分明、便于在 Codex 中逐个完成。

---

### 01_build_q2_basepanel.py

**功能：**

构建 Q2 的基础年度面板，不重做 Q1，只做字段提取、格式统一与质量检查。

**输入数据：**

- `Q1/output/Shaoguan_RVRI_Q1_Validated.csv`

**调用变量：**

- `grid_id`
- `district_name`
- `source_year`
- `rvri`
- `risk_state`
- `stock_pressure`
- `mismatch_gap`
- `ndbi`
- `light`
- `ndvi`
- 可选：`rvri_raw`

**使用方法：**

- 读取年度格网面板；
- 保留 Q2 所需字段；
- 检查 `grid_id-source_year` 唯一性；
- 检查 2019-2023 是否完整；
- 检查缺失值、异常值、重复记录；
- 输出 Q2 可直接调用的基础表。

**输出结果：**

- `Q2/output/Q2_BasePanel_2019_2023.csv`

---

### 02_enrich_spatial_context.py

**功能：**

为格网补充空间位置、区位和功能活跃背景，并识别本地老城核心。

**输入数据：**

- `Q2/output/Q2_BasePanel_2019_2023.csv`
- `Q1/data/scientific_grid_500m.geojson`
- `Q1/data/shaoguan_districts_official.json`
- `Q1/data/pois_cache.geojson`

**调用变量：**

- `grid_id`
- `district_name`
- geometry
- POI 点位或 POI 密度
- 2019 年 `light`
- 2019 年 `ndbi`

**使用方法：**

- 空间连接格网 geometry；
- 核对行政区归属；
- 统计每个格网的 `poi_density`；
- 按 `district_name` 或本地建成片区识别 `local_core`；
- 计算每个格网 `dist_to_local_core`；
- 生成 `core_fringe_flag`（核心区 / 过渡区 / 外围区）。

**输出结果：**

- `Q2/output/Q2_BasePanel_Spatial_2019_2023.csv`
- `Q2/output/Q2_BasePanel_Spatial_2019_2023.geojson`

---

### 03_engineer_temporal_features.py

**功能：**

将年度面板转为格网级特征表，构造 2019-2023 的趋势变量与机制变量。

**输入数据：**

- `Q2/output/Q2_BasePanel_Spatial.csv`

**调用变量：**

- `rvri`
- `risk_state`
- `stock_pressure`
- `mismatch_gap`
- `light`
- `ndbi`
- `ndvi`
- `dist_to_local_core`
- `poi_density`
- `core_fringe_flag`

**使用方法：**

按 `grid_id` 聚合，构造：

- 当前状态变量：
  - `rvri_2023`
  - `risk_state_2023`
  - `stock_2023`
  - `mismatch_2023`
  - `light_2023`
  - `ndbi_2023`
  - `ndvi_2023`
- 趋势变量：
  - `rvri_mean`
  - `rvri_slope`
  - `risk_high_freq`
  - `stock_mean`
  - `stock_slope`
  - `mismatch_mean`
  - `mismatch_slope`
  - `light_mean`
  - `light_slope`
  - `ndbi_slope`
- 派生变量：
  - `build_lag`
  - `persist_gap`

趋势计算方法建议：

- 以年份为自变量的线性回归斜率；
- 或使用首末年差值作为简化备选；
- 规则固定后，全流程保持一致。

**输出结果：**

- `Q2/output/Q2_Grid_Features_2019_2023.csv`

---

### 04_screen_builtup_and_candidates.py

**功能：**

筛除非建成区，并识别进入 Q2 类型判别的空置风险候选格网。

**输入数据：**

- `Q2/output/Q2_Grid_FeatureTable.csv`

**调用变量：**

- `ndbi_2023`
- `ndvi_2023`
- `stock_2023`
- `rvri_2023`
- `risk_state_2023`
- `risk_high_freq`
- `mismatch_mean`

**使用方法：**

1. 建成区筛选：
   - 使用 `ndbi_2023`、`stock_2023` 与 `ndvi_2023` 过滤未开发/生态格网；
2. 候选样本识别：
   - 使用 `rvri_2023`、`risk_state_2023`、`risk_high_freq`、`mismatch_mean` 判定是否进入空置类型识别；
3. 对非候选样本先标记为 `stable_candidate` 或 `non_built_filtered`。

**输出结果：**

- `Q2/output/Q2_CandidateTable.csv`

---

### 05_classify_vacancy_types.py

**功能：**

基于双得分机制，对候选格网进行“老城衰退型 / 新区扩张型 / 过渡混合型”分类。

**输入数据：**

- `Q2/output/Q2_CandidateTable.csv`

**调用变量：**

- `rvri_2023`
- `stock_mean`
- `stock_slope`
- `mismatch_mean`
- `mismatch_slope`
- `light_slope`
- `ndbi_slope`
- `risk_high_freq`
- `build_lag`
- `persist_gap`
- `dist_to_local_core`
- `poi_density`
- `core_fringe_flag`

**使用方法：**

- 对分类变量标准化；
- 构建：
  - `OldDeclineScore`
  - `NewExpansionScore`
- 根据得分差进行类型赋值：
  - `q2_type = 1`：老城衰退型空置
  - `q2_type = 2`：新区扩张型空置
  - `q2_type = 3`：过渡混合型
- 将前一步非候选样本写回：
  - `q2_type = 0`：稳定占用型

**推荐方法：**

- 规则型双得分判别法（主方法）
- 权重可先采用等权或依据机制重要性设定，再做敏感性分析

**输出结果：**

- `Q2/output/Q2_Classified_GridTable.csv`
- `Q2/output/Q2_Classified_GridMap.geojson`

---

### 06_validate_q2_typology.py

**功能：**

对 Q2 分类结果做结构验证、空间验证与稳健性检验。

**输入数据：**

- `Q2/output/Q2_Classified_GridTable.csv`
- `Q2/output/Q2_Classified_GridMap.geojson`

**调用变量：**

- `q2_type`
- `rvri_2023`
- `stock_mean`
- `stock_slope`
- `mismatch_mean`
- `light_slope`
- `ndbi_slope`
- `dist_to_local_core`
- `poi_density`
- `district_name`

**使用方法：**

- 比较四类样本在核心变量上的均值、中位数、分布差异；
- 检查分类结果是否具有合理空间集聚；
- 统计不同区县的类型占比；
- 用聚类方法做辅助稳健性检验：
  - `KMeans` / `GMM` / 层次聚类
- 检查规则型分类与聚类结果的一致性。

**输出结果：**

- `Q2/output/Q2_Validation_Report.json`
- `Q2/output/Q2_Type_Profile.csv`
- `Q2/output/Q2_District_Summary.csv`

---

### 07_export_q2_deliverables.py

**功能：**

整理 Q2 最终成果，用于论文写作、图表输出和答辩展示。

**输入数据：**

- `Q2/output/Q2_Classified_GridTable.csv`
- `Q2/output/Q2_Classified_GridMap.geojson`
- `Q2/output/Q2_Validation_Report.json`
- `Q2/output/Q2_Type_Profile.csv`
- `Q2/output/Q2_District_Summary.csv`

**调用变量：**

- `q2_type`
- 各类核心特征均值/中位数
- 区县类型占比
- 空间分布结果

**使用方法：**

- 输出用于论文正文的总表；
- 输出四类样本画像表；
- 输出区县对比表；
- 输出类型空间分布图；
- 输出方法流程图、分类逻辑图、变量解释表。

**输出结果：**

- `Q2/output/final/Q2_Main_Result_Table.csv`
- `Q2/output/final/Q2_Type_Map.geojson`
- `Q2/output/final/Q2_Method_Summary.md`

---

## 12. 推荐的程序执行顺序

推荐严格按以下顺序实现：

1. `01_build_q2_basepanel.py`
2. `02_enrich_spatial_context.py`
3. `03_engineer_temporal_features.py`
4. `04_screen_builtup_and_candidates.py`
5. `05_classify_vacancy_types.py`
6. `06_validate_q2_typology.py`
7. `07_export_q2_deliverables.py`

不建议跳步实现，因为 Q2 的核心在于：

- 先有可靠的年度面板；
- 再补空间背景；
- 再做趋势特征；
- 最后做机制分类与验证。

---

## 13. Q2 的核心结论表达模板

Q2 在正文中建议表述为：

> 本问在 Q1 已构建的住宅空置风险复合指数基础上，不再重复计算风险水平，而是通过建成存量压力、建成-活力错配、夜间活力、建成强度、时序扩张趋势与空间区位特征，对高风险格网进一步进行类型识别。最终将格网划分为稳定占用型、老城衰退型空置、新区扩张型空置和过渡混合型四类，其中“老城衰退型空置”和“新区扩张型空置”是本问的核心识别对象。

---

## 14. 实现时必须坚持的原则

1. **不重做 Q1**
   - Q2 直接继承 `Shaoguan_RVRI_Q1_Validated.csv`。

2. **不只看单年**
   - 必须使用 2019-2023 的趋势信息，避免把短期波动误判为类型差异。

3. **不只看指数**
   - `rvri` 只负责告诉我们“风险高不高”；
   - 类型识别必须加入 `stock_pressure`、`mismatch_gap`、`light`、`ndbi` 和空间区位变量。

4. **不只做二分类**
   - 应保留“稳定占用型”和“过渡混合型”，这样结果更稳、解释更完整。

5. **区位识别优先本地核心**
   - 不使用全市单中心粗糙替代各区县本地老城核心。

6. **主方法优先可解释性**
   - 先用规则型双得分法建立清晰逻辑，再用聚类等方法做稳健性验证。

---

## 15. 本问最简实现摘要

如果只保留最核心的执行思路，Q2 可以压缩为以下四步：

1. 从 `Shaoguan_RVRI_Q1_Validated.csv` 提取：
   - `grid_id`
   - `source_year`
   - `district_name`
   - `rvri`
   - `risk_state`
   - `stock_pressure`
   - `mismatch_gap`
   - `ndbi`
   - `light`
   - `ndvi`

2. 计算：
   - `risk_high_freq`
   - `stock_slope`
   - `light_slope`
   - `mismatch_slope`
   - `ndbi_slope`
   - `build_lag`
   - `dist_to_local_core`
   - `poi_density`

3. 筛选：
   - 先识别建成区；
   - 再识别空置风险候选格网。

4. 分类：
   - 近核心、存量大、扩张弱、活力下降 → 老城衰退型空置；
   - 位置偏外围、扩张快、建设快于活力导入 → 新区扩张型空置；
   - 两者接近 → 过渡混合型；
   - 非候选 → 稳定占用型。

---

## 16. 最终交付建议

Q2 最终建议至少形成以下成果：

1. **一个格网级 Q2 分类结果表**
2. **一个带类型字段的 GeoJSON 地图文件**
3. **一个四类样本画像表**
4. **一个区县维度类型占比汇总表**
5. **一个 Q2 方法与验证说明文件**

其中最重要的主成果是：

- `Q2_Classified_GridTable.csv`
- `Q2_Classified_GridMap.geojson`
- `Q2_Validation_Report.json`

---

## 17. 一句话总结

Q2 的本质是：

> 在 Q1 已完成的住宅空置风险识别基础上，利用 `rvri + stock_pressure + mismatch_gap` 为主轴，结合 `light、ndbi、ndvi` 的时序变化与本地核心区位背景，把“高风险格网”进一步识别为“老城衰退型空置”与“新区扩张型空置”，并用“稳定占用型”和“过渡混合型”作为辅助边界类别，使结果既有机制解释力，也有空间可信度。

---

## 18. 当前 Q2 是否已经完成

在当前数据条件下，Q2 已经完成主体实现，可以视为第二问的正式完成版本。

这里“已经完成”的含义是：

1. 已完成从 Q1 年度风险面板到底层 Q2 类型识别面板的全流程构建；
2. 已完成建成区筛选、候选格网识别、类型判别、统计验证与成果导出；
3. 已生成可直接用于论文写作、制图和汇报答辩的主成果文件；
4. 已形成“稳定占用型 / 老城衰退型空置 / 新区扩张型空置 / 过渡混合型”四类结果。

需要说明的是：

当前 Q2 的“本地老城核心”识别，采用的是第 9 节中的**备选方案**，而不是第 9.1 节中“官方老城 / 新区规划边界优先”的方案。原因不是程序未实现，而是当前数据中并未提供专门的“老城范围 / 新区范围 / 历史建成区”官方边界图层。

因此，当前 Q2 的完成口径应表述为：

“在现有数据条件下，Q2 已经完成基于年度风险面板、时序机制特征与本地核心区位识别的四分类实现，并形成了可复现的正式交付成果。”

---

## 19. 官方边界文件应如何准确表述

当前 Q1/Q2 中可调用的官方边界文件是：

- `Q1/data/shaoguan_districts_official.json`

它的准确含义是：

- **韶关市各区县行政区边界**

而不是：

- 官方老城区边界
- 官方新区边界
- 历史建成区边界
- 城市更新单元边界

因此，在论文和答辩中应准确写成：

“本文使用 `shaoguan_districts_official.json` 作为区县行政边界约束，用于校核格网行政归属，并在各区县内部识别本地核心区；由于缺乏专门的老城 / 新区官方规划边界，本文进一步采用 2019 年夜间灯光、建成强度和 POI 密度的综合指数，在区县内部识别本地老城核心，并据此计算格网到本地核心区的距离及圈层位置。”

这意味着当前 Q2 的区位构建逻辑是：

1. 行政边界层面：使用官方区县边界；
2. 老城 / 新区机制层面：使用区县内部的本地核心识别结果；
3. 因此，Q2 的“老城衰退型 / 新区扩张型”并不是基于人工主观圈定，而是基于区县内部相对中心性与扩张性特征判别得到。

---

## 20. 当前 Q2 实际实现方法

当前 Q2 实际采用的是“**两阶段四分类 + 规则型双得分判别 + 空间区位补充 + 聚类稳健性验证**”的方法框架。

### 20.1 阶段一：建成区与候选格网筛选

先基于以下变量识别建成区与空置风险候选格网：

- `ndbi_2023`
- `stock_2023`
- `ndvi_2023`
- `rvri_2023`
- `risk_state_2023`
- `risk_high_freq`
- `mismatch_mean`

这一阶段的目的是：

1. 剔除生态 / 低开发背景格网；
2. 保留已建成且存在一定空置风险的候选格网；
3. 对非候选样本预先标记为稳定占用型或非建成过滤样本。

### 20.2 阶段二：类型判别

在候选格网中，构造：

- `OldDeclineScore`
- `NewExpansionScore`

再据此将格网划分为：

- `q2_type = 0`：稳定占用型
- `q2_type = 1`：老城衰退型空置
- `q2_type = 2`：新区扩张型空置
- `q2_type = 3`：过渡混合型

其中最重要的判别特征包括：

- `rvri_2023`
- `stock_mean`
- `stock_slope`
- `mismatch_mean`
- `mismatch_slope`
- `light_slope`
- `ndbi_slope`
- `build_lag`
- `persist_gap`
- `dist_to_local_core`
- `poi_density`
- `core_fringe_flag`

### 20.3 本地核心识别方法

当前本地核心识别采用的是：

1. 锚定 `2019` 年作为基期；
2. 按 `district_name` 分组，避免全市单中心；
3. 在每个区县内部，对以下变量做综合评分：
   - `light`
   - `ndbi`
   - `poi_density`
4. 提取各区县内部综合评分前 `5%` 左右的格网作为本地核心；
5. 计算每个格网到本地核心的距离，生成：
   - `dist_to_local_core`
   - `core_fringe_flag`

这一步使 Q2 从“纯特征分类”提升为“带区位解释的机制分类”。

### 20.4 稳健性验证方法

在类型验证阶段，当前已经增加：

- `KMeans`
- `Gaussian Mixture Model`

作为辅助稳健性检验，用于检查规则型标签与数据驱动聚类之间是否具有大体一致的结构关系。

---

## 21. 当前最重要的输出文件

如果后续接手者没有看过代码，只需要先理解下面这 5 个核心文件即可。它们已经足够支撑 Q2 的论文写作、制图和答辩展示。

### 21.1 `Q2_Grid_Typology_Master.csv`

文件路径：

- `Q2/output/Q2_Grid_Typology_Master.csv`

它是什么：

- Q2 的**最终格网级主结果表**
- 每个 `grid_id` 一行
- 是后续所有定量分析的主底表

它是谁生成的：

- 由 `07_export_q2_deliverables.py` 汇总导出
- 上游实际来自：
  - `04_screen_builtup_and_candidates.py`
  - `05_classify_vacancy_types.py`
  - `06_validate_q2_typology.py`

它里面最重要的内容：

- 格网最终类型 `q2_type / q2_label`
- 候选样本标识
- 当前状态特征
- 时序特征
- 机制派生特征
- 空间区位特征

论文里主要拿它做什么：

1. 统计四类样本数量与占比；
2. 比较四类样本在 `rvri_2023`、`stock_mean`、`stock_slope`、`mismatch_mean` 等变量上的差异；
3. 生成正文、附录和补充表中的定量分析结果。

不建议怎么用：

- 不要把它当作“原始遥感数据表”；
- 不要再拿它去重做 Q1 的风险指数。

### 21.2 `Q2_Grid_Typology_Master.geojson`

文件路径：

- `Q2/output/Q2_Grid_Typology_Master.geojson`

它是什么：

- Q2 的**最终空间结果图层**
- 以格网 geometry 为载体，附带最终类型字段

它是谁生成的：

- 由 `05_classify_vacancy_types.py` 先生成分类图层；
- 再由 `07_export_q2_deliverables.py` 汇总导出为最终主地图文件。

论文里主要拿它做什么：

1. 绘制 Q2 四类样本空间分布图；
2. 绘制老城衰退型与新区扩张型对比图；
3. 做答辩中的主地图展示。

对接手者最重要的提醒：

- 如果要出图，优先用这个文件，而不是回头再从中间表重新拼 geometry；
- 这是 Q2 最终空间表达的标准入口。

### 21.3 `Q2_Typology_Summary_Overall.csv`

文件路径：

- `Q2/output/Q2_Typology_Summary_Overall.csv`

它是什么：

- Q2 的**总体结果汇总表**
- 按类型汇总样本量、占比及主要特征均值

它是谁生成的：

- 由 `06_validate_q2_typology.py` 生成类型画像；
- 再由 `07_export_q2_deliverables.py` 提炼出总体汇总表。

论文里主要拿它做什么：

1. 写总体类型占比；
2. 概括四类样本的平均特征差异；
3. 作为论文正文中“总体结果表”的直接来源。

### 21.4 `Q2_Typology_Summary_By_District.csv`

文件路径：

- `Q2/output/Q2_Typology_Summary_By_District.csv`

它是什么：

- Q2 的**区县维度类型汇总表**
- 反映各区县四类样本的数量与占比

它是谁生成的：

- 由 `06_validate_q2_typology.py` 先生成 `Q2_District_Summary.csv`；
- 再由 `07_export_q2_deliverables.py` 输出为最终区县汇总结果。

论文里主要拿它做什么：

1. 写区县之间的类型分异；
2. 比较不同区县中老城衰退型与新区扩张型的占比差异；
3. 支撑“空间异质性”或“区域分异”部分的文字和表格。

### 21.5 `Q2_Validation_Report.json`

文件路径：

- `Q2/output/Q2_Validation_Report.json`

它是什么：

- Q2 的**方法与验证说明文件**
- 用 JSON 记录当前分类结果的样本数、稳健性检验、空间验证与警告信息

它是谁生成的：

- 由 `06_validate_q2_typology.py` 直接生成

它里面最重要的内容：

1. 各类型样本量；
2. 候选格网数量；
3. 空间结果文件是否存在；
4. 聚类稳健性检验结果；
5. 当前实现中的 warning 信息。

论文里主要拿它做什么：

1. 写“方法有效性与稳健性检验”；
2. 写“辅助聚类与规则型分类的一致性”；
3. 写“当前实现边界与局限性说明”。

---

## 22. 程序与文件的对应关系

为了让没看过代码的人也能快速接手，Q2 的程序和产物关系可概括为：

1. `01_build_q2_basepanel.py`
   - 作用：从 Q1 年度风险表提取 Q2 所需字段，形成基础面板
   - 关键产物：`Q2_BasePanel_2019_2023.csv`

2. `02_enrich_spatial_context.py`
   - 作用：补充 geometry、POI 密度、区县核对、本地核心距离与圈层位置
   - 关键产物：`Q2_BasePanel_Spatial_2019_2023.csv / geojson`

3. `03_engineer_temporal_features.py`
   - 作用：将年度面板压缩为格网级特征表，构造当前状态、时序斜率和机制变量
   - 关键产物：`Q2_Grid_Features_2019_2023.csv`

4. `04_screen_builtup_and_candidates.py`
   - 作用：筛除非建成区，并识别进入类型判别的候选格网
   - 关键产物：`Q2_CandidateTable.csv`

5. `05_classify_vacancy_types.py`
   - 作用：通过规则型双得分法完成四分类
   - 关键产物：`Q2_Classified_GridTable.csv`、`Q2_Classified_GridMap.geojson`

6. `06_validate_q2_typology.py`
   - 作用：做类型画像、区县汇总、空间验证和聚类稳健性检验
   - 关键产物：`Q2_Validation_Report.json`、`Q2_Type_Profile.csv`、`Q2_District_Summary.csv`

7. `07_export_q2_deliverables.py`
   - 作用：汇总最终主表、主图和论文/答辩所需的直接交付文件
   - 关键产物：
     - `Q2_Grid_Typology_Master.csv`
     - `Q2_Grid_Typology_Master.geojson`
     - `Q2_Typology_Summary_Overall.csv`
     - `Q2_Typology_Summary_By_District.csv`

---

## 23. 论文写作时最应引用的文件

如果后续开始写论文，最建议优先引用的文件是：

1. `Q2/output/Q2_Grid_Typology_Master.csv`
   - 用途：正文定量分析、后续图表和附录统计基础

2. `Q2/output/Q2_Grid_Typology_Master.geojson`
   - 用途：绘制类型分布图、空间格局图、答辩展示图

3. `Q2/output/Q2_Typology_Summary_Overall.csv`
   - 用途：写总体结果，概括四类占比与结构差异

4. `Q2/output/Q2_Typology_Summary_By_District.csv`
   - 用途：写区县分异、老城衰退型与新区扩张型的空间异质性

5. `Q2/output/Q2_Validation_Report.json`
   - 用途：写“方法有效性”“稳健性检验”“空间可信度”部分

如果只保留一句话来指导后续写作，应写成：

“Q2 的主分析以 `Q2_Grid_Typology_Master.csv` 为核心底表，以 `Q2_Grid_Typology_Master.geojson` 为核心空间成果，以 `Q2_Typology_Summary_Overall.csv` 和 `Q2_Typology_Summary_By_District.csv` 为主要结果汇总表，以 `Q2_Validation_Report.json` 为方法与稳健性说明文件。”

---

## 24. 当前 Q2 已实现的目标应如何表述

当前 Q2 已经实现的目标可以在论文中表述为：

“在 Q1 已完成住宅空置风险识别的基础上，本文进一步构建了格网级空置类型识别框架。通过建成区筛选、空置风险候选识别、本地核心区位刻画、时序机制特征构造及规则型双得分分类，最终将 2019-2023 年韶关市 500m 格网划分为稳定占用型、老城衰退型空置、新区扩张型空置和过渡混合型四类，并利用聚类辅助检验验证了分类结构的稳健性。”

如果需要更偏比赛论文风格的压缩表达，可写成：

“Q2 已完成从风险识别到风险类型判别的完整扩展，实现了‘是否存在空置风险’向‘空置形成机制为何’的进一步推进。”

---

## 25. 当前 Q2 结果摘要

截至当前正式版本，Q2 总体分类结果为：

- 稳定占用型：`29632`
- 老城衰退型空置：`16427`
- 新区扩张型空置：`18775`
- 过渡混合型：`14519`

该结果说明：

1. 稳定占用型仍为样本中占比最高的类型，是后续所有差异分析的对照组；
2. 新区扩张型空置数量略高于老城衰退型空置，说明外围建设扩张快于活力导入的问题在当前格局中更为突出；
3. 老城衰退型空置仍占相当比例，说明传统中心附近的存量空心化问题同样不可忽视；
4. 过渡混合型占比不低，表明韶关市内部存在一定数量的新旧交界区和机制复合区，不宜将所有高风险格网简单二分。

这组结果可直接作为 Q2 结果分析部分的首段定量概括。

---

## 26. 给后续论文写作者的直接提示

如果后续接手者没有看过程序，只需要记住下面这组关系：

1. 要做正文定量分析：
   - 优先读 `Q2_Grid_Typology_Master.csv`

2. 要做空间图：
   - 优先读 `Q2_Grid_Typology_Master.geojson`

3. 要写总体结果：
   - 优先读 `Q2_Typology_Summary_Overall.csv`

4. 要写区县差异：
   - 优先读 `Q2_Typology_Summary_By_District.csv`

5. 要写方法是否可靠：
   - 优先读 `Q2_Validation_Report.json`

如果要用一句最简洁的话概括 Q2 已经做了什么，可以直接写成：

“Q2 已在 Q1 年度风险面板基础上，完成了建成区筛选、候选格网识别、本地核心区位刻画、时序机制特征构造、四分类判别、统计验证与最终成果导出，形成了可直接用于论文写作和答辩展示的正式结果体系。”
