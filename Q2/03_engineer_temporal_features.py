from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "grid_id",
    "district_name",
    "source_year",
    "rvri",
    "risk_state",
    "stock_pressure",
    "mismatch_gap",
    "light",
    "ndbi",
    "ndvi",
    "poi_count",
    "poi_density",
    "dist_to_local_core",
    "core_fringe_flag",
]

CURRENT_YEAR = 2023


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "output"

    parser = argparse.ArgumentParser(
        description="从年度空间面板构建 Q2 格网级时序特征表。"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=output_dir / "Q2_BasePanel_Spatial_2019_2023.csv",
        help="年度空间面板输入文件，可为 CSV 或 GeoJSON。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=output_dir / "Q2_Grid_Features_2019_2023.csv",
        help="格网级时序特征输出文件。",
    )
    return parser.parse_args()


def load_panel(path: Path) -> pd.DataFrame:
    """读取年度空间面板。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到输入文件: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".geojson", ".json"}:
        try:
            import geopandas as gpd
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "读取 GeoJSON 需要 geopandas，请改用 CSV 输入或在项目环境中运行。"
            ) from exc
        frame = gpd.read_file(path)
        frame = pd.DataFrame(frame.drop(columns="geometry", errors="ignore"))
    else:
        raise ValueError(f"不支持的输入格式: {path.suffix}")

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"输入文件缺少必要字段: {missing}")

    frame = frame.copy()
    frame["grid_id"] = frame["grid_id"].astype(str).str.strip()
    frame["district_name"] = frame["district_name"].astype(str).str.strip()
    frame["source_year"] = pd.to_numeric(frame["source_year"], errors="coerce").astype("Int64")

    numeric_columns = [
        "rvri",
        "risk_state",
        "stock_pressure",
        "mismatch_gap",
        "light",
        "ndbi",
        "ndvi",
        "poi_count",
        "poi_density",
        "dist_to_local_core",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["core_fringe_flag"] = frame["core_fringe_flag"].astype("string")
    return frame


def linear_slope(years: pd.Series, values: pd.Series) -> float:
    """计算一元线性回归斜率。

    说明：
    - 以年份为自变量 x
    - 以目标指标为因变量 y
    - 返回 y = a + b*x 中的 b
    - 有效观测少于 2 个时返回缺失值
    """
    valid = pd.DataFrame({"year": years, "value": values}).dropna()
    if len(valid) < 2:
        return np.nan

    x = valid["year"].to_numpy(dtype=float)
    y = valid["value"].to_numpy(dtype=float)
    x_centered = x - x.mean()
    denominator = np.sum(x_centered ** 2)
    if denominator == 0:
        return np.nan
    numerator = np.sum(x_centered * (y - y.mean()))
    return float(numerator / denominator)


def latest_non_null(series: pd.Series):
    """取序列中最后一个非空值。"""
    valid = series.dropna()
    if valid.empty:
        return pd.NA
    return valid.iloc[-1]


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    """构建格网级时序特征。"""
    panel = panel.sort_values(["grid_id", "source_year"]).copy()
    high_risk_state = panel["risk_state"].dropna().max()

    records: list[dict] = []
    grouped = panel.groupby("grid_id", sort=True)

    for grid_id, group in grouped:
        group = group.sort_values("source_year").copy()
        current = group[group["source_year"] == CURRENT_YEAR]
        current_row = current.iloc[0] if not current.empty else None

        valid_risk = group["risk_state"].dropna()
        valid_risk_years = len(valid_risk)
        if valid_risk_years == 0 or pd.isna(high_risk_state):
            risk_high_freq = np.nan
        else:
            risk_high_freq = float((valid_risk == high_risk_state).sum() / valid_risk_years)

        record = {
            "grid_id": grid_id,
            "district_name": latest_non_null(group["district_name"]),
            "poi_count": latest_non_null(group["poi_count"]),
            "poi_density": latest_non_null(group["poi_density"]),
            "dist_to_local_core": latest_non_null(group["dist_to_local_core"]),
            "core_fringe_flag": latest_non_null(group["core_fringe_flag"]),
            "rvri_2023": current_row["rvri"] if current_row is not None else np.nan,
            "risk_state_2023": current_row["risk_state"] if current_row is not None else np.nan,
            "stock_2023": current_row["stock_pressure"] if current_row is not None else np.nan,
            "mismatch_2023": current_row["mismatch_gap"] if current_row is not None else np.nan,
            "light_2023": current_row["light"] if current_row is not None else np.nan,
            "ndbi_2023": current_row["ndbi"] if current_row is not None else np.nan,
            "ndvi_2023": current_row["ndvi"] if current_row is not None else np.nan,
            "rvri_mean": float(group["rvri"].mean()) if group["rvri"].notna().any() else np.nan,
            "rvri_slope": linear_slope(group["source_year"], group["rvri"]),
            "risk_high_freq": risk_high_freq,
            "stock_mean": float(group["stock_pressure"].mean()) if group["stock_pressure"].notna().any() else np.nan,
            "stock_slope": linear_slope(group["source_year"], group["stock_pressure"]),
            "mismatch_mean": float(group["mismatch_gap"].mean()) if group["mismatch_gap"].notna().any() else np.nan,
            "mismatch_slope": linear_slope(group["source_year"], group["mismatch_gap"]),
            "light_mean": float(group["light"].mean()) if group["light"].notna().any() else np.nan,
            "light_slope": linear_slope(group["source_year"], group["light"]),
            "ndbi_slope": linear_slope(group["source_year"], group["ndbi"]),
            "year_count": int(group["source_year"].dropna().nunique()),
        }

        record["build_lag"] = (
            record["stock_slope"] - record["light_slope"]
            if pd.notna(record["stock_slope"]) and pd.notna(record["light_slope"])
            else np.nan
        )
        record["persist_gap"] = (
            record["mismatch_mean"] * record["risk_high_freq"]
            if pd.notna(record["mismatch_mean"]) and pd.notna(record["risk_high_freq"])
            else np.nan
        )

        records.append(record)

    features = pd.DataFrame.from_records(records)
    return features.sort_values("grid_id").reset_index(drop=True)


def export_features(features: pd.DataFrame, output_path: Path) -> None:
    """导出特征表。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False, encoding="utf-8-sig")


def main() -> None:
    """主入口。"""
    args = parse_args()
    panel = load_panel(args.input)
    features = build_features(panel)
    export_features(features, args.output)

    print("Q2 时序特征构建完成")
    print(f"- 输入文件: {args.input}")
    print(f"- 输出文件: {args.output}")
    print("- slope 计算方法: 以 source_year 为自变量的一元线性回归斜率")
    print(f"- 输出格网数: {len(features)}")
    print(f"- 当前截面年份: {CURRENT_YEAR}")
    print(f"- 2023 截面缺失格网数: {int(features['rvri_2023'].isna().sum())}")


if __name__ == "__main__":
    main()
