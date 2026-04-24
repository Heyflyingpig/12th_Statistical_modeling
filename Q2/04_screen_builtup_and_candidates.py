from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from analysis_domain import ANALYSIS_DOMAIN_MIN_NDVI, ANALYSIS_DOMAIN_NDBI_QUANTILE
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

DEFAULT_RESIDENTIAL_MIN_NDVI = ANALYSIS_DOMAIN_MIN_NDVI


def parse_args() -> argparse.Namespace:
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"

    parser = argparse.ArgumentParser(
        description="Screen built-up grids and vacancy candidates for Q2.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Input feature table. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=output_dir / "Q2_CandidateTable.csv",
        help="Output path for the screened candidate table.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=output_dir / "logs" / "04_screen_builtup_and_candidates.json",
        help="Output path for the step log.",
    )
    return parser.parse_args()


def resolve_input(user_input: Path | None, output_dir: Path) -> Path:
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
        raise FileNotFoundError("Could not find the Q2 feature table.")
    return path


def load_features(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Input feature table is missing required columns: {missing}")
    return frame


def compute_thresholds(frame: pd.DataFrame) -> dict[str, float]:
    valid = frame.copy()
    return {
        "analysis_domain_ndbi_q60": float(valid["ndbi_2023"].quantile(ANALYSIS_DOMAIN_NDBI_QUANTILE)),
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
    screened = frame.copy()
    builtup_flag = (
        screened["ndbi_2023"].ge(thresholds["analysis_domain_ndbi_q60"])
        & screened["ndvi_2023"].ge(DEFAULT_RESIDENTIAL_MIN_NDVI)
    )

    residential_flag = builtup_flag.copy()

    vacancy_candidate_flag = residential_flag & (
        (screened["risk_state_2023"] >= thresholds["risk_state_medium"])
        | (screened["rvri_2023"] >= thresholds["rvri_2023_q65"])
        | (screened["risk_high_freq"] >= max(0.4, thresholds["risk_high_freq_q65"]))
        | (screened["mismatch_mean"] >= thresholds["mismatch_mean_q65"])
    )

    screened["builtup_flag"] = builtup_flag
    screened["residential_flag"] = residential_flag
    screened["analysis_domain"] = np.where(residential_flag, "loose_builtup", "outside_domain")
    screened["in_analysis_domain"] = residential_flag
    screened["vacancy_candidate_flag"] = vacancy_candidate_flag
    screened["screen_status"] = np.where(
        ~screened["builtup_flag"],
        "non_built_filtered",
        np.where(
            ~screened["residential_flag"],
            "non_residential_filtered",
            np.where(screened["vacancy_candidate_flag"], "vacancy_candidate", "stable_candidate"),
        ),
    )
    return screened


def main() -> None:
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
        "residential_rows": int(candidates["residential_flag"].sum()),
        "candidate_rows": int(candidates["vacancy_candidate_flag"].sum()),
        "stable_rows": int((candidates["screen_status"] == "stable_candidate").sum()),
        "non_residential_rows": int((candidates["screen_status"] == "non_residential_filtered").sum()),
        "non_built_rows": int((candidates["screen_status"] == "non_built_filtered").sum()),
        "thresholds": thresholds,
        "warnings": [],
    }
    write_step_log(args.log, stats)

    print("Q2 step 4 completed.")
    print(f"- Input file: {input_path}")
    print(f"- Output file: {args.output}")
    print(f"- Total rows: {len(features)}")
    print(f"- Built-up rows: {stats['builtup_rows']}")
    print(f"- Residential built-up rows: {stats['residential_rows']}")
    print(f"- Vacancy candidate rows: {stats['candidate_rows']}")
    print(f"- Stable residential control rows: {stats['stable_rows']}")
    print(f"- Built-up but non-residential rows: {stats['non_residential_rows']}")
    print(f"- Non-built filtered rows: {stats['non_built_rows']}")


if __name__ == "__main__":
    main()
