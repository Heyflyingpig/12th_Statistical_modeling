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
