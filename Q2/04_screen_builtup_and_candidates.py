from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from q2_pipeline_utils import resolve_existing_file, write_step_log


REQUIRED_COLUMNS = [
    "grid_id",
    "district_name",
    "rvri_2023",
    "risk_state_2023",
    "stock_2023",
    "mismatch_mean",
    "ndbi_2023",
    "ndvi_2023",
    "risk_high_freq",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"

    parser = argparse.ArgumentParser(
        description="筛除非建成区并识别 Q2 空置风险候选格网。"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="输入特征表路径，留空时自动识别。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=output_dir / "Q2_CandidateTable.csv",
        help="候选格网表输出路径。",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=output_dir / "logs" / "04_screen_builtup_and_candidates.json",
        help="步骤日志输出路径。",
    )
    return parser.parse_args()


def resolve_input(user_input: Path | None, output_dir: Path) -> Path:
    """识别输入特征表。"""
    if user_input is not None:
        return user_input

    path = resolve_existing_file(
        output_dir,
        [
            "Q2_Grid_Features_2019_2023.csv",
            "Q2_Grid_FeatureTable.csv",
        ],
    )
    if path is None:
        raise FileNotFoundError("未找到 Q2 特征表输入文件。")
    return path


def load_features(path: Path) -> pd.DataFrame:
    """读取特征表并检查必要字段。"""
    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"输入特征表缺少必要字段: {missing}")
    return frame


def compute_thresholds(frame: pd.DataFrame) -> dict[str, float]:
    """计算筛选阈值。"""
    valid = frame.copy()
    return {
        "ndbi_2023_q35": float(valid["ndbi_2023"].quantile(0.35)),
        "stock_2023_q35": float(valid["stock_2023"].quantile(0.35)),
        "ndvi_2023_q75": float(valid["ndvi_2023"].quantile(0.75)),
        "rvri_2023_q65": float(valid["rvri_2023"].quantile(0.65)),
        "mismatch_mean_q65": float(valid["mismatch_mean"].quantile(0.65)),
        "risk_high_freq_q65": float(valid["risk_high_freq"].quantile(0.65)),
        "risk_state_high": float(valid["risk_state_2023"].dropna().max()),
        "risk_state_medium": float(valid["risk_state_2023"].dropna().quantile(0.5)),
    }


def screen_candidates(frame: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    """按文档逻辑筛选建成区与空置风险候选。"""
    screened = frame.copy()

    builtup_flag = (
        (
            screened["ndbi_2023"] >= thresholds["ndbi_2023_q35"]
        )
        | (
            screened["stock_2023"] >= thresholds["stock_2023_q35"]
        )
    ) & ~(
        (screened["ndvi_2023"] >= thresholds["ndvi_2023_q75"])
        & (screened["ndbi_2023"] < thresholds["ndbi_2023_q35"])
    )

    vacancy_candidate_flag = builtup_flag & (
        (screened["risk_state_2023"] >= thresholds["risk_state_medium"])
        | (screened["rvri_2023"] >= thresholds["rvri_2023_q65"])
        | (screened["risk_high_freq"] >= max(0.4, thresholds["risk_high_freq_q65"]))
        | (screened["mismatch_mean"] >= thresholds["mismatch_mean_q65"])
    )

    screened["builtup_flag"] = builtup_flag
    screened["vacancy_candidate_flag"] = vacancy_candidate_flag
    screened["screen_status"] = np.where(
        ~screened["builtup_flag"],
        "non_built_filtered",
        np.where(screened["vacancy_candidate_flag"], "vacancy_candidate", "stable_candidate"),
    )
    return screened


def main() -> None:
    """主入口。"""
    args = parse_args()
    output_dir = Path(__file__).resolve().parent / "output"
    input_path = resolve_input(args.input, output_dir)
    features = load_features(input_path)
    thresholds = compute_thresholds(features)
    candidates = screen_candidates(features, thresholds)
    candidates.to_csv(args.output, index=False, encoding="utf-8-sig")

    stats = {
        "input_file": str(input_path),
        "output_file": str(args.output),
        "input_rows": int(len(features)),
        "builtup_rows": int(candidates["builtup_flag"].sum()),
        "candidate_rows": int(candidates["vacancy_candidate_flag"].sum()),
        "stable_rows": int((candidates["screen_status"] == "stable_candidate").sum()),
        "non_built_rows": int((candidates["screen_status"] == "non_built_filtered").sum()),
        "thresholds": thresholds,
        "warnings": [],
    }
    write_step_log(args.log, stats)

    print("Q2 第04步完成")
    print(f"- 输入文件: {input_path}")
    print(f"- 输出文件: {args.output}")
    print(f"- 总格网数: {len(features)}")
    print(f"- 建成区格网数: {stats['builtup_rows']}")
    print(f"- 候选格网数: {stats['candidate_rows']}")
    print(f"- 稳定对照格网数: {stats['stable_rows']}")
    print(f"- 非建成过滤格网数: {stats['non_built_rows']}")


if __name__ == "__main__":
    main()
