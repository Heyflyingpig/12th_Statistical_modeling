# Q1 Output Guide

`Q1/output/` 根目录只保留当前年度版正式结果。

当前正式结果包括：

1. `Shaoguan_RVRI_Q1_Validated.csv`
2. `Q1_Data_Quality_Audit.json`
3. `Q1_RVRI_Model_Metadata.json`
4. `Q1_Diagnostic_Full_Report.json`
5. `validation_report.json`
6. 当前年度版图件

历史结果归档规则：

1. `archive_legacy_quarterly_20260420/` 保存旧季度版与 2026-04-20 的历史快照结果。
2. `archive_legacy_misc/` 保存旧方法遗留图件与旧版 GeoJSON。

后续脚本默认应以本目录根部的年度版文件作为读取入口，不再直接依赖归档目录。
