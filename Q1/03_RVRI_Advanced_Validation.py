from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from analysis_domain import attach_unified_analysis_domain, summarize_unified_analysis_domain


Q1_DIR = BASE_DIR / "Q1"
DATA_DIR = Q1_DIR / "data"
OUTPUT_DIR = Q1_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BY_YEAR_SUBDIR = "by_year"

PRIMARY_PANEL_CSV = OUTPUT_DIR / "Shaoguan_RVRI_Q1_Validated.csv"
PRIMARY_GRID_GEOJSON = DATA_DIR / "scientific_grid_500m.geojson"
PRIMARY_POI_GEOJSON = DATA_DIR / "pois_cache.geojson"
PRIMARY_DISTRICT_GEOJSON = DATA_DIR / "shaoguan_districts_official.json"

DEFAULT_URBAN_QUANTILE = 0.75
DEFAULT_CORE_QUANTILE = 0.90
MORAN_PERMUTATIONS = 99
DEFAULT_RESIDENTIAL_MIN_NDVI = 0.10
DEFAULT_DISPLAY_URBAN_QUANTILE = 0.60
DEFAULT_DISPLAY_MIN_NDVI = 0.05

plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_theme(style="whitegrid")


def find_latest_matching_file(primary_path: Path) -> Path:
    if primary_path.exists():
        return primary_path

    matches = list(primary_path.parent.rglob(primary_path.name))
    if not matches:
        raise FileNotFoundError(f"Could not find {primary_path.name} under {primary_path.parent}")
    return max(matches, key=lambda path: path.stat().st_mtime)


def load_annual_panel(csv_path: Path | None = None) -> pd.DataFrame:
    panel_path = find_latest_matching_file(csv_path or PRIMARY_PANEL_CSV)
    panel = pd.read_csv(panel_path)
    if "time_grain" not in panel.columns or not panel["time_grain"].eq("annual").all():
        raise ValueError(f"{panel_path} is not an annual RVRI panel.")
    return panel


def representative_point(geometry: dict) -> np.ndarray:
    geom_type = geometry["type"]
    coords = geometry["coordinates"]
    if geom_type == "Point":
        return np.array(coords[:2], dtype=float)
    if geom_type == "Polygon":
        return np.array(coords[0], dtype=float).mean(axis=0)
    if geom_type == "MultiPolygon":
        return np.array(coords[0][0], dtype=float).mean(axis=0)
    raise ValueError(f"Unsupported geometry type: {geom_type}")


def extract_boundary_rings(features: list[dict]) -> list[np.ndarray]:
    rings: list[np.ndarray] = []
    for feature in features:
        geometry = feature["geometry"]
        geom_type = geometry["type"]
        coords = geometry["coordinates"]
        if geom_type == "Polygon":
            rings.append(np.asarray(coords[0], dtype=float))
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                rings.append(np.asarray(polygon[0], dtype=float))
    return rings


def build_affine_grid_index(features: list[dict]) -> pd.DataFrame:
    origin_feature = min(features, key=lambda feature: sum(feature["geometry"]["coordinates"][0][0]))
    ring = origin_feature["geometry"]["coordinates"][0]

    origin = np.array(ring[0], dtype=float)
    v_col = np.array(ring[1], dtype=float) - origin
    v_row = np.array(ring[3], dtype=float) - origin
    matrix = np.column_stack([v_col, v_row])
    matrix_inv = np.linalg.inv(matrix)

    rows = []
    for feature in features:
        ring = feature["geometry"]["coordinates"][0]
        anchor = np.array(ring[0], dtype=float)
        uv = matrix_inv @ (anchor - origin)
        col, row = np.rint(uv).astype(int)
        center = anchor + 0.5 * (v_col + v_row)
        rows.append(
            {
                "grid_id": str(feature["properties"]["grid_id"]),
                "col": int(col),
                "row": int(row),
                "cx": float(center[0]),
                "cy": float(center[1]),
            }
        )

    return pd.DataFrame(rows)


def build_grid_lattice(grid_path: Path | None = None) -> tuple[pd.DataFrame, dict]:
    grid_geojson_path = find_latest_matching_file(grid_path or PRIMARY_GRID_GEOJSON)
    data = json.loads(grid_geojson_path.read_text(encoding="utf-8"))
    grid = build_affine_grid_index(data["features"])

    # Recover the affine basis from the same origin cell used above.
    origin_feature = min(data["features"], key=lambda feature: sum(feature["geometry"]["coordinates"][0][0]))
    ring = origin_feature["geometry"]["coordinates"][0]
    origin = np.array(ring[0], dtype=float)
    v_col = np.array(ring[1], dtype=float) - origin
    v_row = np.array(ring[3], dtype=float) - origin
    lattice = {
        "origin": origin,
        "matrix_inv": np.linalg.inv(np.column_stack([v_col, v_row])),
        "coord_to_grid": {(int(row.col), int(row.row)): row.grid_id for row in grid.itertuples(index=False)},
    }
    return grid, lattice


def count_pois_by_grid(grid: pd.DataFrame, lattice: dict, poi_features: list[dict]) -> pd.Series:
    counts: dict[str, int] = {}

    for feature in poi_features:
        point = representative_point(feature["geometry"])
        uv = lattice["matrix_inv"] @ (point - lattice["origin"])
        base = tuple(np.floor(uv).astype(int))

        assigned_grid = None
        for d_col in (0, 1, -1):
            for d_row in (0, 1, -1):
                candidate = (base[0] + d_col, base[1] + d_row)
                if candidate in lattice["coord_to_grid"]:
                    assigned_grid = lattice["coord_to_grid"][candidate]
                    break
            if assigned_grid is not None:
                break

        if assigned_grid is not None:
            counts[assigned_grid] = counts.get(assigned_grid, 0) + 1

    series = pd.Series(counts, name="poi_count", dtype=float)
    series.index = series.index.astype(str)
    return series


def _safe_corr(frame: pd.DataFrame, left: str, right: str, method: str = "pearson") -> float | None:
    subset = frame[[left, right]].dropna()
    if subset.empty:
        return None
    return float(subset[left].corr(subset[right], method=method))


def _neighbor_positive_light(snapshot: pd.DataFrame) -> pd.Series:
    valid = snapshot.dropna(subset=["col", "row"]).copy()
    coord_to_idx = {
        (int(row.col), int(row.row)): idx
        for idx, row in enumerate(valid[["col", "row"]].itertuples(index=False))
    }
    light = valid["light"].fillna(0).to_numpy(dtype=float)
    flags: list[bool] = []

    for row in valid[["col", "row"]].itertuples(index=False):
        has_positive_neighbor = False
        for d_col in (-1, 0, 1):
            for d_row in (-1, 0, 1):
                if d_col == 0 and d_row == 0:
                    continue
                neighbor = coord_to_idx.get((int(row.col) + d_col, int(row.row) + d_row))
                if neighbor is not None and light[neighbor] > 0:
                    has_positive_neighbor = True
                    break
            if has_positive_neighbor:
                break
        flags.append(has_positive_neighbor)

    return pd.Series(flags, index=valid.index, dtype=bool)


def select_residential_candidate_snapshot(
    snapshot: pd.DataFrame,
    poi_counts: pd.Series | None = None,
    urban_quantile: float = DEFAULT_URBAN_QUANTILE,
    min_ndvi: float = DEFAULT_RESIDENTIAL_MIN_NDVI,
    require_settlement_context: bool = True,
) -> dict:
    working = snapshot.dropna(subset=["rvri", "ndbi", "ndvi", "light", "col", "row"]).copy()
    if "poi_count" in working.columns:
        working = working.drop(columns=["poi_count"])
    if poi_counts is not None and not poi_counts.empty:
        working = working.merge(poi_counts.rename("poi_count"), left_on="grid_id", right_index=True, how="left")
    else:
        working["poi_count"] = 0.0
    working["poi_count"] = working["poi_count"].fillna(0.0)

    urban_threshold = float(working["ndbi"].quantile(urban_quantile))
    working["neighbor_positive_light"] = False
    neighbor_flags = _neighbor_positive_light(working)
    working.loc[neighbor_flags.index, "neighbor_positive_light"] = neighbor_flags

    working["passes_builtup"] = working["ndbi"] >= urban_threshold
    working["passes_non_barren"] = working["ndvi"] >= min_ndvi
    working["passes_settlement_context"] = (
        working["light"].fillna(0).gt(0)
        | working["neighbor_positive_light"]
        | working["poi_count"].gt(0)
    )
    working["residential_candidate"] = (
        working["passes_builtup"]
        & working["passes_non_barren"]
        & (working["passes_settlement_context"] if require_settlement_context else True)
    )

    candidates = working[working["residential_candidate"]].copy()
    summary = {
        "urban_quantile": urban_quantile,
        "urban_ndbi_threshold": urban_threshold,
        "min_ndvi": min_ndvi,
        "snapshot_rows": int(len(working)),
        "candidate_rows": int(len(candidates)),
        "excluded_barren_or_remote_rows": int((~working["residential_candidate"]).sum()),
        "positive_light_candidate_rows": int(candidates["light"].fillna(0).gt(0).sum()),
        "neighbor_light_context_rows": int(candidates["neighbor_positive_light"].sum()),
        "poi_context_rows": int(candidates["poi_count"].gt(0).sum()),
        "require_settlement_context": bool(require_settlement_context),
    }
    return {"snapshot": candidates, "summary": summary}


def assess_method_effectiveness(
    panel: pd.DataFrame,
    urban_quantile: float = DEFAULT_URBAN_QUANTILE,
    core_quantile: float = DEFAULT_CORE_QUANTILE,
) -> dict:
    working = panel.dropna(subset=["rvri", "ndbi", "ndvi", "light", "mismatch_gap"]).copy()
    if working.empty:
        raise ValueError("Annual RVRI panel has no usable rows for validation.")

    urban_threshold = float(working["ndbi"].quantile(urban_quantile))
    core_threshold = float(working["ndbi"].quantile(core_quantile))

    urban = working[working["ndbi"] >= urban_threshold].copy()
    core = working[working["ndbi"] >= core_threshold].copy()

    summary = {
        "full_sample": {
            "rows": int(len(working)),
            "corr_rvri_light": _safe_corr(working, "rvri", "light"),
            "corr_rvri_mismatch": _safe_corr(working, "rvri", "mismatch_gap"),
            "corr_rvri_ndbi": _safe_corr(working, "rvri", "ndbi"),
            "corr_rvri_ndvi": _safe_corr(working, "rvri", "ndvi"),
        },
        "urban_subset": {
            "rows": int(len(urban)),
            "ndbi_threshold": urban_threshold,
            "corr_rvri_light": _safe_corr(urban, "rvri", "light"),
            "corr_rvri_mismatch": _safe_corr(urban, "rvri", "mismatch_gap"),
        },
        "core_subset": {
            "rows": int(len(core)),
            "ndbi_threshold": core_threshold,
            "corr_rvri_light": _safe_corr(core, "rvri", "light"),
            "corr_rvri_mismatch": _safe_corr(core, "rvri", "mismatch_gap"),
        },
    }

    light_corr = summary["urban_subset"]["corr_rvri_light"]
    mismatch_corr = summary["urban_subset"]["corr_rvri_mismatch"]
    summary["works_for_q1"] = bool(
        light_corr is not None
        and mismatch_corr is not None
        and light_corr <= -0.30
        and mismatch_corr >= 0.50
    )
    return summary


def compute_moran_metrics(snapshot: pd.DataFrame, permutations: int = MORAN_PERMUTATIONS) -> dict:
    valid = snapshot.dropna(subset=["rvri", "col", "row"]).copy()
    if len(valid) < 2:
        valid["cluster"] = "NA"
        valid["lag_rvri"] = 0.0
        return {
            "summary": {
                "global_moran_i": 0.0,
                "p_value": None,
                "hh_count": 0,
                "rows": int(len(valid)),
            },
            "snapshot": valid,
        }

    coord_to_idx = {(int(row.col), int(row.row)): i for i, row in enumerate(valid[["col", "row"]].itertuples(index=False))}

    src: list[int] = []
    dst: list[int] = []
    for idx, row in enumerate(valid[["col", "row"]].itertuples(index=False)):
        for d_col in (-1, 0, 1):
            for d_row in (-1, 0, 1):
                if d_col == 0 and d_row == 0:
                    continue
                neighbor = coord_to_idx.get((int(row.col) + d_col, int(row.row) + d_row))
                if neighbor is not None:
                    src.append(idx)
                    dst.append(neighbor)

    src_arr = np.asarray(src, dtype=np.int32)
    dst_arr = np.asarray(dst, dtype=np.int32)
    values = valid["rvri"].to_numpy(dtype=float)
    centered = values - values.mean()
    if len(src_arr) == 0:
        valid["cluster"] = "NA"
        valid["lag_rvri"] = 0.0
        return {
            "summary": {
                "global_moran_i": 0.0,
                "p_value": None,
                "hh_count": 0,
                "rows": int(len(valid)),
            },
            "snapshot": valid,
        }

    degree = np.bincount(src_arr, minlength=len(values)).astype(float)
    neighbor_sum = np.bincount(src_arr, weights=centered[dst_arr], minlength=len(values))
    lag = np.divide(
        neighbor_sum,
        degree,
        out=np.zeros(len(values), dtype=float),
        where=degree > 0,
    )
    non_island = degree > 0
    s0 = float(non_island.sum())
    denominator = float(np.sum(centered * centered))
    moran_i = float((len(values) / s0) * np.dot(centered[non_island], lag[non_island]) / denominator)

    rng = np.random.default_rng(42)
    permuted_stats = []
    for _ in range(permutations):
        shuffled = rng.permutation(centered)
        shuffled_neighbor_sum = np.bincount(src_arr, weights=shuffled[dst_arr], minlength=len(values))
        shuffled_lag = np.divide(
            shuffled_neighbor_sum,
            degree,
            out=np.zeros(len(values), dtype=float),
            where=degree > 0,
        )
        permuted_stats.append(float((len(values) / s0) * np.dot(shuffled[non_island], shuffled_lag[non_island]) / denominator))
    permuted_stats_arr = np.asarray(permuted_stats)
    p_value = float((np.sum(np.abs(permuted_stats_arr) >= abs(moran_i)) + 1) / (len(permuted_stats_arr) + 1))

    clusters = np.where(
        centered > 0,
        np.where(lag > 0, "HH", "HL"),
        np.where(lag > 0, "LH", "LL"),
    )
    valid["cluster"] = clusters
    valid["lag_rvri"] = lag

    return {
        "summary": {
            "global_moran_i": moran_i,
            "p_value": p_value,
            "hh_count": int((valid["cluster"] == "HH").sum()),
            "rows": int(len(valid)),
        },
        "snapshot": valid,
    }


def compute_poi_validation(
    snapshot: pd.DataFrame,
    poi_counts: pd.Series,
    urban_quantile: float = DEFAULT_URBAN_QUANTILE,
) -> dict:
    working = snapshot.dropna(subset=["rvri", "ndbi"]).copy()
    working = working.merge(poi_counts, left_on="grid_id", right_index=True, how="left")
    working["poi_count"] = working["poi_count"].fillna(0)

    urban_threshold = float(working["ndbi"].quantile(urban_quantile))
    subset = working[(working["ndbi"] >= urban_threshold) & (working["poi_count"] > 0)].copy()
    subset["poi_log"] = np.log1p(subset["poi_count"])

    return {
        "summary": {
            "rows": int(len(subset)),
            "ndbi_threshold": urban_threshold,
            "spearman_rvri_poi": _safe_corr(subset, "rvri", "poi_count", method="spearman"),
            "pearson_rvri_poi_log": _safe_corr(subset, "rvri", "poi_log"),
        },
        "snapshot": subset,
    }


def compute_coupling_metrics(
    snapshot: pd.DataFrame,
    urban_quantile: float = DEFAULT_URBAN_QUANTILE,
) -> dict:
    working = snapshot.dropna(subset=["rvri", "ndbi", "light"]).copy()
    urban_threshold = float(working["ndbi"].quantile(urban_quantile))
    subset = working[working["ndbi"] >= urban_threshold].copy()

    for column in ["ndbi", "light"]:
        min_value = float(working[column].min())
        max_value = float(working[column].max())
        subset[f"{column}_norm"] = (subset[column] - min_value) / (max_value - min_value + 1e-9)

    u1 = subset["ndbi_norm"].to_numpy(dtype=float) + 1e-5
    u2 = subset["light_norm"].to_numpy(dtype=float) + 1e-5
    coupling = (2 * np.sqrt(u1 * u2)) / (u1 + u2 + 1e-9)
    coordination = 0.5 * u1 + 0.5 * u2
    subset["ccdm_D"] = np.sqrt(coupling * coordination)

    subset["ccdm_level"] = pd.cut(
        subset["ccdm_D"],
        bins=[0.0, 0.3, 0.5, 0.7, 1.0],
        labels=["严重失调", "轻度失调", "勉强协调", "优质协调"],
        include_lowest=True,
    )

    return {
        "summary": {
            "rows": int(len(subset)),
            "ndbi_threshold": urban_threshold,
            "ccdm_mean": float(subset["ccdm_D"].mean()),
            "corr_rvri_vs_ccdm": _safe_corr(subset, "rvri", "ccdm_D"),
            "ccdm_distribution": {str(key): int(value) for key, value in subset["ccdm_level"].value_counts().to_dict().items()},
        },
        "snapshot": subset,
    }


def plot_method_effectiveness(snapshot: pd.DataFrame, output_path: Path) -> None:
    plt.figure(figsize=(10, 6))
    sample = snapshot.sample(min(4000, len(snapshot)), random_state=42)
    sns.scatterplot(data=sample, x="light", y="rvri", hue="ndbi", palette="viridis", alpha=0.35, s=18, linewidth=0)
    plt.xlabel("Nighttime Light")
    plt.ylabel("RVRI")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_lisa_like_map(
    candidate_snapshot: pd.DataFrame,
    display_snapshot: pd.DataFrame,
    full_snapshot: pd.DataFrame,
    output_path: Path,
    year: int,
    moran_i: float,
    district_geojson_path: Path | None = None,
) -> None:
    colors = {"HH": "#e31a1c", "LL": "#1f78b4", "HL": "#fb9a99", "LH": "#a6cee3"}
    district_geojson_path = district_geojson_path or PRIMARY_DISTRICT_GEOJSON
    candidate_ids = set(candidate_snapshot["grid_id"].astype(str).tolist())
    display_ids = set(display_snapshot["grid_id"].astype(str).tolist())
    background_snapshot = full_snapshot.copy()
    background_snapshot["grid_id"] = background_snapshot["grid_id"].astype(str)
    excluded_snapshot = background_snapshot[~background_snapshot["grid_id"].isin(display_ids)].copy()
    display_only_snapshot = background_snapshot[
        background_snapshot["grid_id"].isin(display_ids) & ~background_snapshot["grid_id"].isin(candidate_ids)
    ].copy()

    plt.figure(figsize=(10, 10))
    ax = plt.gca()

    if district_geojson_path.exists():
        district_geojson = json.loads(district_geojson_path.read_text(encoding="utf-8"))
        for ring in extract_boundary_rings(district_geojson.get("features", [])):
            ax.plot(ring[:, 0], ring[:, 1], color="#000000", linewidth=0.85, alpha=0.95, zorder=5)

    if not background_snapshot.empty:
        ax.scatter(
            background_snapshot["cx"],
            background_snapshot["cy"],
            s=1.0,
            c="#d9d9d9",
            alpha=0.45,
            label="Frame",
            zorder=2,
        )
    if not excluded_snapshot.empty:
        ax.scatter(
            excluded_snapshot["cx"],
            excluded_snapshot["cy"],
            s=1.2,
            c="#a6a6a6",
            alpha=0.55,
            label="Excluded",
            zorder=3,
        )
    if not display_only_snapshot.empty:
        ax.scatter(
            display_only_snapshot["cx"],
            display_only_snapshot["cy"],
            s=1.4,
            c="#e6d8ad",
            alpha=0.60,
            label="Built-up context",
            zorder=3.2,
        )
    for cluster, color in colors.items():
        subset = candidate_snapshot[candidate_snapshot["cluster"] == cluster]
        if not subset.empty:
            ax.scatter(subset["cx"], subset["cy"], s=3, c=color, label=cluster, alpha=0.75, zorder=4)
    from matplotlib.patches import Patch

    handles = [Patch(facecolor=colors[item], edgecolor="none", label=item) for item in ["LL", "LH", "HL", "HH"]]
    ax.legend(handles=handles, loc="lower left", frameon=True, title="LISA Type")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="box")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_poi_validation(snapshot: pd.DataFrame, output_path: Path) -> None:
    plt.figure(figsize=(10, 6))
    sns.regplot(
        data=snapshot,
        x="poi_log",
        y="rvri",
        scatter_kws={"alpha": 0.35, "s": 20, "color": "#2c7bb6"},
        line_kws={"color": "#d7191c"},
    )
    plt.xlabel("log(1 + POI count)")
    plt.ylabel("RVRI")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_coupling_validation(snapshot: pd.DataFrame, output_path: Path) -> None:
    sample = snapshot.sample(min(5000, len(snapshot)), random_state=42)
    grid = sns.jointplot(
        data=sample,
        x="light",
        y="ndbi",
        kind="hex",
        color="#2c7fb8",
        height=8,
    )
    grid.set_axis_labels("Nighttime Light", "NDBI")
    plt.tight_layout()
    grid.fig.savefig(output_path, dpi=300)
    plt.close(grid.fig)


def _write_validation_outputs(
    merged: pd.DataFrame,
    snapshot: pd.DataFrame,
    grid: pd.DataFrame,
    lattice: dict,
    poi_features: list[dict],
    output_dir: Path,
    snapshot_year: int,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    effectiveness = assess_method_effectiveness(merged)
    urban_threshold = effectiveness["urban_subset"]["ndbi_threshold"]
    urban_snapshot = snapshot[snapshot["ndbi"] >= urban_threshold].copy()
    poi_counts = count_pois_by_grid(grid, lattice, poi_features)
    snapshot = attach_unified_analysis_domain(snapshot, year_col="source_year")
    residential_candidates = select_residential_candidate_snapshot(snapshot, poi_counts=poi_counts)
    analysis_domain = snapshot[snapshot["in_analysis_domain"].fillna(False)].copy()
    display_candidates = select_residential_candidate_snapshot(
        snapshot,
        poi_counts=poi_counts,
        urban_quantile=DEFAULT_DISPLAY_URBAN_QUANTILE,
        min_ndvi=DEFAULT_DISPLAY_MIN_NDVI,
        require_settlement_context=False,
    )
    moran_snapshot = analysis_domain
    moran = compute_moran_metrics(moran_snapshot)
    poi_validation = compute_poi_validation(snapshot, poi_counts)
    coupling = compute_coupling_metrics(snapshot)

    plot_method_effectiveness(urban_snapshot, output_dir / "Q1_RVRI_Scientific_Check.png")
    plot_lisa_like_map(
        candidate_snapshot=moran["snapshot"],
        display_snapshot=display_candidates["snapshot"],
        full_snapshot=snapshot,
        output_path=output_dir / "Q1_LISA_Map.png",
        year=snapshot_year,
        moran_i=moran["summary"]["global_moran_i"],
    )
    plot_poi_validation(poi_validation["snapshot"], output_dir / "Q1_POI_Validation_Enhanced.png")
    plot_coupling_validation(coupling["snapshot"], output_dir / "Q1_Step6_KDE_Coupling_Validation.png")

    report = {
        "data_basis": {
            "panel_time_grain": "annual",
            "validated_years": sorted(merged["source_year"].dropna().astype(int).unique().tolist()),
            "latest_snapshot_year": snapshot_year,
            "total_rows": int(len(merged)),
            "snapshot_rows": int(len(snapshot)),
        },
        "analysis_domain_filter": summarize_unified_analysis_domain(snapshot, year_col="source_year"),
        "strict_residential_candidate_filter": residential_candidates["summary"],
        "method_effectiveness": effectiveness,
        "spatial_autocorr": moran["summary"],
        "poi_validation": poi_validation["summary"],
        "coupling_coordination": coupling["summary"],
    }

    (output_dir / "Q1_Diagnostic_Full_Report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "validation_report.json").write_text(
        json.dumps(
            {
                "method_effectiveness": effectiveness,
                "latest_snapshot_year": snapshot_year,
                "spatial_moran_i": moran["summary"]["global_moran_i"],
                "poi_spearman": poi_validation["summary"]["spearman_rvri_poi"],
                "ccdm_corr": coupling["summary"]["corr_rvri_vs_ccdm"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def run_validation(
    annual_csv_path: Path | None = None,
    grid_geojson_path: Path | None = None,
    poi_geojson_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict:
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    panel = load_annual_panel(annual_csv_path)
    grid, lattice = build_grid_lattice(grid_geojson_path)
    poi_geojson = json.loads(find_latest_matching_file(poi_geojson_path or PRIMARY_POI_GEOJSON).read_text(encoding="utf-8"))

    merged = panel.merge(grid, on="grid_id", how="left")
    latest_year = int(merged["source_year"].max())
    latest_snapshot = merged[(merged["source_year"] == latest_year) & merged["rvri"].notna()].copy()
    return _write_validation_outputs(
        merged=merged,
        snapshot=latest_snapshot,
        grid=grid,
        lattice=lattice,
        poi_features=poi_geojson["features"],
        output_dir=output_dir,
        snapshot_year=latest_year,
    )


def run_validation_by_year(
    annual_csv_path: Path | None = None,
    grid_geojson_path: Path | None = None,
    poi_geojson_path: Path | None = None,
    output_root_dir: Path | None = None,
) -> dict:
    output_root_dir = output_root_dir or OUTPUT_DIR
    output_root_dir.mkdir(parents=True, exist_ok=True)

    panel = load_annual_panel(annual_csv_path)
    grid, lattice = build_grid_lattice(grid_geojson_path)
    poi_geojson = json.loads(find_latest_matching_file(poi_geojson_path or PRIMARY_POI_GEOJSON).read_text(encoding="utf-8"))

    merged = panel.merge(grid, on="grid_id", how="left")
    years = sorted(merged["source_year"].dropna().astype(int).unique().tolist())
    by_year_dir = output_root_dir / BY_YEAR_SUBDIR
    by_year_dir.mkdir(parents=True, exist_ok=True)

    year_reports: dict[str, dict] = {}
    year_summaries: list[dict] = []

    for year in years:
        snapshot = merged[(merged["source_year"] == year) & merged["rvri"].notna()].copy()
        year_dir = by_year_dir / str(year)
        report = _write_validation_outputs(
            merged=merged,
            snapshot=snapshot,
            grid=grid,
            lattice=lattice,
            poi_features=poi_geojson["features"],
            output_dir=year_dir,
            snapshot_year=year,
        )
        year_reports[str(year)] = report
        year_summaries.append(
            {
                "year": year,
                "rows": int(len(snapshot)),
                "spatial_moran_i": report["spatial_autocorr"]["global_moran_i"],
                "poi_spearman": report["poi_validation"]["spearman_rvri_poi"],
                "ccdm_corr": report["coupling_coordination"]["corr_rvri_vs_ccdm"],
            }
        )

    summary = {
        "years": years,
        "year_reports": year_reports,
        "year_summaries": year_summaries,
    }
    (by_year_dir / "by_year_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    report = run_validation()
    print("Q1 annual validation finished.")
    print(f"Latest snapshot year: {report['data_basis']['latest_snapshot_year']}")
    print(f"Method works for Q1: {report['method_effectiveness']['works_for_q1']}")
    print(f"Global Moran's I: {report['spatial_autocorr']['global_moran_i']:.4f}")


if __name__ == "__main__":
    main()
