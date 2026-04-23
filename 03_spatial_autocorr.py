from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch


CURRENT_DIR = Path(__file__).resolve().parent
REPO_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from q3_utils import (
    LOGGER,
    OUTPUT_DIR,
    Q3_LISA_PANEL_PATH,
    build_node_aligned_values,
    compute_global_moran,
    compute_local_moran,
    ensure_q3_panel,
    ensure_spatial_weights,
    load_grid,
    save_geojson,
    save_json,
    setup_logging,
    update_summary,
)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="计算 Q3 年度 Moran's I 与 LISA。")
    parser.add_argument("--permutations", type=int, default=199, help="置换次数，默认 199。")
    parser.add_argument("--alpha", type=float, default=0.05, help="LISA 显著性阈值，默认 0.05。")
    return parser


def plot_moran_trend(report: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(report["year"], report["moran_i"], marker="o", linewidth=2.0, color="#b44d2d")
    ax.axhline(0.0, linestyle="--", linewidth=1.0, color="#555555")
    ax.set_title("Annual Moran's I Trend")
    ax.set_xlabel("Year")
    ax.set_ylabel("Moran's I")
    ax.grid(alpha=0.25, linestyle=":")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_lisa_map(latest_gdf: gpd.GeoDataFrame, output_path: Path) -> None:
    color_map = {
        "HH": "#bb3e03",
        "LL": "#3a86ff",
        "HL": "#ffb703",
        "LH": "#8ecae6",
        "NS": "#d9d9d9",
    }
    order = ["NS", "LL", "LH", "HL", "HH"]
    fig, ax = plt.subplots(figsize=(9, 9))
    for label in order:
        subset = latest_gdf.loc[latest_gdf["lisa_type"].fillna("NS") == label]
        if subset.empty:
            continue
        subset.plot(ax=ax, color=color_map[label], linewidth=0.02, edgecolor="white")
    ax.set_axis_off()
    ax.set_title("Q3 Latest-Year LISA Cluster Map")
    legend_handles = [Patch(facecolor=color_map[item], edgecolor="none", label=item) for item in order]
    ax.legend(handles=legend_handles, loc="lower left", frameon=True, title="LISA Type")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    setup_logging()
    args = build_argparser().parse_args()
    LOGGER.info("开始执行 Q3 Step 3：年度空间自相关分析。")
    panel, _, panel_meta = ensure_q3_panel()
    nodes, edges, weights_meta = ensure_spatial_weights()
    grid = load_grid()
    src_idx = edges["src_idx"].to_numpy(dtype=int)
    dst_idx = edges["dst_idx"].to_numpy(dtype=int)

    report_rows: list[dict[str, object]] = []
    lisa_frames: list[pd.DataFrame] = []
    years = sorted(pd.to_numeric(panel["year"], errors="coerce").dropna().astype(int).unique().tolist())

    for year in years:
        LOGGER.info("计算年度 Moran/LISA：year=%s", year)
        year_df = panel.loc[pd.to_numeric(panel["year"], errors="coerce").astype(int) == year].copy()
        values = build_node_aligned_values(panel_year=year_df, nodes=nodes, value_col="rvri")
        global_result = compute_global_moran(
            values=values,
            src_idx=src_idx,
            dst_idx=dst_idx,
            permutations=args.permutations,
            seed=20260423 + year,
        )
        local_result = compute_local_moran(
            values=values,
            src_idx=src_idx,
            dst_idx=dst_idx,
            permutations=args.permutations,
            alpha=args.alpha,
            seed=20260500 + year,
        )
        local_frame = pd.concat([nodes[["node_idx", "grid_id"]], local_result], axis=1)
        local_frame["year"] = year
        lisa_frames.append(local_frame)

        type_counts = local_frame["lisa_type"].value_counts()
        report_rows.append(
            {
                "year": year,
                "moran_i": global_result["moran_i"],
                "permutation_p_value": global_result["permutation_p_value"],
                "z_score": global_result["z_score"],
                "hh_count": int(type_counts.get("HH", 0)),
                "ll_count": int(type_counts.get("LL", 0)),
                "hl_count": int(type_counts.get("HL", 0)),
                "lh_count": int(type_counts.get("LH", 0)),
                "ns_count": int(type_counts.get("NS", 0)),
                "permutations": args.permutations,
            }
        )
        LOGGER.info(
            "年度 Moran/LISA 计算完成：year=%s, moran_i=%.4f, p=%.4f",
            year,
            global_result["moran_i"],
            global_result["permutation_p_value"],
        )

    report_df = pd.DataFrame(report_rows).sort_values("year")
    lisa_panel = pd.concat(lisa_frames, ignore_index=True)

    annual_report_path = OUTPUT_DIR / "annual_moran_report.csv"
    trend_plot_path = OUTPUT_DIR / "Q3_Moran_Trend.png"
    latest_geojson_path = OUTPUT_DIR / "lisa_cluster_latest.geojson"
    lisa_map_path = OUTPUT_DIR / "Q3_LISA_Map.png"

    report_df.to_csv(annual_report_path, index=False, encoding="utf-8-sig")
    lisa_panel.to_csv(Q3_LISA_PANEL_PATH, index=False, encoding="utf-8-sig")
    plot_moran_trend(report=report_df, output_path=trend_plot_path)

    latest_year = int(report_df["year"].max())
    latest_lisa = lisa_panel.loc[lisa_panel["year"] == latest_year].copy()
    latest_geo = grid.merge(latest_lisa, on="grid_id", how="left")
    save_geojson(latest_geo, latest_geojson_path)
    plot_lisa_map(latest_gdf=latest_geo, output_path=lisa_map_path)

    success_years = int(((report_df["moran_i"] > 0) & (report_df["permutation_p_value"] < 0.05)).sum())
    summary_payload = {
        "panel_input": panel_meta["input_path"],
        "weight_node_count": weights_meta["node_count"],
        "years": years,
        "significant_positive_years": success_years,
        "meets_moran_success_rule": bool(success_years >= 4),
        "latest_year": latest_year,
        "latest_year_metrics": report_df.loc[report_df["year"] == latest_year].iloc[0].to_dict(),
        "annual_report_path": str(annual_report_path.relative_to(REPO_DIR)),
        "lisa_panel_path": str(Q3_LISA_PANEL_PATH.relative_to(REPO_DIR)),
        "latest_geojson_path": str(latest_geojson_path.relative_to(REPO_DIR)),
        "lisa_map_path": str(lisa_map_path.relative_to(REPO_DIR)),
        "trend_plot_path": str(trend_plot_path.relative_to(REPO_DIR)),
    }

    save_json(OUTPUT_DIR / "q3_spatial_autocorr_summary.json", summary_payload)
    update_summary("spatial_autocorrelation", summary_payload)
    LOGGER.info("Q3 Step 3 完成，空间自相关结果已更新到输出目录。")

    print("Q3 空间自相关分析完成。")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
