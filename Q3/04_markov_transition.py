from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


CURRENT_DIR = Path(__file__).resolve().parent
REPO_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from q3_utils import (
    LOGGER,
    OUTPUT_DIR,
    build_transition_matrix,
    ensure_q3_panel,
    matrix_power_summary,
    save_json,
    setup_logging,
    update_summary,
)


def build_argparser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="计算 Q3 整体与分区县 Markov 转移矩阵。")


def matrix_from_long(matrix_df: pd.DataFrame) -> np.ndarray:
    matrix = (
        matrix_df.pivot(index="risk_state", columns="next_risk_state", values="probability")
        .reindex(index=range(3), columns=range(3), fill_value=0.0)
        .to_numpy(dtype=float)
    )
    row_sum = matrix.sum(axis=1, keepdims=True)
    zero_rows = np.isclose(row_sum.squeeze(), 0.0)
    if zero_rows.any():
        matrix[zero_rows] = np.eye(3)[zero_rows]
        row_sum = matrix.sum(axis=1, keepdims=True)
    return matrix / row_sum


def main() -> None:
    setup_logging()
    build_argparser().parse_args()
    LOGGER.info("开始执行 Q3 Step 4：Markov 转移分析。")
    _, transition, panel_meta = ensure_q3_panel()
    transition = transition.loc[transition["in_analysis_domain"].fillna(False)].copy()
    transition["risk_state"] = pd.to_numeric(transition["risk_state"], errors="coerce").astype(int)
    transition["next_risk_state"] = pd.to_numeric(transition["next_risk_state"], errors="coerce").astype(int)

    overall_matrix = build_transition_matrix(transition_df=transition)
    district_matrix = build_transition_matrix(transition_df=transition, group_cols=["district_name"])

    overall_matrix_path = OUTPUT_DIR / "markov_transition_matrix.csv"
    district_matrix_path = OUTPUT_DIR / "markov_transition_by_district.csv"
    k_step_path = OUTPUT_DIR / "markov_k_step_summary.json"

    overall_matrix.to_csv(overall_matrix_path, index=False, encoding="utf-8-sig")
    district_matrix.to_csv(district_matrix_path, index=False, encoding="utf-8-sig")

    matrix = matrix_from_long(overall_matrix)
    k_step_payload = {
        "input_path": panel_meta["input_path"],
        "analysis_domain": panel_meta.get("analysis_domain"),
        "transition_rows": int(len(transition)),
        "overall_matrix": matrix.round(6).tolist(),
        **matrix_power_summary(matrix=matrix, powers=[2, 3]),
        "signals": {
            "diagonal_dominant": bool(float(np.trace(matrix)) >= float(matrix.sum() - np.trace(matrix))),
            "p_2_to_2": float(matrix[2, 2]),
            "p_2_to_0": float(matrix[2, 0]),
            "p_0_to_2": float(matrix[0, 2]),
            "high_risk_persistence_stronger_than_fall": bool(matrix[2, 2] > matrix[2, 0]),
            "cross_level_jump_exists": bool(matrix[0, 2] > 0),
        },
    }
    save_json(k_step_path, k_step_payload)

    summary_payload = {
        "overall_matrix_path": str(overall_matrix_path.relative_to(REPO_DIR)),
        "district_matrix_path": str(district_matrix_path.relative_to(REPO_DIR)),
        "k_step_summary_path": str(k_step_path.relative_to(REPO_DIR)),
        **k_step_payload["signals"],
    }
    update_summary("markov_transition", summary_payload)
    LOGGER.info("Q3 Step 4 完成，Markov 转移结果已更新到输出目录。")

    print("Q3 Markov 转移分析完成。")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
