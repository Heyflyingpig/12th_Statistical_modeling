from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


# Q2 当前必须保留的字段
REQUIRED_COLUMNS = [
    "grid_id",
    "district_name",
    "source_year",
    "rvri",
    "risk_state",
    "stock_pressure",
    "mismatch_gap",
    "ndbi",
    "light",
    "ndvi",
]

# 这些字段缺失时，不适合继续进入 Q2 后续流程
CRITICAL_COLUMNS = [
    "grid_id",
    "district_name",
    "source_year",
    "rvri",
    "risk_state",
    "stock_pressure",
    "mismatch_gap",
    "ndbi",
    "light",
    "ndvi",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    base_dir = Path(__file__).resolve().parent.parent
    default_input = base_dir / "Q1" / "output" / "Shaoguan_RVRI_Q1_Validated.csv"
    default_output = base_dir / "Q2" / "output" / "Q2_BasePanel_2019_2023.csv"

    parser = argparse.ArgumentParser(
        description="构建 Q2 的年度基础面板表。"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help="Q1 年度面板输入文件路径。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help="Q2 基础面板输出文件路径。",
    )
    return parser.parse_args()


def validate_columns(frame: pd.DataFrame, required_columns: list[str]) -> None:
    """检查输入字段是否齐全。"""
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"输入文件缺少必要字段: {missing}")


def standardize_types(frame: pd.DataFrame) -> pd.DataFrame:
    """统一字段类型。"""
    cleaned = frame.copy()

    cleaned["grid_id"] = cleaned["grid_id"].astype(str).str.strip()
    cleaned["district_name"] = cleaned["district_name"].astype(str).str.strip()

    cleaned["source_year"] = pd.to_numeric(cleaned["source_year"], errors="coerce")
    cleaned["risk_state"] = pd.to_numeric(cleaned["risk_state"], errors="coerce")
    cleaned["rvri"] = pd.to_numeric(cleaned["rvri"], errors="coerce")
    cleaned["stock_pressure"] = pd.to_numeric(cleaned["stock_pressure"], errors="coerce")
    cleaned["mismatch_gap"] = pd.to_numeric(cleaned["mismatch_gap"], errors="coerce")
    cleaned["ndbi"] = pd.to_numeric(cleaned["ndbi"], errors="coerce")
    cleaned["light"] = pd.to_numeric(cleaned["light"], errors="coerce")
    cleaned["ndvi"] = pd.to_numeric(cleaned["ndvi"], errors="coerce")

    return cleaned


def drop_invalid_string_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """清理字符串键值中的空字符串和伪缺失值。"""
    cleaned = frame.copy()

    invalid_tokens = {"", "nan", "none", "null"}
    for column in ["grid_id", "district_name"]:
        normalized = cleaned[column].str.lower()
        cleaned.loc[normalized.isin(invalid_tokens), column] = pd.NA

    return cleaned


def deduplicate_panel(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """按 grid_id + source_year 去重。"""
    before = len(frame)
    deduped = frame.drop_duplicates(subset=["grid_id", "source_year"], keep="first").copy()
    removed = before - len(deduped)
    return deduped, removed


def missing_summary(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    """统计关键字段缺失数。"""
    return frame[columns].isna().sum().sort_index()


def drop_critical_missing(frame: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, int]:
    """删除关键字段缺失记录。"""
    before = len(frame)
    cleaned = frame.dropna(subset=columns).copy()
    removed = before - len(cleaned)
    return cleaned, removed


def build_basepanel(input_path: Path, output_path: Path) -> None:
    """执行 Q2 基础面板构建流程。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到输入文件: {input_path}")

    raw = pd.read_csv(input_path)
    validate_columns(raw, REQUIRED_COLUMNS)

    panel = raw[REQUIRED_COLUMNS].copy()
    raw_rows = len(panel)

    panel = standardize_types(panel)
    panel = drop_invalid_string_keys(panel)

    panel, duplicate_removed = deduplicate_panel(panel)
    missing_before_drop = missing_summary(panel, CRITICAL_COLUMNS)
    panel, missing_removed = drop_critical_missing(panel, CRITICAL_COLUMNS)

    panel["source_year"] = panel["source_year"].astype(int)
    panel["risk_state"] = panel["risk_state"].astype(int)
    panel = panel.sort_values(["source_year", "grid_id"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_path, index=False, encoding="utf-8-sig")

    year_counts = panel["source_year"].value_counts().sort_index()

    print("Q2 基础面板构建完成")
    print(f"- 输入文件: {input_path}")
    print(f"- 输出文件: {output_path}")
    print(f"- 原始记录数: {raw_rows}")
    print(f"- 去重移除记录数: {duplicate_removed}")
    print(f"- 关键缺失移除记录数: {missing_removed}")
    print(f"- 清洗后记录数: {len(panel)}")
    print("- 年份分布:")
    for year, count in year_counts.items():
        print(f"  - {year}: {count}")
    print("- 关键字段缺失统计（去重后、删除前）:")
    for column, count in missing_before_drop.items():
        print(f"  - {column}: {int(count)}")


def main() -> None:
    """主入口。"""
    args = parse_args()
    build_basepanel(input_path=args.input, output_path=args.output)


if __name__ == "__main__":
    main()
