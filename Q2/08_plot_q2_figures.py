from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


TYPE_LABELS = {
    0: "稳定占用型",
    1: "老城衰退型空置",
    2: "新区扩张型空置",
    3: "过渡混合型",
}

TYPE_COLORS = {
    0: "#d9dde3",
    1: "#b24a3a",
    2: "#2f6c9f",
    3: "#d4a64a",
}

FOCUS_COLORS = {
    1: "#c4553d",
    2: "#3e7cb1",
}

DISTRICT_PREFERRED_COLUMNS = [
    "district_name_official",
    "district_name_y",
    "district_name_x",
    "district_name_grid",
]


def parse_args() -> argparse.Namespace:
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"

    parser = argparse.ArgumentParser(description="Generate Q2 publication-ready figures.")
    parser.add_argument(
        "--map",
        type=Path,
        default=output_dir / "final" / "Q2_Type_Map.geojson",
        help="Final Q2 type GeoJSON.",
    )
    parser.add_argument(
        "--districts",
        type=Path,
        default=q2_dir.parent / "Q1" / "data" / "shaoguan_districts_official.json",
        help="District boundary file.",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=output_dir,
        help="Directory for exported figures.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Output figure DPI.",
    )
    return parser.parse_args()


def configure_matplotlib() -> str:
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
    ]
    available = {font.name for font in font_manager.fontManager.ttflist}
    font_name = next((name for name in candidates if name in available), "DejaVu Sans")

    plt.rcParams["font.family"] = font_name
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"
    plt.rcParams["savefig.facecolor"] = "white"
    return font_name


def load_layers(map_path: Path, districts_path: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    q2_map = gpd.read_file(map_path)
    districts = gpd.read_file(districts_path)

    if q2_map.crs is None:
        q2_map = q2_map.set_crs("EPSG:4326")
    if districts.crs is None:
        districts = districts.set_crs("EPSG:4326")

    q2_map = q2_map.to_crs("EPSG:4326")
    districts = districts.to_crs(q2_map.crs)
    return q2_map, districts


def add_district_name(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = frame.copy()
    district_series = None
    for column in DISTRICT_PREFERRED_COLUMNS:
        if column in result.columns:
            if district_series is None:
                district_series = result[column].astype("string")
            else:
                district_series = district_series.fillna(result[column].astype("string"))
    if district_series is None:
        raise ValueError("No district name column found in Q2 map.")
    result["district_name"] = district_series.fillna("未识别区")
    return result


def add_type_fields(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = frame.copy()
    result["q2_type"] = pd.to_numeric(result["q2_type"], errors="coerce").fillna(0).astype(int)
    result["q2_label"] = result["q2_type"].map(TYPE_LABELS).fillna(result.get("q2_label", "未分类"))
    result["plot_color"] = result["q2_type"].map(TYPE_COLORS).fillna("#cccccc")
    return result


def add_focus_fields(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = frame.copy()
    result["focus_color"] = np.where(
        result["q2_type"] == 1,
        FOCUS_COLORS[1],
        np.where(result["q2_type"] == 2, FOCUS_COLORS[2], "#e6e6e6"),
    )
    result["focus_alpha"] = np.where(result["q2_type"].isin([1, 2]), 0.95, 0.22)
    return result


def annotate_districts(ax: plt.Axes, districts: gpd.GeoDataFrame) -> None:
    centroids = districts.to_crs(3857).centroid.to_crs(districts.crs)
    for (_, row), point in zip(districts.iterrows(), centroids, strict=False):
        label = row.get("name")
        if not label:
            continue
        ax.text(
            point.x,
            point.y,
            label,
            fontsize=8,
            color="#444444",
            ha="center",
            va="center",
            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.75},
            zorder=5,
        )


def style_map_axes(ax: plt.Axes, title: str, subtitle: str) -> None:
    ax.set_title(f"{title}\n{subtitle}", fontsize=16, fontweight="bold", loc="left", pad=14)
    ax.set_axis_off()


def save_figure(fig: plt.Figure, path: Path, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_overall_map(
    q2_map: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    output_path: Path,
    dpi: int,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 12))
    q2_map.plot(ax=ax, color=q2_map["plot_color"], linewidth=0)
    districts.boundary.plot(ax=ax, color="#525252", linewidth=0.8, zorder=4)
    annotate_districts(ax, districts)
    style_map_axes(ax, "Q2 四分类空间格局图", "基于 2019-2023 年格网识别结果")

    handles = [Patch(facecolor=TYPE_COLORS[key], edgecolor="none", label=TYPE_LABELS[key]) for key in sorted(TYPE_LABELS)]
    ax.legend(
        handles=handles,
        title="Q2 类型",
        loc="lower left",
        frameon=False,
        fontsize=10,
        title_fontsize=11,
    )
    save_figure(fig, output_path, dpi)


def plot_focus_map(
    q2_map: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    output_path: Path,
    dpi: int,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 12))
    for type_code in [0, 3, 1, 2]:
        subset = q2_map[q2_map["q2_type"] == type_code]
        if subset.empty:
            continue
        subset.plot(
            ax=ax,
            color=subset["focus_color"],
            linewidth=0,
            alpha=float(subset["focus_alpha"].iloc[0]),
        )
    districts.boundary.plot(ax=ax, color="#4d4d4d", linewidth=0.85, zorder=4)
    annotate_districts(ax, districts)
    style_map_axes(ax, "Q2 重点空置类型对比图", "突出老城衰退型空置与新区扩张型空置")

    handles = [
        Patch(facecolor=FOCUS_COLORS[1], edgecolor="none", label="老城衰退型空置"),
        Patch(facecolor=FOCUS_COLORS[2], edgecolor="none", label="新区扩张型空置"),
        Patch(facecolor="#e6e6e6", edgecolor="none", label="其他类型（弱化显示）"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=10)
    save_figure(fig, output_path, dpi)


def build_district_summary(q2_map: gpd.GeoDataFrame) -> pd.DataFrame:
    summary = (
        q2_map.groupby(["district_name", "q2_type"], dropna=False)
        .size()
        .rename("grid_count")
        .reset_index()
    )
    summary["q2_label"] = summary["q2_type"].map(TYPE_LABELS)

    total = summary.groupby("district_name")["grid_count"].sum().rename("district_total")
    summary = summary.merge(total, on="district_name", how="left")
    summary["share"] = summary["grid_count"] / summary["district_total"]
    return summary


def plot_district_share_chart(summary: pd.DataFrame, output_path: Path, dpi: int) -> None:
    pivot = (
        summary.pivot(index="district_name", columns="q2_type", values="share")
        .fillna(0)
        .reindex(columns=sorted(TYPE_LABELS))
    )
    totals = summary.groupby("district_name")["district_total"].first().sort_values(ascending=False)
    pivot = pivot.loc[totals.index]

    fig, ax = plt.subplots(figsize=(12, 8))
    left = np.zeros(len(pivot))
    y = np.arange(len(pivot))

    for type_code in sorted(TYPE_LABELS):
        values = pivot[type_code].to_numpy()
        ax.barh(
            y,
            values,
            left=left,
            color=TYPE_COLORS[type_code],
            edgecolor="white",
            linewidth=0.8,
            label=TYPE_LABELS[type_code],
        )
        left += values

    ax.set_yticks(y)
    ax.set_yticklabels(pivot.index, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("类型占比", fontsize=11)
    ax.set_title("各区县 Q2 类型结构占比图", fontsize=16, fontweight="bold", loc="left", pad=14)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    ax.grid(axis="x", color="#d9d9d9", linestyle="--", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)

    totals_text = [
        Line2D([0], [0], color="none", label=f"{name}: {int(totals.loc[name])} 格")
        for name in pivot.index[:3]
    ]
    legend_main = ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=4,
        frameon=False,
        fontsize=10,
    )
    ax.add_artist(legend_main)
    ax.legend(handles=totals_text, loc="upper right", frameon=False, fontsize=9, title="样本量提示")

    save_figure(fig, output_path, dpi)


def write_manifest(summary: pd.DataFrame, figures_dir: Path, font_name: str) -> Path:
    counts = (
        summary.groupby("q2_type", as_index=False)["grid_count"]
        .sum()
        .assign(q2_label=lambda df: df["q2_type"].map(TYPE_LABELS))
        .sort_values("q2_type")
    )
    payload = {
        "font_family": font_name,
        "figures_dir": str(figures_dir),
        "overall_counts": counts.to_dict(orient="records"),
        "districts": sorted(summary["district_name"].unique().tolist()),
        "generated_files": [
            "Q2_Typology_Map_Overall.png",
            "Q2_Typology_Map_Focus.png",
            "Q2_Typology_Share_By_District.png",
        ],
    }
    manifest_path = figures_dir / "Q2_Figure_Manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    args = parse_args()
    figures_dir = args.figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)

    font_name = configure_matplotlib()
    q2_map, districts = load_layers(args.map, args.districts)
    q2_map = add_district_name(q2_map)
    q2_map = add_type_fields(q2_map)
    q2_map = add_focus_fields(q2_map)

    plot_overall_map(
        q2_map=q2_map,
        districts=districts,
        output_path=figures_dir / "Q2_Typology_Map_Overall.png",
        dpi=args.dpi,
    )
    plot_focus_map(
        q2_map=q2_map,
        districts=districts,
        output_path=figures_dir / "Q2_Typology_Map_Focus.png",
        dpi=args.dpi,
    )

    district_summary = build_district_summary(q2_map)
    plot_district_share_chart(
        summary=district_summary,
        output_path=figures_dir / "Q2_Typology_Share_By_District.png",
        dpi=args.dpi,
    )
    district_summary.to_csv(figures_dir / "Q2_Typology_Share_By_District.csv", index=False, encoding="utf-8-sig")

    manifest_path = write_manifest(district_summary, figures_dir, font_name)

    print(f"图件输出目录: {figures_dir}")
    print(f"使用字体: {font_name}")
    print(f"总图: {figures_dir / 'Q2_Typology_Map_Overall.png'}")
    print(f"重点图: {figures_dir / 'Q2_Typology_Map_Focus.png'}")
    print(f"区县统计图: {figures_dir / 'Q2_Typology_Share_By_District.png'}")
    print(f"区县汇总表: {figures_dir / 'Q2_Typology_Share_By_District.csv'}")
    print(f"清单: {manifest_path}")


if __name__ == "__main__":
    main()
