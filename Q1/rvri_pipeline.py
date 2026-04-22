from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover - optional at test time
    gpd = None


BASE_DIR = Path(__file__).resolve().parent.parent
Q1_DIR = BASE_DIR / "Q1"
DATA_DIR = Q1_DIR / "data"
OUTPUT_DIR = Q1_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL_FEATURES = ["stock_pressure", "eco_deficit", "mismatch_gap"]
LIGHT_SENTINEL_FLOOR = -1e30
LIGHT_MISSING_RATE_THRESHOLD = 0.05
MIN_POSITIVE_LIGHT_RATE = 0.03
QUARTER_CONSTANT_THRESHOLD = 0.95


def clean_light_series(series: pd.Series) -> pd.Series:
    cleaned = pd.to_numeric(series, errors="coerce")
    cleaned = cleaned.replace([np.inf, -np.inf], np.nan)
    return cleaned.mask(cleaned <= LIGHT_SENTINEL_FLOOR)


def load_panel_files(data_dir: Path | None = None) -> pd.DataFrame:
    data_dir = data_dir or DATA_DIR
    frames = []

    for path in sorted(data_dir.glob("Shaoguan_RVRI_20*.csv")):
        match = re.search(r"(20\d{2})", path.name)
        if match is None:
            continue

        year = int(match.group(1))
        frame = pd.read_csv(path)
        required = {"grid_id", "time", "ndbi", "ndvi", "light"}
        if not required.issubset(frame.columns):
            continue

        if "district_name" not in frame.columns:
            frame["district_name"] = frame.get("district")

        frame = frame[
            ["grid_id", "district_name", "time", "ndbi", "ndvi", "light"]
        ].copy()
        frame["source_year"] = year
        frames.append(frame)

    if not frames:
        raise FileNotFoundError(f"No panel files were found under {data_dir}")

    panel = pd.concat(frames, ignore_index=True)
    panel["grid_id"] = panel["grid_id"].astype(str)
    panel["light"] = clean_light_series(panel["light"])
    panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel


def _safe_corr(frame: pd.DataFrame, left: str, right: str) -> float | None:
    subset = frame[[left, right]].dropna()
    if subset.empty:
        return None
    return float(subset.corr().iloc[0, 1])


def _quarter_constant_share(frame: pd.DataFrame) -> float:
    if frame["time"].nunique() <= 1:
        return float("nan")

    pivot = frame.pivot_table(
        index="grid_id",
        columns="time",
        values="light",
        aggfunc="mean",
        observed=False,
    )
    if pivot.empty:
        return float("nan")

    def is_constant(row: pd.Series) -> bool:
        values = row.dropna()
        if len(values) <= 1:
            return False
        return values.nunique() == 1

    return float(pivot.apply(is_constant, axis=1).mean())


def audit_year_quality(panel: pd.DataFrame) -> pd.DataFrame:
    records = []

    for year, frame in panel.groupby("source_year", sort=True):
        issues = []
        zero_rate = float(frame["light"].fillna(0).eq(0).mean())
        positive_rate = float(frame["light"].fillna(0).gt(0).mean())
        missing_rate = float(frame["light"].isna().mean())
        constant_share = _quarter_constant_share(frame)
        temporal_grain = (
            "annual_replicated"
            if pd.notna(constant_share) and constant_share >= QUARTER_CONSTANT_THRESHOLD
            else "quarterly"
        )

        if missing_rate >= LIGHT_MISSING_RATE_THRESHOLD:
            issues.append("missing light")
        if positive_rate < MIN_POSITIVE_LIGHT_RATE:
            issues.append("no usable nightlight signal")
        if temporal_grain == "annual_replicated":
            issues.append("quarter-constant light")

        usable = missing_rate < LIGHT_MISSING_RATE_THRESHOLD and positive_rate >= MIN_POSITIVE_LIGHT_RATE
        records.append(
            {
                "source_year": int(year),
                "rows": int(len(frame)),
                "unique_grids": int(frame["grid_id"].nunique()),
                "light_zero_rate": zero_rate,
                "positive_light_rate": positive_rate,
                "light_missing_rate": missing_rate,
                "quarter_constant_share": constant_share,
                "temporal_grain": temporal_grain,
                "corr_ndbi_light": _safe_corr(frame, "ndbi", "light"),
                "corr_ndvi_light": _safe_corr(frame, "ndvi", "light"),
                "usable_for_calibration": bool(usable),
                "issues": "; ".join(issues),
            }
        )

    return pd.DataFrame(records)


def aggregate_to_annual_panel(panel: pd.DataFrame) -> pd.DataFrame:
    annual = (
        panel.groupby(["grid_id", "district_name", "source_year"], dropna=False, as_index=False)
        .agg({"ndbi": "mean", "ndvi": "mean", "light": "mean"})
        .copy()
    )
    annual["time"] = annual["source_year"].astype(str)
    annual["time_grain"] = "annual"
    return annual


def _zscore_by_year(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.nan, index=series.index)
    return (series - series.mean()) / std


def build_risk_features(panel: pd.DataFrame) -> pd.DataFrame:
    enriched = panel.copy()

    for column in ["ndbi", "ndvi", "light"]:
        enriched[f"{column}_z"] = enriched.groupby("source_year")[column].transform(
            _zscore_by_year
        )

    enriched["stock_pressure"] = enriched["ndbi_z"]
    enriched["activity_deficit"] = -enriched["light_z"]
    enriched["eco_deficit"] = -enriched["ndvi_z"]
    enriched["mismatch_gap"] = enriched["ndbi_z"] - enriched["light_z"]
    return enriched


def fit_rvri_model(
    reference_panel: pd.DataFrame,
    feature_names: Iterable[str] | None = None,
) -> dict:
    feature_names = list(feature_names or DEFAULT_MODEL_FEATURES)
    working = reference_panel.dropna(subset=feature_names).copy()
    if working.empty:
        raise ValueError("No reference rows are available for RVRI calibration.")

    scaler = StandardScaler()
    x_ref = scaler.fit_transform(working[feature_names])

    pca = PCA(n_components=1)
    ref_scores = pca.fit_transform(x_ref).ravel()
    loadings = pd.Series(pca.components_[0], index=feature_names)

    sign = 1.0
    if loadings.mean() < 0:
        sign = -1.0
        loadings = -loadings
        ref_scores = -ref_scores

    if (loadings <= 0).any():
        raise ValueError(
            "The selected RVRI features do not produce a monotonic first component."
        )

    return {
        "features": feature_names,
        "scaler": scaler,
        "pca": pca,
        "sign": sign,
        "loadings": {name: float(value) for name, value in loadings.items()},
        "explained_variance_ratio": float(pca.explained_variance_ratio_[0]),
        "reference_rows": int(len(working)),
        "reference_score_min": float(ref_scores.min()),
        "reference_score_max": float(ref_scores.max()),
    }


def _minmax_scale(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    minimum = series.min()
    maximum = series.max()
    if pd.isna(minimum) or pd.isna(maximum) or minimum == maximum:
        return pd.Series(0.5, index=series.index, dtype=float)
    return (series - minimum) / (maximum - minimum)


def _assign_risk_state(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)
    if valid.nunique() < 3:
        ranked = valid.rank(method="first", pct=True)
        result = pd.Series(np.nan, index=series.index)
        result.loc[valid.index] = np.where(ranked <= 1 / 3, 0, np.where(ranked <= 2 / 3, 1, 2))
        return result

    labels = pd.qcut(valid, q=3, labels=[0, 1, 2], duplicates="drop")
    result = pd.Series(np.nan, index=series.index)
    result.loc[valid.index] = labels.astype(float)
    return result


def score_panel(
    panel: pd.DataFrame,
    quality_audit: pd.DataFrame,
    feature_names: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    feature_names = list(feature_names or DEFAULT_MODEL_FEATURES)
    scored = aggregate_to_annual_panel(panel)
    scored = build_risk_features(scored)

    quality_map = quality_audit.set_index("source_year")["usable_for_calibration"].to_dict()
    temporal_map = quality_audit.set_index("source_year")["temporal_grain"].to_dict()
    scored["usable_for_calibration"] = scored["source_year"].map(quality_map).fillna(False)
    scored["temporal_grain"] = scored["source_year"].map(temporal_map).fillna("unknown")
    scored["quality_flag"] = np.where(scored["usable_for_calibration"], "validated", "degraded_light")
    scored.loc[
        scored["usable_for_calibration"] & scored["temporal_grain"].eq("annual_replicated"),
        "quality_flag",
    ] = "annual_ntl_replicated"

    reference_panel = scored[scored["usable_for_calibration"]].copy()
    model_info = fit_rvri_model(reference_panel, feature_names)

    eligible_mask = scored["usable_for_calibration"] & scored[feature_names].notna().all(axis=1)
    scored["rvri_raw"] = np.nan

    if eligible_mask.any():
        transformed = model_info["pca"].transform(
            model_info["scaler"].transform(scored.loc[eligible_mask, feature_names])
        ).ravel()
        transformed = transformed * model_info["sign"]
        scored.loc[eligible_mask, "rvri_raw"] = transformed

    scored["rvri"] = np.nan
    for year, index in scored.loc[eligible_mask].groupby("source_year").groups.items():
        scored.loc[index, "rvri"] = _minmax_scale(scored.loc[index, "rvri_raw"])

    scored["risk_state"] = np.nan
    for year, index in scored.loc[eligible_mask].groupby("source_year").groups.items():
        scored.loc[index, "risk_state"] = _assign_risk_state(scored.loc[index, "rvri"])

    return scored, model_info


def save_outputs(
    scored: pd.DataFrame,
    quality_audit: pd.DataFrame,
    model_info: dict,
    output_dir: Path | None = None,
    grid_path: Path | None = None,
) -> dict:
    output_dir = output_dir or OUTPUT_DIR
    grid_path = grid_path or (DATA_DIR / "scientific_grid_500m.geojson")
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "Shaoguan_RVRI_Q1_Validated.csv"
    audit_path = output_dir / "Q1_Data_Quality_Audit.json"
    metadata_path = output_dir / "Q1_RVRI_Model_Metadata.json"
    geojson_path = output_dir / "Shaoguan_RVRI_Q1_Validated_Latest.geojson"

    scored.to_csv(csv_path, index=False)

    audit_payload = {
        "quality_audit": quality_audit.to_dict(orient="records"),
        "validated_years": quality_audit.loc[
            quality_audit["usable_for_calibration"], "source_year"
        ].tolist(),
        "degraded_years": quality_audit.loc[
            ~quality_audit["usable_for_calibration"], "source_year"
        ].tolist(),
    }
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_payload = {
        "features": model_info["features"],
        "loadings": model_info["loadings"],
        "explained_variance_ratio": model_info["explained_variance_ratio"],
        "reference_rows": model_info["reference_rows"],
        "reference_score_min": model_info["reference_score_min"],
        "reference_score_max": model_info["reference_score_max"],
    }
    metadata_path.write_text(
        json.dumps(metadata_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if gpd is not None and grid_path.exists():
        validated = scored.loc[scored["quality_flag"] == "validated"].copy()
        if not validated.empty:
            latest_time = sorted(validated["time"].unique())[-1]
            snapshot = validated.loc[validated["time"] == latest_time].copy()
            grid = gpd.read_file(grid_path)
            grid["grid_id"] = grid["grid_id"].astype(str)
            merged = grid.merge(snapshot, on="grid_id", how="inner")
            merged.to_file(geojson_path, driver="GeoJSON")

    return {
        "csv_path": str(csv_path),
        "audit_path": str(audit_path),
        "metadata_path": str(metadata_path),
        "geojson_path": str(geojson_path),
    }


def run_pipeline(
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    grid_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    panel = load_panel_files(data_dir)
    quality_audit = audit_year_quality(panel)
    scored, model_info = score_panel(panel, quality_audit)
    output_paths = save_outputs(scored, quality_audit, model_info, output_dir, grid_path)
    return scored, quality_audit, model_info, output_paths


def main() -> None:
    scored, quality_audit, model_info, output_paths = run_pipeline()
    validated_years = quality_audit.loc[
        quality_audit["usable_for_calibration"], "source_year"
    ].tolist()
    degraded_years = quality_audit.loc[
        ~quality_audit["usable_for_calibration"], "source_year"
    ].tolist()

    print("Q1 RVRI synthesis finished.")
    print(f"Validated years: {validated_years}")
    print(f"Degraded years: {degraded_years}")
    print(f"Explained variance (PC1): {model_info['explained_variance_ratio']:.2%}")
    print(f"Saved validated panel to: {output_paths['csv_path']}")
    print(f"Saved quality audit to: {output_paths['audit_path']}")


if __name__ == "__main__":
    main()
