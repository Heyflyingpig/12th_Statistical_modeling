from __future__ import annotations

from typing import Any

import pandas as pd


ANALYSIS_DOMAIN_NAME = "loose_builtup"
ANALYSIS_DOMAIN_NDBI_QUANTILE = 0.60
ANALYSIS_DOMAIN_MIN_NDVI = 0.05


def infer_year_column(frame: pd.DataFrame) -> str:
    for column in ("source_year", "year"):
        if column in frame.columns:
            return column
    raise ValueError("Data frame must contain either source_year or year.")


def attach_unified_analysis_domain(
    frame: pd.DataFrame,
    *,
    year_col: str | None = None,
    ndbi_quantile: float = ANALYSIS_DOMAIN_NDBI_QUANTILE,
    min_ndvi: float = ANALYSIS_DOMAIN_MIN_NDVI,
    domain_name: str = ANALYSIS_DOMAIN_NAME,
) -> pd.DataFrame:
    """Mark the paper-facing spatial analysis sample used by Q1 and Q3.

    The rule intentionally matches the former Q1 khaki display layer: a
    year-specific loose built-up context defined by NDBI and a light NDVI
    exclusion. It is broad enough for paper maps and state-transition work,
    while still excluding the least relevant non-built background cells.
    """
    year_col = year_col or infer_year_column(frame)
    result = frame.copy()
    result["analysis_domain"] = "outside_domain"
    result["in_analysis_domain"] = False
    result["analysis_domain_ndbi_threshold"] = pd.NA
    result["analysis_domain_min_ndvi"] = min_ndvi

    required = [year_col, "rvri", "ndbi", "ndvi"]
    working = result.dropna(subset=required).copy()
    for year, group in working.groupby(year_col, dropna=True):
        threshold = float(group["ndbi"].quantile(ndbi_quantile))
        mask = (
            result[year_col].eq(year)
            & result["rvri"].notna()
            & result["ndbi"].ge(threshold)
            & result["ndvi"].ge(min_ndvi)
        )
        result.loc[mask, "analysis_domain"] = domain_name
        result.loc[mask, "in_analysis_domain"] = True
        result.loc[result[year_col].eq(year), "analysis_domain_ndbi_threshold"] = threshold

    return result


def summarize_unified_analysis_domain(
    frame: pd.DataFrame,
    *,
    year_col: str | None = None,
    domain_name: str = ANALYSIS_DOMAIN_NAME,
) -> dict[str, Any]:
    year_col = year_col or infer_year_column(frame)
    domain = frame[frame["analysis_domain"].eq(domain_name)].copy()
    yearly = []
    for year, group in domain.groupby(year_col, dropna=True):
        yearly.append(
            {
                "year": int(year),
                "domain_rows": int(len(group)),
                "ndbi_threshold": float(group["analysis_domain_ndbi_threshold"].dropna().iloc[0])
                if group["analysis_domain_ndbi_threshold"].notna().any()
                else None,
            }
        )
    return {
        "domain_name": domain_name,
        "rule": {
            "ndbi_quantile": ANALYSIS_DOMAIN_NDBI_QUANTILE,
            "min_ndvi": ANALYSIS_DOMAIN_MIN_NDVI,
            "settlement_context_required": False,
        },
        "total_domain_rows": int(len(domain)),
        "yearly": yearly,
    }
