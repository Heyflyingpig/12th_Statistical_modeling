from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd

from q2_pipeline_utils import resolve_existing_file, write_step_log


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"

    parser = argparse.ArgumentParser(
        description="汇总 Q2 最终交付文件。"
    )
    parser.add_argument("--table", type=Path, default=None, help="分类结果表路径。")
    parser.add_argument("--map", type=Path, default=None, help="分类结果地图路径。")
    parser.add_argument("--report", type=Path, default=None, help="验证报告路径。")
    parser.add_argument("--type-profile", type=Path, default=None, help="类型画像表路径。")
    parser.add_argument("--district-summary", type=Path, default=None, help="区县汇总表路径。")
    parser.add_argument(
        "--master-csv",
        type=Path,
        default=output_dir / "Q2_Grid_Typology_Master.csv",
        help="最终主表输出路径。",
    )
    parser.add_argument(
        "--master-geojson",
        type=Path,
        default=output_dir / "Q2_Grid_Typology_Master.geojson",
        help="最终主地图输出路径。",
    )
    parser.add_argument(
        "--overall-summary",
        type=Path,
        default=output_dir / "Q2_Typology_Summary_Overall.csv",
        help="总体汇总输出路径。",
    )
    parser.add_argument(
        "--district-summary-output",
        type=Path,
        default=output_dir / "Q2_Typology_Summary_By_District.csv",
        help="区县汇总输出路径。",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=output_dir / "logs" / "07_export_q2_deliverables.json",
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


def build_overall_summary(type_profile: pd.DataFrame) -> pd.DataFrame:
    """构建总体汇总表。"""
    columns = ["q2_type", "q2_label", "sample_count", "sample_share"]
    additional = [col for col in type_profile.columns if col.endswith("_mean")][:6]
    return type_profile[columns + additional].copy()


def main() -> None:
    """主入口。"""
    args = parse_args()
    output_dir = Path(__file__).resolve().parent / "output"

    table_path = resolve_input(args.table, output_dir, ["Q2_Classified_GridTable.csv"])
    map_path = resolve_input(args.map, output_dir, ["Q2_Classified_GridMap.geojson"])
    report_path = resolve_input(args.report, output_dir, ["Q2_Validation_Report.json"])
    type_profile_path = resolve_input(args.type_profile, output_dir, ["Q2_Type_Profile.csv"])
    district_summary_path = resolve_input(args.district_summary, output_dir, ["Q2_District_Summary.csv"])

    classified_table = pd.read_csv(table_path)
    classified_table.to_csv(args.master_csv, index=False, encoding="utf-8-sig")

    classified_map = gpd.read_file(map_path)
    classified_map.to_file(args.master_geojson, driver="GeoJSON")

    type_profile = pd.read_csv(type_profile_path)
    overall_summary = build_overall_summary(type_profile)
    overall_summary.to_csv(args.overall_summary, index=False, encoding="utf-8-sig")

    district_summary = pd.read_csv(district_summary_path)
    district_summary.to_csv(args.district_summary_output, index=False, encoding="utf-8-sig")

    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.master_csv, final_dir / "Q2_Main_Result_Table.csv")
    shutil.copy2(args.master_geojson, final_dir / "Q2_Type_Map.geojson")

    warnings: list[str] = []
    if not report_path.exists():
        warnings.append("验证报告缺失，已跳过复制。")

    log_payload = {
        "input_table": str(table_path),
        "input_map": str(map_path),
        "input_report": str(report_path),
        "input_type_profile": str(type_profile_path),
        "input_district_summary": str(district_summary_path),
        "master_csv": str(args.master_csv),
        "master_geojson": str(args.master_geojson),
        "overall_summary": str(args.overall_summary),
        "district_summary_output": str(args.district_summary_output),
        "final_dir": str(final_dir),
        "rows_master": int(len(classified_table)),
        "rows_map": int(len(classified_map)),
        "warnings": warnings,
    }
    write_step_log(args.log, log_payload)

    print("Q2 第07步完成")
    print(f"- 主表输出: {args.master_csv}")
    print(f"- 主地图输出: {args.master_geojson}")
    print(f"- 总体汇总: {args.overall_summary}")
    print(f"- 区县汇总: {args.district_summary_output}")
    print(f"- final 目录: {final_dir}")


if __name__ == "__main__":
    main()
