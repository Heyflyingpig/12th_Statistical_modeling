from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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
    "district_name",
]


def parse_args() -> argparse.Namespace:
    q2_dir = Path(__file__).resolve().parent
    output_dir = q2_dir / "output"
    parser = argparse.ArgumentParser(description="Generate Q2 publication-ready figures.")
    parser.add_argument("--map", type=Path, default=output_dir / "final" / "Q2_Type_Map.geojson")
    parser.add_argument("--districts", type=Path, default=q2_dir.parent / "Q1" / "data" / "shaoguan_districts_official.json")
    parser.add_argument("--figures-dir", type=Path, default=output_dir)
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def configure_matplotlib() -> str:
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS"]
    available = {font.name for font in font_manager.fontManager.ttflist}
    font_name = next((name for name in candidates if name in available), "DejaVu Sans")
    plt.rcParams["font.family"] = font_name
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"
    plt.rcParams["savefig.facecolor"] = "white"
    return font_name


def polygon_center(geometry: dict[str, Any]) -> tuple[float, float]:
    if geometry["type"] == "Polygon":
        ring = np.asarray(geometry["coordinates"][0], dtype=float)
    elif geometry["type"] == "MultiPolygon":
        ring = np.asarray(geometry["coordinates"][0][0], dtype=float)
    else:
        point = np.asarray(geometry["coordinates"][:2], dtype=float)
        return float(point[0]), float(point[1])
    center = ring.mean(axis=0)
    return float(center[0]), float(center[1])


def read_feature_table(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for feature in data.get("features", []):
        props = dict(feature.get("properties", {}))
        cx, cy = polygon_center(feature["geometry"])
        props["cx"] = cx
        props["cy"] = cy
        rows.append(props)
    return pd.DataFrame(rows)


def read_district_layers(path: Path) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rings: list[pd.DataFrame] = []
    labels = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geometry = feature["geometry"]
        parts = []
        if geometry["type"] == "Polygon":
            parts = [geometry["coordinates"][0]]
        elif geometry["type"] == "MultiPolygon":
            parts = [polygon[0] for polygon in geometry["coordinates"]]
        part_centers = []
        for part in parts:
            ring = pd.DataFrame(part, columns=["x", "y"])
            rings.append(ring)
            part_centers.append(ring[["x", "y"]].mean())
        if part_centers:
            center = pd.DataFrame(part_centers).mean()
            labels.append({"name": props.get("name", ""), "x": center["x"], "y": center["y"]})
    return rings, pd.DataFrame(labels)


def add_district_name(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    district_series = None
    for column in DISTRICT_PREFERRED_COLUMNS:
        if column in result.columns:
            if district_series is None:
                district_series = result[column].astype("string")
            else:
                district_series = district_series.fillna(result[column].astype("string"))
    if district_series is None:
        result["district_name"] = "未识别区"
    else:
        result["district_name"] = district_series.fillna("未识别区")
    return result


def add_type_fields(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["q2_type"] = pd.to_numeric(result["q2_type"], errors="coerce").fillna(0).astype(int)
    result["q2_label"] = result["q2_type"].map(TYPE_LABELS).fillna(result.get("q2_label", "未分类"))
    result["plot_color"] = result["q2_type"].map(TYPE_COLORS).fillna("#cccccc")
    result["focus_color"] = np.where(
        result["q2_type"] == 1,
        FOCUS_COLORS[1],
        np.where(result["q2_type"] == 2, FOCUS_COLORS[2], "#e6e6e6"),
    )
    result["focus_alpha"] = np.where(result["q2_type"].isin([1, 2]), 0.95, 0.22)
    return result


def draw_boundaries(ax: plt.Axes, rings: list[pd.DataFrame]) -> None:
    for ring in rings:
        ax.plot(ring["x"], ring["y"], color="#000000", linewidth=0.85, alpha=0.95, zorder=5)


def annotate_districts(ax: plt.Axes, labels: pd.DataFrame) -> None:
    for row in labels.itertuples(index=False):
        if not row.name:
            continue
        ax.text(
            row.x,
            row.y,
            row.name,
            fontsize=8,
            color="#444444",
            ha="center",
            va="center",
            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.75},
            zorder=6,
        )


def save_figure(fig: plt.Figure, path: Path, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_overall_map(q2_map: pd.DataFrame, rings: list[pd.DataFrame], labels: pd.DataFrame, output_path: Path, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.scatter(q2_map["cx"], q2_map["cy"], s=2.2, c=q2_map["plot_color"], linewidths=0, alpha=0.82)
    draw_boundaries(ax, rings)
    annotate_districts(ax, labels)
    ax.set_axis_off()
    ax.set_aspect("equal", adjustable="box")
    handles = [Patch(facecolor=TYPE_COLORS[key], edgecolor="none", label=TYPE_LABELS[key]) for key in sorted(TYPE_LABELS)]
    ax.legend(handles=handles, title="Q2 类型", loc="lower left", frameon=False, fontsize=10, title_fontsize=11)
    save_figure(fig, output_path, dpi)


def plot_focus_map(q2_map: pd.DataFrame, rings: list[pd.DataFrame], labels: pd.DataFrame, output_path: Path, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(12, 12))
    for type_code in [0, 3, 1, 2]:
        subset = q2_map[q2_map["q2_type"] == type_code]
        if subset.empty:
            continue
        ax.scatter(subset["cx"], subset["cy"], s=2.2, c=subset["focus_color"], alpha=float(subset["focus_alpha"].iloc[0]), linewidths=0)
    draw_boundaries(ax, rings)
    annotate_districts(ax, labels)
    ax.set_axis_off()
    ax.set_aspect("equal", adjustable="box")
    handles = [
        Patch(facecolor=FOCUS_COLORS[1], edgecolor="none", label="老城衰退型空置"),
        Patch(facecolor=FOCUS_COLORS[2], edgecolor="none", label="新区扩张型空置"),
        Patch(facecolor="#e6e6e6", edgecolor="none", label="其他类型（弱化显示）"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=10)
    save_figure(fig, output_path, dpi)


def build_district_summary(q2_map: pd.DataFrame) -> pd.DataFrame:
    summary = q2_map.groupby(["district_name", "q2_type"], dropna=False).size().rename("grid_count").reset_index()
    summary["q2_label"] = summary["q2_type"].map(TYPE_LABELS)
    total = summary.groupby("district_name")["grid_count"].sum().rename("district_total")
    summary = summary.merge(total, on="district_name", how="left")
    summary["share"] = summary["grid_count"] / summary["district_total"]
    return summary


def plot_district_share_chart(summary: pd.DataFrame, output_path: Path, dpi: int) -> None:
    pivot = summary.pivot(index="district_name", columns="q2_type", values="share").fillna(0).reindex(columns=sorted(TYPE_LABELS))
    totals = summary.groupby("district_name")["district_total"].first().sort_values(ascending=False)
    pivot = pivot.loc[totals.index]

    fig, ax = plt.subplots(figsize=(12, 8))
    left = np.zeros(len(pivot))
    y = np.arange(len(pivot))
    for type_code in sorted(TYPE_LABELS):
        values = pivot[type_code].to_numpy()
        ax.barh(y, values, left=left, color=TYPE_COLORS[type_code], edgecolor="white", linewidth=0.8, label=TYPE_LABELS[type_code])
        left += values

    ax.set_yticks(y)
    ax.set_yticklabels(pivot.index, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("类型占比", fontsize=11)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    ax.grid(axis="x", color="#d9d9d9", linestyle="--", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)

    totals_text = [Line2D([0], [0], color="none", label=f"{name}: {int(totals.loc[name])} 格") for name in pivot.index[:3]]
    legend_main = ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), ncol=4, frameon=False, fontsize=10)
    ax.add_artist(legend_main)
    ax.legend(handles=totals_text, loc="upper right", frameon=False, fontsize=9, title="样本量提示")
    save_figure(fig, output_path, dpi)


def write_manifest(summary: pd.DataFrame, figures_dir: Path, font_name: str) -> Path:
    counts = summary.groupby("q2_type", as_index=False)["grid_count"].sum().assign(q2_label=lambda df: df["q2_type"].map(TYPE_LABELS)).sort_values("q2_type")
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
    rings, labels = read_district_layers(args.districts)
    q2_map = add_type_fields(add_district_name(read_feature_table(args.map)))

    plot_overall_map(q2_map, rings, labels, figures_dir / "Q2_Typology_Map_Overall.png", args.dpi)
    plot_focus_map(q2_map, rings, labels, figures_dir / "Q2_Typology_Map_Focus.png", args.dpi)
    district_summary = build_district_summary(q2_map)
    plot_district_share_chart(district_summary, figures_dir / "Q2_Typology_Share_By_District.png", args.dpi)
    district_summary.to_csv(figures_dir / "Q2_Typology_Share_By_District.csv", index=False, encoding="utf-8-sig")
    manifest_path = write_manifest(district_summary, figures_dir, font_name)

    print(f"图件输出目录: {figures_dir}")
    print(f"使用字体: {font_name}")
    print(f"清单: {manifest_path}")


if __name__ == "__main__":
    main()
