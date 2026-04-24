from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd


def load_prediction_module():
    module_path = Path(__file__).resolve().parents[2] / "Q3" / "06_low_to_high_predict.py"
    spec = spec_from_file_location("q3_prediction", module_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_upgrade_candidates_uses_non_high_to_high_target():
    module = load_prediction_module()
    transition = pd.DataFrame(
        {
            "grid_id": ["g0", "g1", "g2", "g3"],
            "year": [2022, 2022, 2022, 2022],
            "risk_state": [0, 1, 2, 1],
            "next_risk_state": [2, 2, 2, 0],
        }
    )

    candidates = module.build_upgrade_candidates(transition)

    assert candidates["grid_id"].tolist() == ["g0", "g1", "g3"]
    assert candidates["non_high_to_high_event"].tolist() == [1, 1, 0]


def test_build_state_projection_outputs_all_three_state_shares():
    module = load_prediction_module()
    panel = pd.DataFrame(
        {
            "grid_id": ["g0", "g1", "g2", "g3"],
            "district_name": ["A", "A", "A", "A"],
            "year": [2023, 2023, 2023, 2023],
            "risk_state": [0, 1, 1, 2],
        }
    )
    transition = pd.DataFrame(
        {
            "district_name": ["A"] * 6,
            "risk_state": [0, 0, 1, 1, 2, 2],
            "next_risk_state": [1, 2, 1, 2, 1, 2],
        }
    )

    projection = module.build_state_projection(panel, transition, base_year=2023, horizon_years=3)

    assert set(["low_share", "mid_share", "high_share"]).issubset(projection.columns)
    assert projection["horizon"].tolist() == [0, 1, 2, 3]
    assert projection.loc[projection["horizon"].eq(0), "high_share"].iloc[0] == 0.25
    assert projection[["low_share", "mid_share", "high_share"]].sum(axis=1).round(6).eq(1.0).all()
