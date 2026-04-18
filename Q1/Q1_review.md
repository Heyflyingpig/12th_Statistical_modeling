| time:2026.4.18

## Q1 审查结论
Q1 的大方向是合理的：用“建筑存量/建成强度 + 夜间灯光活力 + 植被或管理扰动 + 市场校准”构造住宅空置风险指数，理论上可以服务后续 Q2 类型识别和 Q3 空间扩散分析。但当前版本还不能直接作为正式建模结果使用，主要问题是“方案说得比较完整，实证过程和指标方向还不够可复现、可解释”。

## 主要问题

- 高风险：RVRI 合成过程不可复现。Q1/02_RVRI_Synthesis.py 和 Q1/02_RVRI_Synthesis.ipynb 都是 0 字节，但 README.md:20 已声称完成 PCA 且解释力为 47.64%。目前缺少标准化方法、PCA 载荷、贡献率、正负方向调整、缺失值处理和最终 rvri 生成代码。

- 高风险：实际指数逻辑与“房多灯暗”叙述不完全一致。README.md:31 说最高风险集中在“高存量、低活力”，但我抽查最终 GeoJSON 后发现 rvri 与 ndbi_base 相关性约 0.846，与 nightlight_base 相关性只有约 -0.058；最高风险样本里有不少 nightlight_base 很高的格网。这说明当前 RVRI 更像“建筑强度主导指数”，还没有充分证明是“空置风险”。

- 高风险：当前数据不是 Q3 所需的时间面板。Q1/Q1_Agent.md:43 写的是 2016-2026 逐季度风险评分，但实际 Shaoguan_Residential_RVRI_Panel_Data.csv 只有 Q1/Q3 相关字段，并没有年度或季度序列。若要做状态转移概率，至少需要多个时期的 rvri_t、risk_state_t、risk_state_t+1。

- 中高风险：区县字段命名和缺失存在问题。README.md:43 说最终字段是 district_name，但最终 GeoJSON 里是 district_name_x 和 district_name_y，其中 district_name_y 全为空；CSV 中 district_name 也是 84,815 行全空。这会影响后续挂接区县年鉴、人口、产业等宏观变量。

- 中风险：格网构建没有真正使用米制投影。Q1/01_Grid_Generator.py:13 使用 step=0.0045 经纬度近似 500m，Q1/01_Grid_Generator.py:35 仍沿用原始 CRS。实际输出 CRS 是 CRS84，不是 Q1/Q1_Agent.md:67 提到的 EPSG:4479。韶关纬度下首个格网约东西 452m、南北 500m，严格说不是 500m × 500m 等面积格网。

- 中风险：脚本环境不可复跑。我实际运行 python Q1/01_Grid_Generator.py，失败于 ModuleNotFoundError: No module named 'geopandas'。建议补 requirements.txt 或 environment.yml，并把 Q1 的完整处理链路固化为可运行脚本。