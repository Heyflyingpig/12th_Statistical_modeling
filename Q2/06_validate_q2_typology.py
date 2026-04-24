from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from q2_pipeline_utils import resolve_existing_file, write_step_log


PROFILE_VARS = [
    "rvri_2023",
    "stock_mean",
    "stock_slope",
    "mismatch_mean",
    "light_slope",
    "ndbi_slope",
    "dist_to_local_core",
    "poi_density",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"

    parser = argparse.ArgumentParser(
        description="对 Q2 类型结果做统计验证与空间验证。"
    )
    parser.add_argument("--table", type=Path, default=None, help="分类结果表路径。")
    parser.add_argument("--map", type=Path, default=None, help="分类结果地图路径。")
    parser.add_argument(
        "--report",
        type=Path,
        default=output_dir / "Q2_Validation_Report.json",
        help="验证报告输出路径。",
    )
    parser.add_argument(
        "--type-profile",
        type=Path,
        default=output_dir / "Q2_Type_Profile.csv",
        help="类型画像表输出路径。",
    )
    parser.add_argument(
        "--district-summary",
        type=Path,
        default=output_dir / "Q2_District_Summary.csv",
        help="区县汇总表输出路径。",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=output_dir / "logs" / "06_validate_q2_typology.json",
        help="步骤日志输出路径。",
    )
    return parser.parse_args()


def resolve_input(user_input: Path | None, output_dir: Path, candidates: list[str]) -> Path:
    """识别输入文件。"""
    if user_input is not None:
        return user_input
    path = resolve_existing_file(output_dir, candidates)
    if path is None:
        raise FileNotFoundError(f"未找到输入文件，候选名称: {candidates}")
    return path


def build_type_profile(table: pd.DataFrame) -> pd.DataFrame:
    """构建类型画像表。"""
    records = []
    for q2_type, group in table.groupby(["q2_type", "q2_label"], dropna=False):
        q2_code, q2_label = q2_type
        record = {
            "q2_type": q2_code,
            "q2_label": q2_label,
            "sample_count": int(len(group)),
            "sample_share": float(len(group) / len(table)),
        }
        for var in PROFILE_VARS:
            if var in group.columns:
                record[f"{var}_mean"] = float(group[var].mean()) if group[var].notna().any() else None
                record[f"{var}_median"] = float(group[var].median()) if group[var].notna().any() else None
        records.append(record)
    return pd.DataFrame(records).sort_values("q2_type").reset_index(drop=True)


def build_district_summary(table: pd.DataFrame) -> pd.DataFrame:
    """构建区县类型汇总表。"""
    district_summary = (
        table.groupby(["district_name", "q2_type", "q2_label"], dropna=False)
        .size()
        .rename("sample_count")
        .reset_index()
    )
    district_total = (
        district_summary.groupby("district_name")["sample_count"]
        .sum()
        .rename("district_total")
        .reset_index()
    )
    district_summary = district_summary.merge(district_total, on="district_name", how="left")
    district_summary["sample_share"] = district_summary["sample_count"] / district_summary["district_total"]
    return district_summary.sort_values(["district_name", "q2_type"]).reset_index(drop=True)


def compute_optional_cluster_agreement(table: pd.DataFrame) -> dict:
    """使用 KMeans / GMM 做稳健性检验，并严格处理特征量纲。"""
    try:
        from sklearn.cluster import KMeans
        from sklearn.mixture import GaussianMixture
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError:
        return {"available": False, "message": "sklearn 未安装，跳过聚类稳健性检验。"}

    # 1. 扩充特征池：纳入 02 步产出的空间距离与功能密度，以及时序斜率
    candidate_features = [
        "rvri_2023", "stock_mean", "stock_slope", "mismatch_mean", 
        "build_lag", "dist_to_local_core", "poi_density", 
        "light_slope", "ndbi_slope"
    ]
    feature_cols = [col for col in candidate_features if col in table.columns]
    
    sample = table[table["vacancy_candidate_flag"].fillna(False)].copy()
    sample = sample.dropna(subset=feature_cols)
    
    if len(sample) < 10:
        return {"available": False, "message": "有效候选样本过少，跳过聚类稳健性检验。"}

    # 2. 核心步骤：特征标准化以消除量纲差异
    X = sample[feature_cols].values
    X_scaled = StandardScaler().fit_transform(X)

    # 3. 拟合 KMeans (硬聚类)
    # n_clusters=4 假设你有 4 种 q2_label，若实际不同请修改此参数
    k = sample["q2_label"].nunique() if sample["q2_label"].nunique() > 1 else 3
    kmeans = KMeans(n_clusters=k, n_init=20, random_state=42)
    kmeans_labels = kmeans.fit_predict(X_scaled)
    
    # 4. 拟合 GMM (软聚类：捕捉非球形分布的空间经济特征)
    gmm = GaussianMixture(n_components=k, n_init=5, random_state=42)
    gmm_labels = gmm.fit_predict(X_scaled)

    kmeans_cross_tab = pd.crosstab(sample["q2_label"], kmeans_labels).to_dict()
    gmm_cross_tab = pd.crosstab(sample["q2_label"], gmm_labels).to_dict()

    return {
        "available": True,
        "sample_rows": int(len(sample)),
        "feature_columns": feature_cols,
        "n_clusters_used": int(k),
        "kmeans_cross_tab": kmeans_cross_tab,
        "gmm_cross_tab": gmm_cross_tab,
    }


def main() -> None:
    """主入口。"""
    args = parse_args()
    output_dir = Path(__file__).resolve().parent / "output"
    table_path = resolve_input(args.table, output_dir, ["Q2_Classified_GridTable.csv"])
    map_path = resolve_input(args.map, output_dir, ["Q2_Classified_GridMap.geojson"])

    table = pd.read_csv(table_path)
    type_profile = build_type_profile(table)
    district_summary = build_district_summary(table)
    type_profile.to_csv(args.type_profile, index=False, encoding="utf-8-sig")
    district_summary.to_csv(args.district_summary, index=False, encoding="utf-8-sig")

    warnings: list[str] = []
    spatial_summary = {"map_file": str(map_path), "geometry_available": map_path.exists()}
    if table["core_fringe_flag"].isna().all():
        warnings.append("core_fringe_flag 全为空，当前空间区位验证仅基于 district_name 与地图文件存在性。")
    if table["dist_to_local_core"].isna().all():
        warnings.append("dist_to_local_core 全为空，老城核心距离尚未实装，分类更依赖时序与存量特征。")

    cluster_validation = compute_optional_cluster_agreement(table)
    if not cluster_validation.get("available", False):
        warnings.append(cluster_validation.get("message", "聚类稳健性检验未执行。"))

    report = {
        "input_table": str(table_path),
        "input_map": str(map_path),
        "overall_rows": int(len(table)),
        "type_counts": table["q2_label"].value_counts(dropna=False).to_dict(),
        "candidate_rows": int(table["vacancy_candidate_flag"].fillna(False).sum()),
        "type_profile_file": str(args.type_profile),
        "district_summary_file": str(args.district_summary),
        "spatial_validation": spatial_summary,
        "cluster_validation": cluster_validation,
        "warnings": warnings,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    write_step_log(args.log, report)

    print("Q2 第06步完成")
    print(f"- 输入表: {table_path}")
    print(f"- 验证报告: {args.report}")
    print(f"- 类型画像表: {args.type_profile}")
    print(f"- 区县汇总表: {args.district_summary}")
    print(f"- 样本总数: {len(table)}")
    if warnings:
        print("- 警告:")
        for warning in warnings:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
