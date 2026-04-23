from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


CURRENT_DIR = Path(__file__).resolve().parent
REPO_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from q3_utils import (
    LOGGER,
    OUTPUT_DIR,
    Q3_LISA_PANEL_PATH,
    Q3_SPATIAL_PANEL_PATH,
    attach_spatial_features,
    build_node_aligned_values,
    build_probability_geojson,
    compute_local_moran,
    ensure_q3_panel,
    ensure_spatial_weights,
    load_grid,
    save_json,
    setup_logging,
    update_summary,
)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="训练 Q3 下一年低风险转高风险预测模型。")
    parser.add_argument("--permutations", type=int, default=99, help="若需即时补算 LISA 时的置换次数。")
    parser.add_argument("--alpha", type=float, default=0.05, help="若需即时补算 LISA 时的显著性阈值。")
    return parser


def build_prediction_model(
    numeric_features: list[str],
    categorical_features: list[str],
) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_features,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical_features,
            ),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            (
                "model",
                LogisticRegression(
                    solver="liblinear",
                    penalty="l2",
                    C=0.3,
                    max_iter=1000,
                    random_state=20260423,
                ),
            ),
        ]
    )


def ensure_lisa_features(
    panel: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    permutations: int,
    alpha: float,
) -> pd.DataFrame:
    if Q3_LISA_PANEL_PATH.exists():
        LOGGER.info("复用现成的 LISA 面板缓存: %s", Q3_LISA_PANEL_PATH)
        return pd.read_csv(Q3_LISA_PANEL_PATH, low_memory=False)

    LOGGER.info("未检测到 LISA 面板缓存，开始即时补算。")
    src_idx = edges["src_idx"].to_numpy(dtype=int)
    dst_idx = edges["dst_idx"].to_numpy(dtype=int)
    frames: list[pd.DataFrame] = []
    years = sorted(pd.to_numeric(panel["year"], errors="coerce").dropna().astype(int).unique().tolist())
    for year in years:
        LOGGER.info("即时补算 LISA：year=%s", year)
        year_df = panel.loc[pd.to_numeric(panel["year"], errors="coerce").astype(int) == year].copy()
        values = build_node_aligned_values(panel_year=year_df, nodes=nodes, value_col="rvri")
        local_result = compute_local_moran(
            values=values,
            src_idx=src_idx,
            dst_idx=dst_idx,
            permutations=permutations,
            alpha=alpha,
            seed=20260600 + year,
        )
        frame = pd.concat([nodes[["grid_id"]], local_result[["lisa_type"]]], axis=1)
        frame["year"] = year
        frames.append(frame)
    lisa_df = pd.concat(frames, ignore_index=True)
    lisa_df.to_csv(Q3_LISA_PANEL_PATH, index=False, encoding="utf-8-sig")
    LOGGER.info("LISA 面板缓存已写出: %s", Q3_LISA_PANEL_PATH)
    return lisa_df


def ensure_spatial_panel(panel: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    if Q3_SPATIAL_PANEL_PATH.exists():
        LOGGER.info("复用现成的空间特征面板缓存: %s", Q3_SPATIAL_PANEL_PATH)
        return pd.read_csv(Q3_SPATIAL_PANEL_PATH, low_memory=False)
    LOGGER.info("未检测到空间特征面板缓存，开始重新生成。")
    enriched = attach_spatial_features(panel=panel, edges=edges)
    enriched.to_csv(Q3_SPATIAL_PANEL_PATH, index=False, encoding="utf-8-sig")
    LOGGER.info("空间特征面板缓存已写出: %s", Q3_SPATIAL_PANEL_PATH)
    return enriched


def plot_probability_map(prob_geo: gpd.GeoDataFrame, output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 9))
    prob_geo.plot(
        ax=ax,
        column="pred_probability",
        cmap="YlOrRd",
        linewidth=0.02,
        edgecolor="white",
        legend=True,
        legend_kwds={"label": "Predicted Probability"},
    )
    top_decile = prob_geo.loc[prob_geo["prob_rank_pct"] >= 0.9]
    if not top_decile.empty:
        top_decile.boundary.plot(ax=ax, color="#5f0f40", linewidth=0.35)
    ax.set_axis_off()
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def add_probability_ranks(table: pd.DataFrame) -> pd.DataFrame:
    ranked = table.sort_values("pred_probability", ascending=False).reset_index(drop=True)
    ranked["prob_rank_pct"] = 1.0 - (ranked.index / max(len(ranked) - 1, 1))
    ranked["top_decile_flag"] = (ranked["prob_rank_pct"] >= 0.9).astype(int)
    return ranked


def attach_state_boundary_features(feature_panel: pd.DataFrame) -> pd.DataFrame:
    state_summary = (
        feature_panel.groupby(["year", "risk_state"])["rvri"]
        .agg(["min", "max", "mean"])
        .reset_index()
    )
    low_state = state_summary.loc[state_summary["risk_state"] == 0, ["year", "max"]].rename(
        columns={"max": "rvri_max_state0"}
    )
    mid_state = state_summary.loc[state_summary["risk_state"] == 1, ["year", "min", "mean"]].rename(
        columns={
            "min": "rvri_min_state1",
            "mean": "rvri_mean_state1",
        }
    )
    enriched = feature_panel.merge(low_state, on="year", how="left").merge(mid_state, on="year", how="left")
    enriched["rvri_gap_to_mid_threshold"] = enriched["rvri_min_state1"] - enriched["rvri"]
    enriched["rvri_to_mid_mean_gap"] = enriched["rvri_mean_state1"] - enriched["rvri"]
    enriched["rvri_pct_within_low_band"] = enriched["rvri"] / enriched["rvri_max_state0"].replace(0, pd.NA)
    enriched["year_num"] = pd.to_numeric(enriched["year"], errors="coerce")
    return enriched


def summarize_top_decile(scored_df: pd.DataFrame, label_col: str | None = None) -> dict[str, float | int | None]:
    top_decile = scored_df.loc[scored_df["top_decile_flag"] == 1].copy()
    payload: dict[str, float | int | None] = {
        "top_decile_rows": int(len(top_decile)),
        "top_decile_edge_share": float(top_decile["is_edge_zone"].mean()) if not top_decile.empty else None,
        "top_decile_lh_share": float(top_decile["lisa_type"].eq("LH").mean()) if not top_decile.empty else None,
        "top_decile_high_context_share": float(top_decile["neighbor_env_level"].eq("high").mean()) if not top_decile.empty else None,
        "top_decile_mid_context_share": float(top_decile["neighbor_env_level"].eq("mid").mean()) if not top_decile.empty else None,
        "top_decile_mean_probability": float(top_decile["pred_probability"].mean()) if not top_decile.empty else None,
    }
    if label_col is not None:
        payload["top_decile_event_rate"] = float(top_decile[label_col].mean()) if not top_decile.empty else None
    return payload


def evaluate_time_split(
    model: Pipeline,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, float | int | bool | None | list[str] | str]]:
    if train_df["low_to_high_event"].nunique() < 2:
        raise RuntimeError("训练样本中缺少 0->2 正负两类事件，无法训练 Pooled Logistic 模型。")
    if test_df.empty:
        raise RuntimeError("未找到时间回测测试样本，无法评估预测模块。")

    X_train = train_df[feature_columns]
    y_train = train_df["low_to_high_event"].astype(int)
    X_test = test_df[feature_columns]
    y_test = test_df["low_to_high_event"].astype(int)

    model.fit(X_train, y_train)
    pred_probability = model.predict_proba(X_test)[:, 1]
    scored_test = test_df.copy()
    scored_test["pred_probability"] = pred_probability

    auc = float(roc_auc_score(y_test, pred_probability)) if y_test.nunique() > 1 else None
    ap = float(average_precision_score(y_test, pred_probability)) if y_test.nunique() > 1 else None
    brier = float(brier_score_loss(y_test, pred_probability))
    scored_test = add_probability_ranks(scored_test)
    top_n = max(1, int(len(scored_test) * 0.1))
    top_df = scored_test.head(top_n).copy()
    base_rate = float(y_test.mean())
    top_hit_rate = float(top_df["low_to_high_event"].mean())
    lift_at_10 = float(top_hit_rate / base_rate) if base_rate > 0 else None

    evaluation_payload: dict[str, float | int | bool | None | list[str] | str] = {
        "train_year_pairs": ["2019->2020", "2020->2021", "2021->2022"],
        "test_year_pair": "2022->2023",
        "train_rows": int(len(train_df)),
        "test_rows": int(len(scored_test)),
        "train_positive_rate": float(y_train.mean()),
        "test_positive_rate": base_rate,
        "roc_auc": auc,
        "average_precision": ap,
        "brier_score": brier,
        "top_10_percent_hit_rate": top_hit_rate,
        "lift_at_10_percent": lift_at_10,
        "meets_auc_rule": bool(auc is not None and auc >= 0.70),
        "meets_lift_rule": bool(lift_at_10 is not None and lift_at_10 >= 2.0),
    }
    evaluation_payload.update(summarize_top_decile(scored_test, label_col="low_to_high_event"))
    return scored_test, evaluation_payload


def extract_model_coefficients(model: Pipeline) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    feature_names = model.named_steps["preprocess"].get_feature_names_out()
    coefficients = model.named_steps["model"].coef_[0]
    coef_df = (
        pd.DataFrame({"feature": feature_names, "coefficient": coefficients})
        .sort_values("coefficient", ascending=False)
        .reset_index(drop=True)
    )
    return (
        coef_df.head(12).to_dict(orient="records"),
        coef_df.tail(12).sort_values("coefficient").to_dict(orient="records"),
    )


def main() -> None:
    setup_logging()
    args = build_argparser().parse_args()
    LOGGER.info("开始执行 Q3 Step 6：下一年低转高预测。")
    panel, transition, _ = ensure_q3_panel()
    nodes, edges, _ = ensure_spatial_weights()
    spatial_panel = ensure_spatial_panel(panel=panel, edges=edges)
    lisa_panel = ensure_lisa_features(
        panel=panel,
        nodes=nodes,
        edges=edges,
        permutations=args.permutations,
        alpha=args.alpha,
    )

    feature_panel = spatial_panel.merge(
        lisa_panel[["grid_id", "year", "lisa_type"]],
        on=["grid_id", "year"],
        how="left",
    )
    feature_panel["lisa_type"] = feature_panel["lisa_type"].fillna("NS")
    feature_panel["is_edge_zone"] = feature_panel["lisa_type"].isin(["HL", "LH"]).astype(int)
    feature_panel = attach_state_boundary_features(feature_panel)

    transition_model = transition.merge(
        feature_panel[
            [
                "grid_id",
                "year",
                "spatial_lag_rvri",
                "neighbor_high_ratio",
                "neighbor_count",
                "neighbor_env_level",
                "lisa_type",
                "is_edge_zone",
                "rvri_gap_to_mid_threshold",
                "rvri_to_mid_mean_gap",
                "rvri_pct_within_low_band",
                "year_num",
            ]
        ],
        on=["grid_id", "year"],
        how="left",
    )

    candidates = transition_model.loc[transition_model["risk_state"] == 0].copy()
    backtest_train_df = candidates.loc[candidates["year"].isin([2019, 2020, 2021])].copy()
    backtest_test_df = candidates.loc[candidates["year"] == 2022].copy()
    final_train_df = candidates.loc[candidates["year"].isin([2019, 2020, 2021, 2022])].copy()

    prediction_base_year = int(pd.to_numeric(panel["year"], errors="coerce").max())
    prediction_target_year = prediction_base_year + 1
    scoring_df = feature_panel.loc[
        feature_panel["year"].eq(prediction_base_year) & feature_panel["risk_state"].eq(0)
    ].copy()
    if scoring_df.empty:
        raise RuntimeError(f"未找到 {prediction_base_year} 年的低风险候选格网，无法输出真实下一年预测。")

    LOGGER.info(
        "低转高候选样本已就绪: backtest_train_rows=%s, backtest_test_rows=%s, final_train_rows=%s, scoring_rows=%s",
        len(backtest_train_df),
        len(backtest_test_df),
        len(final_train_df),
        len(scoring_df),
    )

    numeric_features = [
        "rvri",
        "mismatch_gap",
        "ndbi",
        "light",
        "ndvi",
        "delta_rvri",
        "delta_mismatch_gap",
        "spatial_lag_rvri",
        "neighbor_high_ratio",
        "neighbor_count",
        "is_edge_zone",
        "rvri_gap_to_mid_threshold",
        "rvri_to_mid_mean_gap",
        "rvri_pct_within_low_band",
        "year_num",
    ]
    categorical_features = ["district_name", "lisa_type", "neighbor_env_level"]
    feature_columns = numeric_features + categorical_features

    backtest_model = build_prediction_model(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
    )
    _, backtest_payload = evaluate_time_split(
        model=backtest_model,
        train_df=backtest_train_df,
        test_df=backtest_test_df,
        feature_columns=feature_columns,
    )
    LOGGER.info(
        "时间回测完成: auc=%s, lift_at_10=%s, top_hit_rate=%s",
        backtest_payload["roc_auc"],
        backtest_payload["lift_at_10_percent"],
        backtest_payload["top_10_percent_hit_rate"],
    )

    final_model = build_prediction_model(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
    )
    final_X = final_train_df[feature_columns]
    final_y = final_train_df["low_to_high_event"].astype(int)
    final_model.fit(final_X, final_y)
    LOGGER.info(
        "最终预测模型训练完成，将基于 %s 年截面输出 %s 年风险概率。",
        prediction_base_year,
        prediction_target_year,
    )

    scoring_df["base_year"] = prediction_base_year
    scoring_df["target_year"] = prediction_target_year
    scoring_df["pred_probability"] = final_model.predict_proba(scoring_df[feature_columns])[:, 1]
    scoring_df = add_probability_ranks(scoring_df)

    top_positive_features, top_negative_features = extract_model_coefficients(final_model)

    output_columns = [
        "grid_id",
        "district_name",
        "base_year",
        "target_year",
        "year",
        "risk_state",
        "rvri",
        "mismatch_gap",
        "delta_rvri",
        "delta_mismatch_gap",
        "spatial_lag_rvri",
        "neighbor_high_ratio",
        "neighbor_env_level",
        "lisa_type",
        "is_edge_zone",
        "neighbor_count",
        "pred_probability",
        "prob_rank_pct",
        "top_decile_flag",
    ]
    output_csv_path = OUTPUT_DIR / "low_to_high_prob_next_year.csv"
    output_geojson_path = OUTPUT_DIR / "low_to_high_prob_next_year.geojson"
    output_map_path = OUTPUT_DIR / "Q3_LowToHigh_Risk_Map.png"
    report_path = OUTPUT_DIR / "q3_prediction_report.json"

    result_table = scoring_df[output_columns].copy()
    result_table.to_csv(output_csv_path, index=False, encoding="utf-8-sig")

    grid = load_grid()
    prob_geo = build_probability_geojson(grid=grid, table=result_table, path=output_geojson_path)
    plot_probability_map(
        prob_geo=prob_geo,
        output_path=output_map_path,
        title=f"Predicted {prediction_target_year} Low-to-High Risk (from {prediction_base_year} Baseline)",
    )

    top_n_prediction = max(1, int(len(result_table) * 0.1))
    top_prediction = result_table.head(top_n_prediction).copy()
    top_decile_threshold = float(top_prediction["pred_probability"].min()) if not top_prediction.empty else None
    future_top_decile_summary = summarize_top_decile(result_table)

    report_payload = {
        "model_spec": {
            "model_family": "pooled_logistic_regression",
            "class_weight": None,
            "numeric_features": numeric_features,
            "categorical_features": categorical_features,
        },
        "backtest_evaluation": backtest_payload,
        "final_training_scope": {
            "train_year_pairs": ["2019->2020", "2020->2021", "2021->2022", "2022->2023"],
            "train_rows": int(len(final_train_df)),
            "train_positive_rate": float(final_y.mean()),
        },
        "future_prediction": {
            "prediction_base_year": prediction_base_year,
            "predicted_target_year": prediction_target_year,
            "scored_rows": int(len(result_table)),
            "mean_pred_probability": float(result_table["pred_probability"].mean()),
            "top_decile_threshold": top_decile_threshold,
            "top_decile_rows": int(len(top_prediction)),
            **future_top_decile_summary,
        },
        "top_positive_features": top_positive_features,
        "top_negative_features": top_negative_features,
        "output_csv_path": str(output_csv_path.relative_to(REPO_DIR)),
        "output_geojson_path": str(output_geojson_path.relative_to(REPO_DIR)),
        "output_map_path": str(output_map_path.relative_to(REPO_DIR)),
    }
    save_json(report_path, report_payload)

    summary_payload = {
        "prediction_report_path": str(report_path.relative_to(REPO_DIR)),
        "output_csv_path": str(output_csv_path.relative_to(REPO_DIR)),
        "output_geojson_path": str(output_geojson_path.relative_to(REPO_DIR)),
        "output_map_path": str(output_map_path.relative_to(REPO_DIR)),
        "prediction_base_year": prediction_base_year,
        "predicted_target_year": prediction_target_year,
        "scored_rows": int(len(result_table)),
        "roc_auc": backtest_payload["roc_auc"],
        "lift_at_10_percent": backtest_payload["lift_at_10_percent"],
        "top_10_percent_hit_rate": backtest_payload["top_10_percent_hit_rate"],
        "meets_auc_rule": backtest_payload["meets_auc_rule"],
        "meets_lift_rule": backtest_payload["meets_lift_rule"],
    }
    update_summary("low_to_high_prediction", summary_payload)
    LOGGER.info("Q3 Step 6 完成，预测结果已更新到输出目录。")

    print("Q3 下一年低转高预测完成。")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
