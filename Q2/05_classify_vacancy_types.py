from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from q2_pipeline_utils import resolve_existing_file, write_step_log


REQUIRED_COLUMNS = [
    "grid_id",
    "district_name",
    "screen_status",
    "vacancy_candidate_flag",
    "rvri_2023",
    "stock_mean",
    "stock_slope",
    "mismatch_mean",
    "mismatch_slope",
    "light_slope",
    "ndbi_slope",
    "risk_high_freq",
    "build_lag",
    "persist_gap",
    "dist_to_local_core",
    "poi_density",
    "core_fringe_flag",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"

    parser = argparse.ArgumentParser(
        description="基于双得分机制进行 Q2 格网类型判别。"
    )
    parser.add_argument("--input", type=Path, default=None, help="候选格网表路径。")
    parser.add_argument("--spatial-map", type=Path, default=None, help="空间面板 GeoJSON 路径。")
    parser.add_argument(
        "--table-output",
        type=Path,
        default=output_dir / "Q2_Classified_GridTable.csv",
        help="分类结果表输出路径。",
    )
    parser.add_argument(
        "--map-output",
        type=Path,
        default=output_dir / "Q2_Classified_GridMap.geojson",
        help="分类结果地图输出路径。",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=output_dir / "logs" / "05_classify_vacancy_types.json",
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


def load_candidate_table(path: Path) -> pd.DataFrame:
    """读取候选格网表。"""
    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"候选格网表缺少必要字段: {missing}")
    return frame


def standardize(series: pd.Series) -> pd.Series:
    """标准化并将缺失视为中性值。"""
    numeric = pd.to_numeric(series, errors="coerce")
    std = numeric.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    standardized = (numeric - numeric.mean()) / std
    return standardized.fillna(0.0)


def encode_core_fringe(series: pd.Series) -> pd.Series:
    """将核心-边缘标识映射为数值。"""
    encoded = pd.Series(0.0, index=series.index)
    normalized = series.fillna("").astype(str).str.lower()
    encoded[normalized.str.contains("outer|fringe|外围|新区")] = 1.0
    encoded[normalized.str.contains("core|核心|老城")] = -1.0
    encoded[normalized.str.contains("transition|过渡")] = 0.5
    return encoded


def classify(frame: pd.DataFrame) -> pd.DataFrame:
    """执行双得分规则型分类。"""
    result = frame.copy()
    result["OldDeclineScore"] = 0.0
    result["NewExpansionScore"] = 0.0
    result["score_gap"] = np.nan
    result["q2_type"] = 0
    result["q2_label"] = "稳定占用型"

    candidate_mask = result["vacancy_candidate_flag"].fillna(False)
    candidates = result.loc[candidate_mask].copy()

    if not candidates.empty:
        core_fringe_score = encode_core_fringe(candidates["core_fringe_flag"])

        old_score = (
            standardize(candidates["rvri_2023"])
            + standardize(candidates["stock_mean"])
            + standardize(candidates["mismatch_mean"])
            + standardize(candidates["persist_gap"])
            + standardize(candidates["risk_high_freq"])
            + standardize(-candidates["stock_slope"])
            + standardize(-candidates["light_slope"])
            + standardize(-candidates["dist_to_local_core"])
            + standardize(candidates["poi_density"])
            + standardize(-core_fringe_score)
        )

        new_score = (
            standardize(candidates["rvri_2023"])
            + standardize(candidates["stock_slope"])
            + standardize(candidates["ndbi_slope"])
            + standardize(candidates["build_lag"])
            + standardize(candidates["mismatch_slope"].fillna(candidates["mismatch_mean"]))
            + standardize(candidates["dist_to_local_core"])
            + standardize(-candidates["poi_density"])
            + standardize(core_fringe_score)
        )

        score_gap = old_score - new_score
        gap_threshold = max(0.5, float(np.nanstd(score_gap) * 0.35))

        result.loc[candidate_mask, "OldDeclineScore"] = old_score.values
        result.loc[candidate_mask, "NewExpansionScore"] = new_score.values
        result.loc[candidate_mask, "score_gap"] = score_gap.values

        old_mask = candidate_mask & (result["score_gap"] >= gap_threshold)
        new_mask = candidate_mask & (result["score_gap"] <= -gap_threshold)
        mixed_mask = candidate_mask & ~(old_mask | new_mask)

        result.loc[old_mask, "q2_type"] = 1
        result.loc[old_mask, "q2_label"] = "老城衰退型空置"
        result.loc[new_mask, "q2_type"] = 2
        result.loc[new_mask, "q2_label"] = "新区扩张型空置"
        result.loc[mixed_mask, "q2_type"] = 3
        result.loc[mixed_mask, "q2_label"] = "过渡混合型"

    return result


def build_map(table: pd.DataFrame, spatial_map_path: Path, map_output: Path) -> dict:
    """将分类结果回写到 GeoJSON。"""
    data = json.loads(spatial_map_path.read_text(encoding="utf-8"))
    table_lookup = table.set_index("grid_id").to_dict(orient="index")
    latest_by_grid: dict[str, dict] = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        grid_id = str(props.get("grid_id"))
        year = props.get("source_year", props.get("year", -1))
        previous = latest_by_grid.get(grid_id)
        previous_year = previous.get("properties", {}).get("source_year", previous.get("properties", {}).get("year", -1)) if previous else -1
        if previous is None or int(year) >= int(previous_year):
            latest_by_grid[grid_id] = feature

    features = []
    for grid_id, feature in latest_by_grid.items():
        merged_props = dict(feature.get("properties", {}))
        if grid_id in table_lookup:
            for key, value in table_lookup[grid_id].items():
                if pd.isna(value):
                    merged_props[key] = None
                elif isinstance(value, np.generic):
                    merged_props[key] = value.item()
                else:
                    merged_props[key] = value
        features.append({"type": "Feature", "properties": merged_props, "geometry": feature["geometry"]})

    payload = {"type": "FeatureCollection", "features": features}
    map_output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {
        "map_rows": int(len(features)),
        "map_output": str(map_output),
    }


def main() -> None:
    """主入口。"""
    args = parse_args()
    output_dir = Path(__file__).resolve().parent / "output"
    input_path = resolve_input(args.input, output_dir, ["Q2_CandidateTable.csv"])
    spatial_map_path = resolve_input(
        args.spatial_map,
        output_dir,
        ["Q2_BasePanel_Spatial_2019_2023.geojson"],
    )

    candidate_table = load_candidate_table(input_path)
    classified = classify(candidate_table)
    classified.to_csv(args.table_output, index=False, encoding="utf-8-sig")
    map_info = build_map(classified, spatial_map_path, args.map_output)

    counts = classified["q2_label"].value_counts(dropna=False).to_dict()
    log_payload = {
        "input_file": str(input_path),
        "spatial_map_file": str(spatial_map_path),
        "table_output": str(args.table_output),
        "map_output": str(args.map_output),
        "rows": int(len(classified)),
        "candidate_rows": int(classified["vacancy_candidate_flag"].fillna(False).sum()),
        "type_counts": counts,
        "warnings": [],
        **map_info,
    }
    write_step_log(args.log, log_payload)

    print("Q2 第05步完成")
    print(f"- 输入文件: {input_path}")
    print(f"- 分类结果表: {args.table_output}")
    print(f"- 分类结果图: {args.map_output}")
    print(f"- 总格网数: {len(classified)}")
    for label, count in counts.items():
        print(f"  - {label}: {count}")


if __name__ == "__main__":
    main()
