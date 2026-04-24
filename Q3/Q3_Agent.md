# Q3 Agent

## 1. 任务定义

Q3 要基于 Q1 已经形成的 RVRI 成果，回答三件事：

- 空置风险是否具有空间自相关
- 空置风险是否具有状态转移规律
- 下一年哪些区域更可能从“低风险”转为“高风险”

当前正式口径必须以“年度版 Q1”为准，不再默认使用季度状态转移叙述。

---

## 2. 输入优先级

优先使用：

- `Q1/output/Shaoguan_RVRI_Q1_Validated.csv`
- `Q1/data/scientific_grid_500m.geojson`

如果正式主表暂时未生成，可兼容使用：

- `Q1/output_v1/Shaoguan_RVRI_Long_Panel_Final.csv`

但一旦走兼容路径，必须先把时间粒度整理回年度口径，再进入 Q3。

---

## 3. 推荐技术路线

### Step 1. 准备 Q3 面板

- 保留 `grid_id`
- 统一出 `year`
- 保留 `rvri`
- 保留 `risk_state`
- 保留 `mismatch_gap / ndbi / ndvi / light / district_name`
- 构造 `state_t -> state_t+1`

### Step 2. 做空间自相关

- 构建 `Queen` 权重矩阵
- 逐年计算 `Global Moran's I`
- 对最新年度计算 `Local Moran's I`
- 输出 `HH / LL / HL / LH`

### Step 3. 做 Markov 转移

- 按 `grid_id + year` 构造相邻年度状态对
- 计算总体转移矩阵
- 计算分区县转移矩阵
- 计算 `P^k` 解释多期演化

### Step 4. 做 Spatial Markov

- 计算 `spatial_lag_rvri`
- 计算 `neighbor_high_ratio`
- 将邻域风险分档
- 比较不同邻域条件下的 `0->2` 和 `1->2`

### Step 5. 做下一年低转高预测

- 只对当前 `risk_state = 0` 的格网建样本
- 标签定义：
  - `y = 1`: `0 -> 2`
  - `y = 0`: `0 -> 非2`
- 模型优先用 `Pooled Logistic Regression`
- 输出每个格网的下一年升级概率

---

## 4. 必须保留的特征

- `rvri`
- `risk_state`
- `mismatch_gap`
- `ndbi`
- `light`
- `ndvi`
- `delta_rvri`
- `delta_mismatch_gap`
- `spatial_lag_rvri`
- `neighbor_high_ratio`
- `lisa_type`
- `district_name`
- 年度哑变量

---

## 5. 本项目下怎么算“Q3 做成了”

### 空间自相关成功

- `2019-2023` 至少 `4/5` 个年度 `Moran's I > 0` 且 `p < 0.05`
- 最新年度结果仍显著为正
- `HH` 形成连续片区

### 状态转移成功

- 转移矩阵主对角线占优
- `P(2->2) > P(2->0)`
- `P(0->2)` 非零

### 空间扩散成功

- `P(0->2 | 高邻域风险)` 高于 `P(0->2 | 低邻域风险)`
- `P(1->2 | 高邻域风险)` 至少不低于低邻域风险条件

### 预测成功

- `ROC-AUC >= 0.70`
- `Lift@10% >= 2`
- 高概率格网主要落在既有高风险片区边缘或扩散带

---

## 6. 不要做错的事

- 不要再把 Q3 主结论写成“季度状态转移”
- 不要直接把 `output_v1` 的旧长面板当作最终正式口径
- 不要随机打散时间做训练测试划分
- 不要只给整体转移概率，不落到 `grid_id` 和地图
- 不要在当前仅有 5 个正式年度的前提下上过重黑箱模型

---

## 7. 建议生成的文件

- `Q3/01_prepare_q3_panel.py`
- `Q3/02_build_spatial_weights.py`
- `Q3/03_spatial_autocorr.py`
- `Q3/04_markov_transition.py`
- `Q3/05_spatial_markov.py`
- `Q3/06_low_to_high_predict.py`
- `Q3/output/q3_summary.json`

---

## 8. 一句话执行顺序

先证明“有空间自相关”，再证明“有状态转移”，再证明“转移受邻域影响”，最后输出“下一年哪些格网最可能低转高”。
