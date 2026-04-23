from __future__ import annotations

import json
from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
Q1_DIR = BASE_DIR / "Q1"
OUTPUT_DIR = Q1_DIR / "output"
BY_YEAR_DIR = OUTPUT_DIR / "by_year"

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def build_annual_evolution_summary() -> Path:
    summary = json.loads((BY_YEAR_DIR / "by_year_summary.json").read_text(encoding="utf-8"))
    metrics = pd.DataFrame(summary["year_summaries"])

    validated = pd.read_csv(OUTPUT_DIR / "Shaoguan_RVRI_Q1_Validated.csv")
    rvri_means = (
        validated.groupby("source_year", as_index=False)["rvri"]
        .mean()
        .rename(columns={"source_year": "year", "rvri": "rvri_mean"})
    )

    merged = metrics.merge(rvri_means, on="year", how="left").sort_values("year")

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()

    ax1.plot(
        merged["year"],
        merged["rvri_mean"],
        color="#d62728",
        marker="o",
        linewidth=2.5,
        label="RVRI mean",
    )
    ax2.plot(
        merged["year"],
        merged["spatial_moran_i"],
        color="#1f77b4",
        marker="s",
        linewidth=2.5,
        label="Global Moran's I",
    )

    for row in merged.itertuples(index=False):
        ax1.text(row.year, row.rvri_mean + 0.006, f"{row.rvri_mean:.3f}", ha="center", va="bottom", fontsize=9)
        ax2.text(
            row.year,
            row.spatial_moran_i + 0.008,
            f"{row.spatial_moran_i:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#1f77b4",
        )

    ax1.set_xlabel("Year")
    ax1.set_ylabel("RVRI mean", color="#d62728")
    ax2.set_ylabel("Global Moran's I", color="#1f77b4")
    ax1.set_xticks(merged["year"])
    ax1.grid(True, axis="y", linestyle="--", alpha=0.3)
    ax1.set_title("Q1 Annual Evolution Summary (2019-2023)")

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="upper left")

    fig.tight_layout()
    output_path = OUTPUT_DIR / "Q1_Annual_Evolution_Summary.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path


def build_lisa_comparison() -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    years = [2019, 2023]

    for ax, year in zip(axes, years):
        image_path = BY_YEAR_DIR / str(year) / "Q1_LISA_Map.png"
        image = mpimg.imread(image_path)
        ax.imshow(image)
        ax.set_title(f"LISA clusters in {year}")
        ax.axis("off")

    fig.suptitle("Q1 Residential-Risk Spatial Cluster Comparison: 2019 vs 2023", fontsize=16)
    fig.tight_layout()
    output_path = OUTPUT_DIR / "Q1_LISA_Comparison_2019_2023.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path


def build_district_risk_profile() -> Path:
    # Values match the residential-candidate summary used in the paper table.
    district_rows = [
        ("南雄市", 859, 1.9711, 0.8766, 0.6206),
        ("始兴县", 848, 2.1635, 0.6050, 0.5857),
        ("翁源县", 1334, 2.3492, 0.4490, 0.5584),
        ("乳源瑶族自治县", 733, 2.5009, 0.3479, 0.5440),
        ("仁化县", 714, 1.9743, 0.2983, 0.5483),
        ("乐昌市", 1086, 2.1099, 0.2974, 0.5422),
        ("浈江区", 752, 4.6847, 0.2101, 0.5228),
        ("武江区", 639, 7.5738, 0.2081, 0.4966),
        ("新丰县", 417, 4.8260, 0.1990, 0.5080),
        ("曲江区", 993, 4.4529, 0.1772, 0.5194),
        ("边缘争议区", 30, 1.6526, 0.1333, 0.5395),
    ]
    profile = pd.DataFrame(
        district_rows,
        columns=["district_name", "candidate_rows", "mean_light", "hh_share", "mean_rvri"],
    ).sort_values("mean_rvri", ascending=True)

    fig, ax1 = plt.subplots(figsize=(10, 7))
    ax2 = ax1.twiny()

    ax1.barh(profile["district_name"], profile["mean_rvri"], color="#d95f02", alpha=0.85, label="Mean RVRI")
    ax2.plot(profile["hh_share"], profile["district_name"], color="#1b9e77", marker="o", linewidth=2.2, label="HH share")

    for row in profile.itertuples(index=False):
        ax1.text(row.mean_rvri + 0.005, row.district_name, f"{row.mean_rvri:.3f}", va="center", fontsize=9)
        ax2.text(row.hh_share + 0.01, row.district_name, f"{row.hh_share:.2f}", va="center", fontsize=9, color="#1b9e77")

    ax1.set_xlabel("Mean RVRI")
    ax2.set_xlabel("HH share")
    ax1.set_title("Q1 District Risk Profile in 2023")
    ax1.grid(True, axis="x", linestyle="--", alpha=0.3)

    output_path = OUTPUT_DIR / "Q1_District_Risk_Profile_2023.png"
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> None:
    summary_path = build_annual_evolution_summary()
    comparison_path = build_lisa_comparison()
    district_path = build_district_risk_profile()
    print(f"Saved annual evolution figure to: {summary_path}")
    print(f"Saved LISA comparison figure to: {comparison_path}")
    print(f"Saved district profile figure to: {district_path}")


if __name__ == "__main__":
    main()
