from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


CURRENT_DIR = Path(__file__).resolve().parent
REPO_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from q3_utils import (
    LOGGER,
    OUTPUT_DIR,
    Q3_SPATIAL_PANEL_PATH,
    attach_spatial_features,
    build_transition_matrix,
    ensure_q3_panel,
    ensure_spatial_weights,
    save_json,
    setup_logging,
    update_summary,
)


def build_argparser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="计算 Q3 Spatial Markov 及空间扩散对比。")


def plot_spatial_markov_comparison(compare_df: pd.DataFrame, output_path: Path) -> None:
    pivot = compare_df.pivot(index="neighbor_env_level", columns="transition_label", values="probability").reindex(
        ["low", "mid", "high"]
    )
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    x = range(len(pivot.index))
    width = 0.32
    ax.bar([i - width / 2 for i in x], pivot["0->2"], width=width, label="0->2", color="#457b9d")
    ax.bar([i + width / 2 for i in x], pivot["1->2"], width=width, label="1->2", color="#d62828")
    ax.set_xticks(list(x), pivot.index.tolist())
    ax.set_xlabel("Neighbor Risk Context")
    ax.set_ylabel("Transition Probability")
    ax.grid(axis="y", alpha=0.2, linestyle=":")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def main() -> None:
    setup_logging()
    build_argparser().parse_args()
    LOGGER.info("开始执行 Q3 Step 5：Spatial Markov 分析。")
    panel, transition, _ = ensure_q3_panel()
    _, edges, _ = ensure_spatial_weights()

    panel_domain = panel.loc[panel["in_analysis_domain"].fillna(False)].copy()
    transition_domain = transition.loc[transition["in_analysis_domain"].fillna(False)].copy()
    panel_spatial = attach_spatial_features(panel=panel_domain, edges=edges)
    panel_spatial.to_csv(Q3_SPATIAL_PANEL_PATH, index=False, encoding="utf-8-sig")

    transition_spatial = transition_domain.merge(
        panel_spatial[
            ["grid_id", "year", "spatial_lag_rvri", "neighbor_high_ratio", "neighbor_count", "neighbor_env_level"]
        ],
        on=["grid_id", "year"],
        how="left",
    )

    spatial_matrix = build_transition_matrix(
        transition_df=transition_spatial.dropna(subset=["neighbor_env_level"]).copy(),
        group_cols=["neighbor_env_level"],
    )
    spatial_matrix_path = OUTPUT_DIR / "spatial_markov_matrix.csv"
    comparison_plot_path = OUTPUT_DIR / "spatial_markov_comparison.png"
    diffusion_summary_path = OUTPUT_DIR / "spatial_diffusion_summary.json"

    spatial_matrix.to_csv(spatial_matrix_path, index=False, encoding="utf-8-sig")

    compare_df = (
        spatial_matrix.loc[
            spatial_matrix["risk_state"].isin([0, 1]) & spatial_matrix["next_risk_state"].eq(2),
            ["neighbor_env_level", "risk_state", "probability"],
        ]
        .copy()
    )
    compare_df["transition_label"] = compare_df["risk_state"].astype(str) + "->2"
    plot_spatial_markov_comparison(compare_df=compare_df, output_path=comparison_plot_path)

    compare_pivot = compare_df.pivot(index="neighbor_env_level", columns="transition_label", values="probability").reindex(
        ["low", "mid", "high"]
    )
    summary_payload = {
        "panel_spatial_path": str(Q3_SPATIAL_PANEL_PATH.relative_to(REPO_DIR)),
        "spatial_markov_matrix_path": str(spatial_matrix_path.relative_to(REPO_DIR)),
        "comparison_plot_path": str(comparison_plot_path.relative_to(REPO_DIR)),
        "analysis_domain_rows": int(len(panel_domain)),
        "analysis_domain_transition_rows": int(len(transition_domain)),
        "high_vs_low": {
            "p_0_to_2_high": float(compare_pivot.loc["high", "0->2"]),
            "p_0_to_2_low": float(compare_pivot.loc["low", "0->2"]),
            "p_1_to_2_high": float(compare_pivot.loc["high", "1->2"]),
            "p_1_to_2_low": float(compare_pivot.loc["low", "1->2"]),
            "high_context_stronger_for_0_to_2": bool(compare_pivot.loc["high", "0->2"] > compare_pivot.loc["low", "0->2"]),
            "high_context_not_weaker_for_1_to_2": bool(compare_pivot.loc["high", "1->2"] >= compare_pivot.loc["low", "1->2"]),
        },
    }
    save_json(diffusion_summary_path, summary_payload)
    summary_payload["diffusion_summary_path"] = str(diffusion_summary_path.relative_to(REPO_DIR))
    update_summary("spatial_markov", summary_payload)
    LOGGER.info("Q3 Step 5 完成，Spatial Markov 结果已更新到输出目录。")

    print("Q3 Spatial Markov 分析完成。")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
