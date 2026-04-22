from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pandas as pd


def load_pipeline_module():
    module_path = Path(__file__).resolve().parents[2] / "Q1" / "rvri_pipeline.py"
    spec = spec_from_file_location("rvri_pipeline", module_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_audit_year_quality_marks_annual_replicated_light_as_q1_usable():
    pipeline = load_pipeline_module()

    df = pd.DataFrame(
        {
            "grid_id": ["g1", "g1", "g1", "g1", "g2", "g2", "g2", "g2"],
            "source_year": [2022] * 8,
            "time": ["2022Q1", "2022Q2", "2022Q3", "2022Q4"] * 2,
            "ndbi": [0.7, 0.7, 0.7, 0.7, 0.2, 0.2, 0.2, 0.2],
            "ndvi": [0.1, 0.1, 0.1, 0.1, 0.6, 0.6, 0.6, 0.6],
            "light": [0.0, 0.0, 0.0, 0.0, 2.5, 2.5, 2.5, 2.5],
        }
    )

    audit = pipeline.audit_year_quality(df)
    row = audit.iloc[0]

    assert row["source_year"] == 2022
    assert row["quarter_constant_share"] == 1.0
    assert bool(row["usable_for_calibration"])
    assert row["temporal_grain"] == "annual_replicated"
    assert "quarter-constant light" in row["issues"]
    assert "no usable nightlight signal" not in row["issues"]


def test_aggregate_to_annual_panel_collapses_quarters():
    pipeline = load_pipeline_module()

    df = pd.DataFrame(
        {
            "grid_id": ["g1", "g1", "g1", "g1"],
            "district_name": ["A", "A", "A", "A"],
            "source_year": [2021] * 4,
            "time": ["2021Q1", "2021Q2", "2021Q3", "2021Q4"],
            "ndbi": [0.2, 0.4, 0.6, 0.8],
            "ndvi": [0.8, 0.7, 0.6, 0.5],
            "light": [3.0, 3.0, 3.0, 3.0],
        }
    )

    annual = pipeline.aggregate_to_annual_panel(df)

    assert len(annual) == 1
    row = annual.iloc[0]
    assert row["time"] == "2021"
    assert row["time_grain"] == "annual"
    assert row["ndbi"] == 0.5
    assert row["ndvi"] == 0.65
    assert row["light"] == 3.0


def test_score_panel_uses_annual_panel_for_replicated_nightlight():
    pipeline = load_pipeline_module()

    df = pd.DataFrame(
        {
            "grid_id": ["g1", "g1", "g1", "g1", "g2", "g2", "g2", "g2"] * 3,
            "district_name": ["A"] * 12 + ["B"] * 12,
            "source_year": [2019] * 8 + [2020] * 8 + [2021] * 8,
            "time": (
                ["2019Q1", "2019Q2", "2019Q3", "2019Q4"] * 2
                + ["2020Q1", "2020Q2", "2020Q3", "2020Q4"] * 2
                + ["2021Q1", "2021Q2", "2021Q3", "2021Q4"] * 2
            ),
            "ndbi": [
                0.8,
                0.82,
                0.81,
                0.83,
                0.2,
                0.22,
                0.21,
                0.23,
                0.82,
                0.84,
                0.83,
                0.85,
                0.25,
                0.27,
                0.26,
                0.28,
                0.84,
                0.86,
                0.85,
                0.87,
                0.3,
                0.32,
                0.31,
                0.33,
            ],
            "ndvi": [
                0.1,
                0.12,
                0.11,
                0.13,
                0.7,
                0.72,
                0.71,
                0.73,
                0.12,
                0.14,
                0.13,
                0.15,
                0.68,
                0.70,
                0.69,
                0.71,
                0.15,
                0.17,
                0.16,
                0.18,
                0.66,
                0.68,
                0.67,
                0.69,
            ],
            "light": [0.0, 0.0, 0.0, 0.0, 3.5, 3.5, 3.5, 3.5] * 3,
        }
    )

    quality_audit = pipeline.audit_year_quality(df)
    scored, model_info = pipeline.score_panel(df, quality_audit)

    assert scored["time_grain"].eq("annual").all()
    assert scored.groupby(["grid_id", "source_year"]).size().eq(1).all()
    assert scored["quality_flag"].eq("annual_ntl_replicated").all()
    assert scored["rvri"].notna().all()
    assert scored.groupby("source_year")["rvri"].agg(["min", "max"]).equals(
        pd.DataFrame({"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]}, index=[2019, 2020, 2021])
    )

    expected_features = ["stock_pressure", "eco_deficit", "mismatch_gap"]
    assert model_info["features"] == expected_features
    assert all(model_info["loadings"][feature] > 0 for feature in expected_features)


def test_clean_light_series_converts_extreme_sentinels_to_nan():
    pipeline = load_pipeline_module()

    raw = pd.Series([0.5, -3.4028235e38, np.inf, -np.inf, 1.2])
    cleaned = pipeline.clean_light_series(raw)

    assert cleaned.isna().sum() == 3
    assert cleaned.iloc[0] == 0.5
    assert cleaned.iloc[-1] == 1.2
