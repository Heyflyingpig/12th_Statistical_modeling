from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from analysis_domain import (
    ANALYSIS_DOMAIN_NAME,
    attach_unified_analysis_domain,
    summarize_unified_analysis_domain,
)

Q1_DIR = ROOT_DIR / "Q1"
Q3_DIR = ROOT_DIR / "Q3"
OUTPUT_DIR = Q3_DIR / "output"

Q3_PANEL_PATH = OUTPUT_DIR / "q3_panel.csv"
Q3_TRANSITION_PATH = OUTPUT_DIR / "q3_transition_panel.csv"
Q3_LISA_PANEL_PATH = OUTPUT_DIR / "q3_lisa_panel.csv"
Q3_SPATIAL_PANEL_PATH = OUTPUT_DIR / "q3_panel_spatial.csv"
Q3_SUMMARY_PATH = OUTPUT_DIR / "q3_summary.json"

SPATIAL_WEIGHT_NODES_PATH = OUTPUT_DIR / "spatial_weight_nodes.csv"
SPATIAL_WEIGHT_EDGES_PATH = OUTPUT_DIR / "spatial_weights_edges.csv.gz"
SPATIAL_WEIGHT_SUMMARY_PATH = OUTPUT_DIR / "spatial_weights_summary.json"

DEFAULT_ANNUAL_INPUTS = [
    Q1_DIR / "output" / "Shaoguan_RVRI_Q1_Validated.csv",
    Q1_DIR / "output1" / "Shaoguan_RVRI_Q1_Validated.csv",
    Q1_DIR / "output_v1" / "Shaoguan_RVRI_Q1_Validated.csv",
    Q1_DIR / "output_v2" / "Shaoguan_RVRI_Q1_Validated.csv",
]
DEFAULT_QUARTERLY_FALLBACKS = [
    Q1_DIR / "output_v1" / "Shaoguan_RVRI_Long_Panel_Final.csv",
]
DEFAULT_GRID_PATH = Q1_DIR / "data" / "scientific_grid_500m.geojson"

LOGGER = logging.getLogger("q3")


def setup_logging(level: str = "INFO") -> logging.Logger:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    LOGGER.setLevel(numeric_level)
    return LOGGER


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def save_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_output_dir()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def update_summary(section: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_output_dir()
    summary: dict[str, Any]
    if Q3_SUMMARY_PATH.exists():
        summary = read_json(Q3_SUMMARY_PATH)
    else:
        summary = {}
    summary[section] = payload
    save_json(Q3_SUMMARY_PATH, summary)
    return summary


def resolve_q1_input(input_path: str | None = None) -> tuple[Path, str]:
    if input_path:
        path = Path(input_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists():
            raise FileNotFoundError(f"未找到指定的 Q1 输入文件: {path}")
        mode = "annual_validated" if "Validated" in path.name else "quarterly_fallback"
        LOGGER.info("使用用户指定的 Q1 输入文件: %s (%s)", path, mode)
        return path, mode

    for path in DEFAULT_ANNUAL_INPUTS:
        if path.exists():
            LOGGER.info("自动识别到年度版 Q1 输入文件: %s", path)
            return path, "annual_validated"
    for path in DEFAULT_QUARTERLY_FALLBACKS:
        if path.exists():
            LOGGER.info("年度主表缺失，回退使用季度兼容输入: %s", path)
            return path, "quarterly_fallback"
    raise FileNotFoundError(
        "未找到可用的 Q1 主结果表。请检查 Q1/output、Q1/output1 或 Q1/output_v1。"
    )


def _rank_to_three_states(series: pd.Series) -> pd.Series:
    # 这里用分位排序而不是直接 qcut，避免大量重复值导致分箱失败。
    valid = series.dropna()
    result = pd.Series(pd.NA, index=series.index, dtype="Int64")
    if valid.empty:
        return result
    pct = valid.rank(method="average", pct=True)
    state = pd.Series(np.select(
        [pct <= 1 / 3, pct <= 2 / 3],
        [0, 1],
        default=2,
    ), index=valid.index)
    result.loc[valid.index] = state.astype("Int64")
    return result


def _normalize_annual_panel(raw: pd.DataFrame, source_path: Path) -> pd.DataFrame:
    panel = raw.copy()
    rename_map = {"source_year": "year"}
    panel = panel.rename(columns=rename_map)
    required_cols = {
        "grid_id",
        "year",
        "district_name",
        "ndbi",
        "ndvi",
        "light",
        "rvri",
        "risk_state",
        "mismatch_gap",
    }
    missing = required_cols - set(panel.columns)
    if missing:
        raise ValueError(f"年度主表缺少必要字段: {sorted(missing)}")

    panel = panel.loc[:, sorted(required_cols | {"time_grain", "temporal_grain", "quality_flag"} & set(panel.columns))]
    panel["grid_id"] = panel["grid_id"].astype(str)
    panel["district_name"] = panel["district_name"].fillna("未知区县").astype(str).str.strip()
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    numeric_cols = ["ndbi", "ndvi", "light", "rvri", "mismatch_gap", "risk_state"]
    for col in numeric_cols:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    panel["risk_state"] = panel["risk_state"].round().astype("Int64")
    panel = panel.dropna(subset=["grid_id", "year", "rvri", "risk_state"]).copy()
    panel["year"] = panel["year"].astype(int)
    panel["risk_state"] = panel["risk_state"].astype(int)
    panel["source_mode"] = "annual_validated"
    panel["source_path"] = str(source_path.relative_to(ROOT_DIR))
    panel = panel.sort_values(["grid_id", "year"]).drop_duplicates(["grid_id", "year"])
    LOGGER.info("年度主表标准化完成: rows=%s, grids=%s, years=%s", len(panel), panel["grid_id"].nunique(), panel["year"].nunique())
    return panel


def _normalize_quarterly_panel(raw: pd.DataFrame, source_path: Path) -> pd.DataFrame:
    panel = raw.copy()
    required_cols = {
        "grid_id",
        "time",
        "district_name",
        "ndbi",
        "ndvi",
        "light",
        "rvri",
        "mismatch_gap",
    }
    missing = required_cols - set(panel.columns)
    if missing:
        raise ValueError(f"季度回退表缺少必要字段: {sorted(missing)}")

    panel["grid_id"] = panel["grid_id"].astype(str)
    panel["district_name"] = panel["district_name"].fillna("未知区县").astype(str).str.strip()
    panel["year"] = panel["time"].astype(str).str.extract(r"(\d{4})")[0]
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    for col in ["ndbi", "ndvi", "light", "rvri", "mismatch_gap"]:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")

    annual = (
        panel.dropna(subset=["grid_id", "year"])
        .groupby(["grid_id", "year"], as_index=False)
        .agg(
            district_name=("district_name", "first"),
            ndbi=("ndbi", "mean"),
            ndvi=("ndvi", "mean"),
            light=("light", "mean"),
            rvri=("rvri", "mean"),
            mismatch_gap=("mismatch_gap", "mean"),
        )
    )
    annual["year"] = annual["year"].astype(int)
    annual["risk_state"] = annual.groupby("year")["rvri"].transform(_rank_to_three_states).astype(int)
    annual["source_mode"] = "quarterly_fallback"
    annual["source_path"] = str(source_path.relative_to(ROOT_DIR))
    annual = annual.sort_values(["grid_id", "year"]).drop_duplicates(["grid_id", "year"])
    LOGGER.info("季度兼容表按年度聚合完成: rows=%s, grids=%s, years=%s", len(annual), annual["grid_id"].nunique(), annual["year"].nunique())
    return annual


def load_q1_panel(input_path: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    path, mode = resolve_q1_input(input_path=input_path)
    if mode == "annual_validated":
        allowed_cols = {
            "grid_id",
            "source_year",
            "district_name",
            "ndbi",
            "ndvi",
            "light",
            "rvri",
            "risk_state",
            "mismatch_gap",
            "time_grain",
            "temporal_grain",
            "quality_flag",
        }
    else:
        allowed_cols = {
            "grid_id",
            "time",
            "district_name",
            "ndbi",
            "ndvi",
            "light",
            "rvri",
            "mismatch_gap",
        }
    LOGGER.info("开始读取 Q1 主结果表: %s", path)
    raw = pd.read_csv(path, low_memory=False, usecols=lambda col: col in allowed_cols)
    LOGGER.info("Q1 主结果表读取完成: raw_rows=%s, columns=%s", len(raw), list(raw.columns))
    if mode == "annual_validated":
        panel = _normalize_annual_panel(raw=raw, source_path=path)
    else:
        panel = _normalize_quarterly_panel(raw=raw, source_path=path)

    metadata = {
        "input_path": str(path.relative_to(ROOT_DIR)),
        "input_mode": mode,
        "rows": int(len(panel)),
        "grid_count": int(panel["grid_id"].nunique()),
        "year_count": int(panel["year"].nunique()),
        "years": [int(x) for x in sorted(panel["year"].unique().tolist())],
    }
    LOGGER.info("Q1 面板加载完成: %s", metadata)
    return panel, metadata


def prepare_q3_panel(input_path: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    LOGGER.info("开始准备 Q3 年度面板。")
    panel, metadata = load_q1_panel(input_path=input_path)
    panel = panel.sort_values(["grid_id", "year"]).drop_duplicates(["grid_id", "year"])
    panel = attach_unified_analysis_domain(panel, year_col="year")

    # 用上一年差分补足趋势特征，首年无法计算时记为 0，便于后续模型直接使用。
    panel["delta_rvri"] = panel.groupby("grid_id")["rvri"].diff().fillna(0.0)
    panel["delta_mismatch_gap"] = panel.groupby("grid_id")["mismatch_gap"].diff().fillna(0.0)
    panel["next_year"] = panel.groupby("grid_id")["year"].shift(-1)
    panel["next_risk_state"] = panel.groupby("grid_id")["risk_state"].shift(-1)
    panel["is_adjacent_transition"] = panel["next_year"].eq(panel["year"] + 1)

    transition = panel.loc[panel["is_adjacent_transition"]].copy()
    transition["next_year"] = transition["next_year"].astype(int)
    transition["next_risk_state"] = transition["next_risk_state"].astype(int)
    transition["transition_label"] = (
        transition["risk_state"].astype(str) + "->" + transition["next_risk_state"].astype(str)
    )
    transition["low_to_high_event"] = (
        (transition["risk_state"] == 0) & (transition["next_risk_state"] == 2)
    ).astype(int)

    metadata.update(
        {
            "prepared_rows": int(len(panel)),
            "prepared_grid_count": int(panel["grid_id"].nunique()),
            "analysis_domain": summarize_unified_analysis_domain(panel, year_col="year"),
            "transition_rows": int(len(transition)),
            "transition_year_pairs": sorted(
                transition[["year", "next_year"]]
                .drop_duplicates()
                .astype(int)
                .astype(str)
                .agg("->".join, axis=1)
                .tolist()
            ),
        }
    )
    LOGGER.info(
        "Q3 年度面板准备完成: rows=%s, transitions=%s, year_pairs=%s",
        len(panel),
        len(transition),
        metadata["transition_year_pairs"],
    )
    return panel, transition, metadata


def save_q3_panel_outputs(
    panel: pd.DataFrame,
    transition: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    ensure_output_dir()
    panel.to_csv(Q3_PANEL_PATH, index=False, encoding="utf-8-sig")
    transition.to_csv(Q3_TRANSITION_PATH, index=False, encoding="utf-8-sig")
    save_json(OUTPUT_DIR / "q3_panel_metadata.json", metadata)
    LOGGER.info("Q3 年度面板已写出: %s, %s", Q3_PANEL_PATH, Q3_TRANSITION_PATH)


def ensure_q3_panel(input_path: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    metadata_path = OUTPUT_DIR / "q3_panel_metadata.json"
    if Q3_PANEL_PATH.exists() and Q3_TRANSITION_PATH.exists() and metadata_path.exists():
        LOGGER.info("检测到现成的 Q3 面板缓存，直接复用。")
        panel = pd.read_csv(Q3_PANEL_PATH, low_memory=False)
        transition = pd.read_csv(Q3_TRANSITION_PATH, low_memory=False)
        metadata = read_json(metadata_path)
        if "in_analysis_domain" not in panel.columns:
            LOGGER.info("Q3 面板缓存缺少统一分析域字段，开始补充。")
            panel = attach_unified_analysis_domain(panel, year_col="year")
            adjacent_mask = panel["is_adjacent_transition"].eq(True) | panel["is_adjacent_transition"].astype(str).str.lower().eq("true")
            transition = panel.loc[adjacent_mask].copy()
            transition["next_year"] = transition["next_year"].astype(int)
            transition["next_risk_state"] = transition["next_risk_state"].astype(int)
            transition["transition_label"] = (
                transition["risk_state"].astype(str) + "->" + transition["next_risk_state"].astype(str)
            )
            transition["low_to_high_event"] = (
                (transition["risk_state"] == 0) & (transition["next_risk_state"] == 2)
            ).astype(int)
            metadata["analysis_domain"] = summarize_unified_analysis_domain(panel, year_col="year")
            save_q3_panel_outputs(panel=panel, transition=transition, metadata=metadata)
        return panel, transition, metadata
    LOGGER.info("未找到完整的 Q3 面板缓存，开始重新生成。")
    panel, transition, metadata = prepare_q3_panel(input_path=input_path)
    save_q3_panel_outputs(panel=panel, transition=transition, metadata=metadata)
    return panel, transition, metadata


def _representative_center(geometry: dict[str, Any]) -> tuple[float, float]:
    coords = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        ring = np.asarray(coords[0], dtype=float)
    elif geometry["type"] == "MultiPolygon":
        ring = np.asarray(coords[0][0], dtype=float)
    else:
        point = np.asarray(coords[:2], dtype=float)
        return float(point[0]), float(point[1])
    center = ring.mean(axis=0)
    return float(center[0]), float(center[1])


def _build_affine_grid_frame(features: list[dict[str, Any]]) -> pd.DataFrame:
    origin_feature = min(features, key=lambda feature: sum(feature["geometry"]["coordinates"][0][0]))
    ring = origin_feature["geometry"]["coordinates"][0]
    origin = np.array(ring[0], dtype=float)
    v_col = np.array(ring[1], dtype=float) - origin
    v_row = np.array(ring[3], dtype=float) - origin
    matrix_inv = np.linalg.inv(np.column_stack([v_col, v_row]))

    rows: list[dict[str, Any]] = []
    for feature in features:
        geometry = feature["geometry"]
        props = feature.get("properties", {})
        if geometry["type"] == "Polygon":
            anchor = np.array(geometry["coordinates"][0][0], dtype=float)
        elif geometry["type"] == "MultiPolygon":
            anchor = np.array(geometry["coordinates"][0][0][0], dtype=float)
        else:
            continue
        col, row = np.rint(matrix_inv @ (anchor - origin)).astype(int)
        cx, cy = _representative_center(geometry)
        rows.append(
            {
                "grid_id": str(props["grid_id"]),
                "district": props.get("district"),
                "col": int(col),
                "row": int(row),
                "cx": cx,
                "cy": cy,
                "geometry": geometry,
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["grid_id"]).reset_index(drop=True)


def load_grid(grid_path: str | None = None) -> pd.DataFrame:
    path = Path(grid_path) if grid_path else DEFAULT_GRID_PATH
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"未找到格网文件: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    grid = _build_affine_grid_frame(data["features"])
    if "grid_id" not in grid.columns:
        raise ValueError("scientific_grid_500m.geojson 缺少 grid_id 字段。")
    grid = grid.copy()
    grid["grid_id"] = grid["grid_id"].astype(str)
    grid = grid.drop_duplicates(subset=["grid_id"]).reset_index(drop=True)
    LOGGER.info("格网读取完成: path=%s, rows=%s", path, len(grid))
    return grid


def build_spatial_weights(
    grid: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    # 500m 规则格网可直接用仿射行列号构造 Queen 邻接，避免依赖额外 GIS 库。
    LOGGER.info("开始构建空间邻接权重: grid_rows=%s", len(grid))
    coord_to_idx = {
        (int(row.col), int(row.row)): idx
        for idx, row in enumerate(grid[["col", "row"]].itertuples(index=False))
    }
    src_idx: list[int] = []
    dst_idx: list[int] = []
    for idx, row in enumerate(grid[["col", "row"]].itertuples(index=False)):
        for d_col in (-1, 0, 1):
            for d_row in (-1, 0, 1):
                if d_col == 0 and d_row == 0:
                    continue
                neighbor = coord_to_idx.get((int(row.col) + d_col, int(row.row) + d_row))
                if neighbor is not None:
                    src_idx.append(idx)
                    dst_idx.append(neighbor)
    grid_ids = grid["grid_id"].to_numpy()

    edges = pd.DataFrame(
        {
            "src_idx": np.asarray(src_idx, dtype=np.int32),
            "dst_idx": np.asarray(dst_idx, dtype=np.int32),
            "src_grid_id": grid_ids[np.asarray(src_idx, dtype=np.int32)],
            "dst_grid_id": grid_ids[np.asarray(dst_idx, dtype=np.int32)],
        }
    ).drop_duplicates(ignore_index=True)

    nodes = pd.DataFrame(
        {
            "node_idx": np.arange(len(grid), dtype=np.int32),
            "grid_id": grid["grid_id"].astype(str).to_numpy(),
        }
    )

    degree = edges.groupby("src_idx").size()
    summary = {
        "node_count": int(len(nodes)),
        "directed_edge_count": int(len(edges)),
        "undirected_edge_count_estimate": int(len(edges) // 2),
        "min_degree": int(degree.min()) if not degree.empty else 0,
        "max_degree": int(degree.max()) if not degree.empty else 0,
        "mean_degree": float(degree.mean()) if not degree.empty else 0.0,
        "grid_path": str(DEFAULT_GRID_PATH.relative_to(ROOT_DIR)),
    }
    LOGGER.info("空间邻接权重构建完成: %s", summary)
    return nodes, edges, summary


def save_spatial_weights_outputs(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    ensure_output_dir()
    nodes.to_csv(SPATIAL_WEIGHT_NODES_PATH, index=False, encoding="utf-8-sig")
    edges.to_csv(SPATIAL_WEIGHT_EDGES_PATH, index=False, encoding="utf-8-sig", compression="gzip")
    save_json(SPATIAL_WEIGHT_SUMMARY_PATH, summary)
    LOGGER.info("空间权重文件已写出: %s, %s", SPATIAL_WEIGHT_NODES_PATH, SPATIAL_WEIGHT_EDGES_PATH)


def ensure_spatial_weights(
    grid_path: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if (
        SPATIAL_WEIGHT_NODES_PATH.exists()
        and SPATIAL_WEIGHT_EDGES_PATH.exists()
        and SPATIAL_WEIGHT_SUMMARY_PATH.exists()
    ):
        LOGGER.info("检测到现成的空间权重缓存，直接复用。")
        nodes = pd.read_csv(SPATIAL_WEIGHT_NODES_PATH)
        edges = pd.read_csv(SPATIAL_WEIGHT_EDGES_PATH, compression="gzip")
        summary = read_json(SPATIAL_WEIGHT_SUMMARY_PATH)
        return nodes, edges, summary

    LOGGER.info("未找到完整的空间权重缓存，开始重新生成。")
    grid = load_grid(grid_path=grid_path)
    nodes, edges, summary = build_spatial_weights(grid=grid)
    save_spatial_weights_outputs(nodes=nodes, edges=edges, summary=summary)
    return nodes, edges, summary


def build_node_aligned_values(
    panel_year: pd.DataFrame,
    nodes: pd.DataFrame,
    value_col: str,
    fill_strategy: str = "mean",
) -> np.ndarray:
    merged = nodes.merge(panel_year[["grid_id", value_col]], on="grid_id", how="left")
    values = merged[value_col].to_numpy(dtype=float)
    if np.isnan(values).any():
        if fill_strategy == "mean":
            fill_value = float(np.nanmean(values))
        else:
            fill_value = 0.0
        values = np.where(np.isnan(values), fill_value, values)
    return values


def filter_nodes_edges_to_domain(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    domain_grid_ids: pd.Series | list[str] | set[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    domain_ids = {str(grid_id) for grid_id in domain_grid_ids}
    domain_nodes = nodes[nodes["grid_id"].astype(str).isin(domain_ids)].copy()
    domain_nodes = domain_nodes.sort_values("node_idx").reset_index(drop=True)
    old_to_new = {int(old_idx): int(new_idx) for new_idx, old_idx in enumerate(domain_nodes["node_idx"])}
    domain_edges = edges[
        edges["src_idx"].astype(int).isin(old_to_new)
        & edges["dst_idx"].astype(int).isin(old_to_new)
    ].copy()
    domain_edges["src_idx"] = domain_edges["src_idx"].astype(int).map(old_to_new).astype(np.int32)
    domain_edges["dst_idx"] = domain_edges["dst_idx"].astype(int).map(old_to_new).astype(np.int32)
    domain_nodes["node_idx"] = np.arange(len(domain_nodes), dtype=np.int32)
    degree = domain_edges.groupby("src_idx").size()
    summary = {
        "domain_name": ANALYSIS_DOMAIN_NAME,
        "node_count": int(len(domain_nodes)),
        "directed_edge_count": int(len(domain_edges)),
        "undirected_edge_count_estimate": int(len(domain_edges) // 2),
        "min_degree": int(degree.min()) if not degree.empty else 0,
        "max_degree": int(degree.max()) if not degree.empty else 0,
        "mean_degree": float(degree.mean()) if not degree.empty else 0.0,
    }
    return domain_nodes, domain_edges, summary


def compute_row_standardized_lag(
    values: np.ndarray,
    src_idx: np.ndarray,
    dst_idx: np.ndarray,
    node_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    degree = np.bincount(src_idx, minlength=node_count).astype(float)
    neighbor_sum = np.bincount(src_idx, weights=values[dst_idx], minlength=node_count)
    lag = np.divide(
        neighbor_sum,
        degree,
        out=np.zeros(node_count, dtype=float),
        where=degree > 0,
    )
    return lag, degree


def compute_global_moran(
    values: np.ndarray,
    src_idx: np.ndarray,
    dst_idx: np.ndarray,
    permutations: int = 199,
    seed: int = 20260423,
) -> dict[str, Any]:
    values = np.asarray(values, dtype=float)
    node_count = len(values)
    centered = values - values.mean()
    lag, degree = compute_row_standardized_lag(
        values=centered,
        src_idx=src_idx,
        dst_idx=dst_idx,
        node_count=node_count,
    )
    non_island = degree > 0
    s0 = float(non_island.sum())
    denominator = float(np.dot(centered, centered))
    if denominator == 0 or s0 == 0:
        return {
            "moran_i": np.nan,
            "permutation_p_value": np.nan,
            "z_score": np.nan,
            "permutations": permutations,
        }

    observed = float((node_count / s0) * np.dot(centered[non_island], lag[non_island]) / denominator)
    rng = np.random.default_rng(seed)
    simulated = np.empty(permutations, dtype=float)
    for i in range(permutations):
        permuted = centered.copy()
        rng.shuffle(permuted)
        lag_perm, _ = compute_row_standardized_lag(
            values=permuted,
            src_idx=src_idx,
            dst_idx=dst_idx,
            node_count=node_count,
        )
        simulated[i] = float((node_count / s0) * np.dot(permuted[non_island], lag_perm[non_island]) / denominator)

    sim_mean = float(simulated.mean())
    sim_std = float(simulated.std(ddof=1))
    p_value = float((np.sum(np.abs(simulated) >= abs(observed)) + 1) / (permutations + 1))
    z_score = float((observed - sim_mean) / sim_std) if sim_std > 0 else np.nan
    return {
        "moran_i": observed,
        "permutation_p_value": p_value,
        "z_score": z_score,
        "permutations": permutations,
        "simulation_mean": sim_mean,
        "simulation_std": sim_std,
    }


def compute_local_moran(
    values: np.ndarray,
    src_idx: np.ndarray,
    dst_idx: np.ndarray,
    permutations: int = 199,
    alpha: float = 0.05,
    seed: int = 20260423,
) -> pd.DataFrame:
    values = np.asarray(values, dtype=float)
    node_count = len(values)
    std = values.std(ddof=0)
    if std == 0:
        z = np.zeros(node_count, dtype=float)
    else:
        z = (values - values.mean()) / std
    lag_z, degree = compute_row_standardized_lag(
        values=z,
        src_idx=src_idx,
        dst_idx=dst_idx,
        node_count=node_count,
    )
    observed = z * lag_z
    rng = np.random.default_rng(seed)
    extreme_count = np.ones(node_count, dtype=float)
    for _ in range(permutations):
        permuted = z.copy()
        rng.shuffle(permuted)
        lag_perm, _ = compute_row_standardized_lag(
            values=permuted,
            src_idx=src_idx,
            dst_idx=dst_idx,
            node_count=node_count,
        )
        local_perm = permuted * lag_perm
        extreme_count += (np.abs(local_perm) >= np.abs(observed)).astype(float)

    p_values = extreme_count / (permutations + 1)
    lisa_type = np.full(node_count, "NS", dtype=object)
    significant = (p_values <= alpha) & (degree > 0)
    lisa_type[significant & (z > 0) & (lag_z > 0)] = "HH"
    lisa_type[significant & (z < 0) & (lag_z < 0)] = "LL"
    lisa_type[significant & (z > 0) & (lag_z < 0)] = "HL"
    lisa_type[significant & (z < 0) & (lag_z > 0)] = "LH"

    return pd.DataFrame(
        {
            "local_moran": observed,
            "local_p_value": p_values,
            "local_z": z,
            "spatial_lag_z": lag_z,
            "neighbor_count": degree.astype(int),
            "lisa_type": lisa_type,
        }
    )


def assign_neighbor_env_level(series: pd.Series) -> pd.Series:
    pct = series.rank(method="average", pct=True)
    labels = np.select(
        [pct <= 1 / 3, pct <= 2 / 3],
        ["low", "mid"],
        default="high",
    )
    return pd.Series(labels, index=series.index)


def attach_spatial_features(
    panel: pd.DataFrame,
    edges: pd.DataFrame,
) -> pd.DataFrame:
    LOGGER.info("开始为年度面板补充空间特征。")
    panel = panel.copy()
    edge_template = edges[["src_grid_id", "dst_grid_id"]].copy()
    feature_frames: list[pd.DataFrame] = []

    for year, year_df in panel.groupby("year"):
        LOGGER.info("计算空间特征: year=%s, rows=%s", year, len(year_df))
        value_map = year_df.set_index("grid_id")["rvri"]
        state_map = year_df.set_index("grid_id")["risk_state"]

        edge_frame = edge_template.copy()
        edge_frame["neighbor_rvri"] = edge_frame["dst_grid_id"].map(value_map)
        neighbor_state = edge_frame["dst_grid_id"].map(state_map)
        edge_frame["neighbor_high"] = np.where(
            neighbor_state.notna(),
            neighbor_state.astype(float).eq(2).astype(float),
            np.nan,
        )

        aggregated = (
            edge_frame.groupby("src_grid_id", as_index=False)
            .agg(
                spatial_lag_rvri=("neighbor_rvri", "mean"),
                neighbor_high_ratio=("neighbor_high", "mean"),
                neighbor_count=("neighbor_rvri", "count"),
            )
            .rename(columns={"src_grid_id": "grid_id"})
        )
        aggregated["year"] = year
        feature_frames.append(aggregated)

    features = pd.concat(feature_frames, ignore_index=True)
    panel = panel.merge(features, on=["grid_id", "year"], how="left")
    panel["spatial_lag_rvri"] = panel["spatial_lag_rvri"].fillna(panel["rvri"])
    panel["neighbor_high_ratio"] = panel["neighbor_high_ratio"].fillna(0.0)
    panel["neighbor_count"] = panel["neighbor_count"].fillna(0).astype(int)
    panel["neighbor_env_level"] = (
        panel.groupby("year")["neighbor_high_ratio"].transform(assign_neighbor_env_level)
    )
    LOGGER.info("空间特征补充完成: rows=%s", len(panel))
    return panel


def _json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def save_geojson(gdf: pd.DataFrame, path: Path) -> None:
    ensure_output_dir()
    features = []
    for row in gdf.to_dict(orient="records"):
        geometry = row.pop("geometry")
        properties = {key: _json_safe(value) for key, value in row.items()}
        features.append({"type": "Feature", "properties": properties, "geometry": geometry})
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("GeoJSON 已写出: %s, rows=%s", path, len(gdf))


def build_transition_matrix(
    transition_df: pd.DataFrame,
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    group_cols = group_cols or []
    LOGGER.info("开始构建转移矩阵: rows=%s, group_cols=%s", len(transition_df), group_cols)
    counts = (
        transition_df.groupby(group_cols + ["risk_state", "next_risk_state"])
        .size()
        .rename("count")
        .reset_index()
    )
    full_frames: list[pd.DataFrame] = []
    if not group_cols:
        group_values = [tuple()]
    else:
        group_values = list(counts[group_cols].drop_duplicates().itertuples(index=False, name=None))

    state_pairs = pd.MultiIndex.from_product([range(3), range(3)], names=["risk_state", "next_risk_state"])
    for group_value in group_values:
        if group_cols:
            mask = np.ones(len(counts), dtype=bool)
            for col, value in zip(group_cols, group_value):
                mask &= counts[col].eq(value)
            subset = counts.loc[mask, ["risk_state", "next_risk_state", "count"]].copy()
        else:
            subset = counts.loc[:, ["risk_state", "next_risk_state", "count"]].copy()

        subset = subset.set_index(["risk_state", "next_risk_state"]).reindex(state_pairs, fill_value=0).reset_index()
        row_sum = subset.groupby("risk_state")["count"].transform("sum")
        subset["probability"] = np.divide(
            subset["count"],
            row_sum,
            out=np.zeros(len(subset), dtype=float),
            where=row_sum > 0,
        )
        if group_cols:
            for col, value in zip(group_cols, group_value):
                subset[col] = value
        full_frames.append(subset)

    columns = group_cols + ["risk_state", "next_risk_state", "count", "probability"]
    matrix_df = pd.concat(full_frames, ignore_index=True)[columns]
    LOGGER.info("转移矩阵构建完成: rows=%s", len(matrix_df))
    return matrix_df


def matrix_power_summary(matrix: np.ndarray, powers: list[int]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for power in powers:
        payload[f"P^{power}"] = np.linalg.matrix_power(matrix, power).round(6).tolist()
    return payload


def build_probability_geojson(
    grid: pd.DataFrame,
    table: pd.DataFrame,
    path: Path,
) -> pd.DataFrame:
    merged = grid.merge(table, on="grid_id", how="inner")
    save_geojson(merged, path)
    LOGGER.info("概率结果空间图层生成完成: rows=%s", len(merged))
    return merged
