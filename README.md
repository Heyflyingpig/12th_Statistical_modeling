# Q3 README

## 1. 当前正式口径

Q3 现在统一采用 **年度 RVRI** 口径，不再使用“季度状态转移”的旧表述。

- 正式研究时间尺度：`2019-2023` 年度
- 状态变量：`rvri` 与 `risk_state`
- 研究主线：`Moran's I / LISA -> Markov -> Spatial Markov -> 下一年低转高识别`

本次实际运行时，脚本优先查找 `Q1/output/`、`Q1/output1/`、`Q1/output_v1/` 下的年度主表；当前真正被读到并用于实跑的是：

- `Q1/output_v1/Shaoguan_RVRI_Q1_Validated.csv`
- `Q1/data/scientific_grid_500m.geojson`

因此，当前 Q3 的结果是基于 **年度版正式表已放在 `output_v1` 下** 的现状生成的。

---

## 2. 本次实际运行环境

本次实跑使用的解释器是：

```bash
D:\Anaconda\python.exe
```

一键运行命令：

```bash
D:\Anaconda\python.exe Q3\run_q3_all.py
```

分步运行命令：

```bash
D:\Anaconda\python.exe Q3\01_prepare_q3_panel.py
D:\Anaconda\python.exe Q3\02_build_spatial_weights.py
D:\Anaconda\python.exe Q3\03_spatial_autocorr.py --permutations 99
D:\Anaconda\python.exe Q3\04_markov_transition.py
D:\Anaconda\python.exe Q3\05_spatial_markov.py
D:\Anaconda\python.exe Q3\06_low_to_high_predict.py
```

---

## 3. 实现路径


### 3.1 公共底座

- `Q3/q3_utils.py`
  - 统一输入路径解析
  - 年度面板准备
  - 空间权重构建
  - Global Moran's I / Local Moran's I 计算
  - 空间滞后变量和邻域高风险占比计算
  - Markov 转移矩阵与 GeoJSON 输出

这里的空间统计实现没有依赖 `libpysal/esda`，而是直接在 `q3_utils.py` 中用：

- `Shapely STRtree` 构建 `Queen` 风格 `touches` 邻接
- `numpy + pandas` 手工实现 Moran/LISA 与 permutation 检验

这样做的原因是当前环境里基础科学计算栈可用，但不额外依赖 `libpysal/esda` 也能稳定复现文档要求的算法逻辑。

### 3.2 各步骤脚本

- `Q3/01_prepare_q3_panel.py`
  - 从 Q1 年度主表提取 `grid_id / year / rvri / risk_state / mismatch_gap / ndbi / ndvi / light / district_name`
  - 生成 `delta_rvri`、`delta_mismatch_gap`
  - 构造相邻年度转移样本

- `Q3/02_build_spatial_weights.py`
  - 用 `Q1/data/scientific_grid_500m.geojson` 构建全量 500m 网格邻接关系
  - 输出节点表与边表

- `Q3/03_spatial_autocorr.py`
  - 逐年计算 `2019-2023` 的 `Global Moran's I`
  - 对最新年份计算 `Local Moran's I`
  - 输出年度趋势图与最新年度 LISA 地图

- `Q3/04_markov_transition.py`
  - 基于 `(risk_state_t, risk_state_t+1)` 构建一步转移矩阵
  - 输出总体矩阵、分区县矩阵和 `P^2 / P^3`

- `Q3/05_spatial_markov.py`
  - 计算 `spatial_lag_rvri` 和 `neighbor_high_ratio`
  - 将邻域环境分为 `low / mid / high`
  - 比较不同邻域风险背景下的转移概率

- `Q3/06_low_to_high_predict.py`
  - 只对 `risk_state = 0` 的样本建模
  - 标签定义为 `0 -> 2`
  - 使用 `Pooled Logistic Regression`
  - 数值变量标准化，类别变量 One-Hot
  - 回测评估：`2019->2020`、`2020->2021`、`2021->2022` 训练，`2022->2023` 测试
  - 最终预测：用 `2019->2023` 全部历史转移重新拟合后，对 `2023` 截面输出下一年风险概率

注意：当前 `q3_prediction_report.json` 会同时保留 **时间回测指标** 和 **最终真实预测的打分范围**；而 `low_to_high_prob_next_year.*` 这一组输出，应该始终对应真正的“基于最新年度截面预测下一年”结果。

---

## 4. 每一步的实际运行结果

### Step 1. 年度面板准备

输入：

- `Q1/output_v1/Shaoguan_RVRI_Q1_Validated.csv`

建模算法：

- `Panel Data Engineering`：按 `grid_id + year` 组织年度面板
- `Feature Engineering`：构造 `delta_rvri`、`delta_mismatch_gap`
- `State Transition Sample Construction`：生成 `t -> t+1` 的相邻年度转移样本

输出：

- `Q3/output/q3_panel.csv`
- `Q3/output/q3_transition_panel.csv`
- `Q3/output/q3_panel_metadata.json`

实际结果：

- 年度面板总行数：`396302`
- 覆盖格网数：`79353`
- 年份数：`5`
- 有效转移样本数：`316927`
- 年度转移对：`2019->2020`、`2020->2021`、`2021->2022`、`2022->2023`

说明：

- 这一层已经把 Q1 年度主表转换成 Q3 可直接使用的“状态演化底表”。

### Step 2. 空间权重构建

输入：

- `Q1/data/scientific_grid_500m.geojson`

建模算法：

- `Queen Contiguity Spatial Weights`：基于格网边/角接触定义邻接关系
- `Shapely STRtree Spatial Index`：用空间索引高效查询 `touches` 邻接
- `Adjacency Graph Construction`：输出节点表、边表和度统计

输出：

- `Q3/output/spatial_weight_nodes.csv`
- `Q3/output/spatial_weights_edges.csv.gz`
- `Q3/output/spatial_weights_summary.json`

实际结果：

- 节点数：`79533`
- 有向邻接边数：`629602`
- 估计无向边数：`314801`
- 最小邻居数：`3`
- 最大邻居数：`8`
- 平均邻居数：`7.9162`

说明：

- 这一步已经把 500m 规则格网转成后续 Moran、LISA 和 Spatial Markov 能直接调用的邻接结构。

### Step 3. 年度空间自相关

建模算法：

- `Global Moran's I`：检验整体空间自相关强度
- `Local Moran's I (LISA)`：识别 `HH / LL / HL / LH` 局部集聚类型
- `Permutation Test`：通过随机置换得到 `p-value` 与显著性判断

输出：

- `Q3/output/annual_moran_report.csv`
- `Q3/output/q3_lisa_panel.csv`
- `Q3/output/lisa_cluster_latest.geojson`
- `Q3/output/Q3_Moran_Trend.png`
- `Q3/output/Q3_LISA_Map.png`

逐年实际结果：

| 年份 | Moran's I | p-value | HH | LL |
| --- | ---: | ---: | ---: | ---: |
| 2019 | 0.7227 | 0.01 | 12946 | 12017 |
| 2020 | 0.7335 | 0.01 | 13946 | 11576 |
| 2021 | 0.7413 | 0.01 | 13999 | 10688 |
| 2022 | 0.7297 | 0.01 | 14060 | 11546 |
| 2023 | 0.7401 | 0.01 | 13524 | 12107 |

关键判断：

- `2019-2023` 为 `5/5` 年显著正相关
- 已满足“至少 `4/5` 年 `Moran's I > 0` 且 `p < 0.05`”的成功标准
- 最新年度 `2023` 仍然显著为正

因此，Q3 关于“空置风险具有空间自相关和空间集聚”的论证是成立的。

### Step 4. 年度 Markov 转移

建模算法：

- `First-Order Markov Chain`：用一步状态转移矩阵刻画年度演化规律
- `Transition Probability Matrix`：估计 `risk_state_t -> risk_state_t+1` 的条件概率
- `Matrix Power (P^2 / P^3)`：刻画多期累计演化趋势

输出：

- `Q3/output/markov_transition_matrix.csv`
- `Q3/output/markov_transition_by_district.csv`
- `Q3/output/markov_k_step_summary.json`

总体一步转移矩阵 `P`：

| 当前状态 \\ 下一状态 | 0 | 1 | 2 |
| --- | ---: | ---: | ---: |
| 0 | 0.8059 | 0.1854 | 0.0087 |
| 1 | 0.1869 | 0.6912 | 0.1219 |
| 2 | 0.0072 | 0.1234 | 0.8694 |

关键判断：

- 主对角线占优，状态具有明显持续性
- `P(2->2) = 0.8694` 明显大于 `P(2->0) = 0.0072`
- `P(0->2) = 0.0087` 非零，说明存在跨级跃迁

因此，Q3 关于“空置风险具有年度状态转移规律”的论证也是成立的。

### Step 5. Spatial Markov

建模算法：

- `Spatial Lag`：计算 `spatial_lag_rvri`
- `Neighbor Risk Context Encoding`：用 `neighbor_high_ratio` 将邻域环境分为 `low / mid / high`
- `Spatial Markov Chain`：比较不同邻域背景下的条件转移概率

输出：

- `Q3/output/q3_panel_spatial.csv`
- `Q3/output/spatial_markov_matrix.csv`
- `Q3/output/spatial_markov_comparison.png`
- `Q3/output/spatial_diffusion_summary.json`

关键对比结果：

- `P(0->2 | high) = 0.0305`
- `P(0->2 | low) = 0.0067`
- `P(1->2 | high) = 0.2102`
- `P(1->2 | low) = 0.0757`

解释：

- 在高风险邻域条件下，低风险格网和中风险格网都更容易继续升级
- 其中 `0->2` 在高风险邻域下约为低风险邻域的 `4.57` 倍

因此，Q3 关于“风险升级受到周边高风险环境带动”的扩散机制证据是成立的。

### Step 6. 下一年低转高识别

建模算法：

- `Pooled Logistic Regression`：对全部年度低风险样本进行合并建模
- `Standardization + One-Hot Encoding`：数值变量标准化、类别变量哑变量化
- `Temporal Holdout Validation`：按时间切分做 `2022->2023` 回测
- `Future Cross-Section Scoring`：用全历史转移重新拟合后，对 `2023` 截面输出 `2024` 风险打分

输出：

- `Q3/output/low_to_high_prob_next_year.csv`
- `Q3/output/low_to_high_prob_next_year.geojson`
- `Q3/output/Q3_LowToHigh_Risk_Map.png`
- `Q3/output/q3_prediction_report.json`

实际回测划分：

- 训练：`2019->2020`、`2020->2021`、`2021->2022`
- 测试：`2022->2023`

实际结果：

- 训练样本数：`79258`
- 测试样本数：`26419`
- 测试集事件率：`0.95%`
- `ROC-AUC = 0.7317`
- `Top 10% hit rate = 2.95%`
- `Lift@10% = 3.1086`

解释：

- `ROC-AUC >= 0.70` 与 `Lift@10% >= 2` 两条都已经满足，说明该模块已经具备中等强度的判别力与排序筛查价值
- 当前模型最有解释力的增量特征包括：接近中风险阈值的程度、当前 `mismatch_gap`、空间滞后 `rvri` 和 `light`
- 但高分格网并不完全等同于 `LH` 边缘带，说明模型抓到的是“综合升级风险”，不应把它过度简化为单一扩散边界图

当前脚本会把这一步拆成两层：

- 一层是 `2022->2023` 的时间回测，用于诚实报告模型判别力
- 一层是基于 `2023` 截面的真实下一年风险打分，用于输出格网级筛查结果

因此，这一步现在可以写成“已经达到任务设定的回测指标门槛，并可用于重点区域筛查”，但仍要避免夸大成完全成熟的强预测模型。

---

## 5. output 目录里各文件的用途

### 5.1 中间底表

- `q3_panel.csv`
  - Q3 的年度主底表
- `q3_transition_panel.csv`
  - 年度相邻转移样本
- `q3_panel_spatial.csv`
  - 在年度主底表上补充了空间滞后、邻域高风险占比等变量
- `q3_lisa_panel.csv`
  - 每个格网每年的 LISA 类型结果

### 5.2 空间统计结果

- `annual_moran_report.csv`
  - `2019-2023` 每年的 Moran's I、p 值和各类聚类数量
- `lisa_cluster_latest.geojson`
  - 最新年度 LISA 聚类空间结果，可直接进 GIS

### 5.3 状态转移结果

- `markov_transition_matrix.csv`
  - 总体一步转移矩阵
- `markov_transition_by_district.csv`
  - 各区县一步转移矩阵
- `markov_k_step_summary.json`
  - `P`、`P^2`、`P^3` 和关键判断结果
- `spatial_markov_matrix.csv`
  - 不同邻域风险档位下的条件转移矩阵
- `spatial_diffusion_summary.json`
  - 高邻域风险与低邻域风险的关键对比摘要

### 5.4 概率识别结果

- `low_to_high_prob_next_year.csv`
  - 基于最新年度截面的下一年格网级预测概率清单
- `low_to_high_prob_next_year.geojson`
  - 基于最新年度截面的下一年预测概率空间图层
- `q3_prediction_report.json`
  - 同时记录时间回测指标、最终训练范围和下一年预测输出摘要

### 5.5 总汇总文件

- `q3_summary.json`
  - 汇总了每一步的实际输入、输出和关键指标

---

## 6. output 里有用的图分别代表什么

### 6.1 `Q3_Moran_Trend.png`

这张图展示 `2019-2023` 每年的 `Global Moran's I` 变化趋势。

怎么看：

- 横轴是年份
- 纵轴是 Moran's I
- 曲线越稳定地位于 `0` 以上，越说明高风险和低风险不是随机散点，而是长期保持空间聚集

当前图的含义：

- 五个年份都稳定在 `0.72-0.74` 左右
- 说明空置风险的空间集聚不是某一年的偶发现象，而是连续存在的结构特征

### 6.2 `Q3_LISA_Map.png`

这张图展示 **最新年度 `2023`** 的局部空间聚类类型。

图上的主要类型：

- `HH`：高风险格网周围仍是高风险格网
- `LL`：低风险格网周围仍是低风险格网
- `HL`：高风险点被低风险环境包围
- `LH`：低风险点被高风险环境包围
- `NS`：不显著

怎么看：

- `HH` 连片区可理解为高风险集聚核心区
- `HL / LH` 更像风险边缘带、过渡带
- `LL` 连片区可理解为低风险稳定区

这张图对 Q3 的意义最大，因为它直接回答了“高风险是不是成片出现”，也能为下一步扩散边界识别提供空间参照。

### 6.3 `spatial_markov_comparison.png`

这张图比较的是不同邻域风险背景下的升级概率。

怎么看：

- 横轴是邻域环境分组：`low / mid / high`
- 两组柱子分别表示：
  - `0->2`
  - `1->2`
- 如果 `high` 档明显更高，就说明高风险片区会对周边产生外溢或带动作用

当前图的含义：

- `0->2` 和 `1->2` 两条升级路径在 `high` 邻域下都明显更高
- 因此可以把这张图当作“高风险片区边缘外溢”的直观证据图

### 6.4 `Q3_LowToHigh_Risk_Map.png`

这张图是格网级“低风险转高风险概率”地图。

怎么看：

- 颜色越深，表示模型给出的升级概率越高
- 图中高概率区如果主要沿着现有高风险片区边缘分布，说明模型至少抓住了一部分扩散走廊

需要特别注意：

- 当前这张图应对应 **“基于 `2023` 截面预测下一年”** 的真实预测图
- 它更适合解释“哪些格网在最新一年已经表现出更高升级倾向，值得优先筛查”
- 当前回测 `ROC-AUC` 已超过 `0.70`，说明这张图具备一定判别力
- 但由于高分区并不完全落在 `LH` 边缘带，它更适合写成“综合风险筛查图”，而不是单一空间扩散边界图

---

## 7. 当前最稳妥的结论写法

基于 `2019-2023` 年度 RVRI，Q3 已经通过实跑形成三条较稳固的结论：

1. 空置风险具有显著且持续的空间自相关。
2. 空置风险具有明显的年度状态持续性与有限跨级跃迁。
3. 高风险邻域会显著抬升周边格网的升级概率，存在空间扩散机制。

同时也要保留一条审慎结论：

4. 当前“下一年低转高识别”模块已经达到回测指标门槛，可作为重点区域筛查工具使用，但仍应继续优化空间边缘解释力与概率校准。

---

## 8. 一句话总结

Q3 现在已经不是“计划版 README”，而是“按实际代码路径与实际结果更新后的 README”：前 3 个模块已经稳定支撑主体结论，预测模块已跑通并可用作重点区域筛查，但还不能夸大为高精度预测模型。
