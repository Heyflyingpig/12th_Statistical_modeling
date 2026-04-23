from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
except ModuleNotFoundError as exc:
    if exc.name == "geopandas":
        print("当前解释器未安装 geopandas。")
        print(f"你现在使用的是: {sys.executable}")
        print("请改用项目环境运行：")
        print(
            r"D:\统计建模比赛\.conda\Scripts\python.exe d:\统计建模比赛\12th_Statistical_modeling\Q2\02_enrich_spatial_context.py"
        )
        raise SystemExit(1)
    raise


PROJECTED_CRS = "EPSG:4511"
GEOGRAPHIC_CRS = "EPSG:4326"
BASE_REQUIRED_COLUMNS = [
    "grid_id",
    "district_name",
    "source_year",
    "rvri",
    "risk_state",
    "stock_pressure",
    "mismatch_gap",
    "ndbi",
    "light",
    "ndvi",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    base_dir = Path(__file__).resolve().parent.parent
    q2_output_dir = base_dir / "Q2" / "output"

    parser = argparse.ArgumentParser(
        description="为 Q2 基础面板补充 geometry、POI 与本地核心区位特征。"
    )
    parser.add_argument(
        "--base-panel",
        type=Path,
        default=q2_output_dir / "Q2_BasePanel_2019_2023.csv",
        help="Q2 基础面板路径。",
    )
    parser.add_argument(
        "--grid",
        type=Path,
        default=base_dir / "Q1" / "data" / "scientific_grid_500m.geojson",
        help="500m 格网路径。",
    )
    parser.add_argument(
        "--districts",
        type=Path,
        default=base_dir / "Q1" / "data" / "shaoguan_districts_official.json",
        help="官方区县边界路径。",
    )
    parser.add_argument(
        "--pois",
        type=Path,
        default=base_dir / "Q1" / "data" / "pois_cache.geojson",
        help="POI 数据路径。",
    )
    parser.add_argument(
        "--output-geojson",
        type=Path,
        default=q2_output_dir / "Q2_BasePanel_Spatial_2019_2023.geojson",
        help="空间面板 GeoJSON 输出路径。",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=q2_output_dir / "Q2_BasePanel_Spatial_2019_2023.csv",
        help="空间面板 CSV 输出路径。",
    )
    return parser.parse_args()


def validate_paths(paths: list[Path]) -> None:
    """检查输入文件是否存在。"""
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"以下输入文件不存在: {missing}")


def validate_columns(frame: pd.DataFrame, required_columns: list[str], name: str) -> None:
    """检查字段是否齐全。"""
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} 缺少必要字段: {missing}")


def load_base_panel(path: Path) -> pd.DataFrame:
    """读取 Q2 基础面板。"""
    panel = pd.read_csv(path)
    validate_columns(panel, BASE_REQUIRED_COLUMNS, "Q2 基础面板")
    panel["grid_id"] = panel["grid_id"].astype(str).str.strip()
    panel["district_name"] = panel["district_name"].astype(str).str.strip()
    panel["source_year"] = pd.to_numeric(panel["source_year"], errors="raise").astype(int)
    return panel


def load_grid(path: Path) -> gpd.GeoDataFrame:
    """读取 500m 格网。"""
    grid = gpd.read_file(path)
    validate_columns(grid, ["grid_id", "district", "geometry"], "500m 格网")
    grid["grid_id"] = grid["grid_id"].astype(str).str.strip()
    grid["district"] = grid["district"].astype(str).str.strip()
    if grid.crs is None:
        grid = grid.set_crs(GEOGRAPHIC_CRS)
    return grid


def load_districts(path: Path) -> gpd.GeoDataFrame:
    """读取官方区县边界。"""
    districts = gpd.read_file(path)
    validate_columns(districts, ["name", "geometry"], "官方区县边界")
    districts = districts[["name", "geometry"]].rename(columns={"name": "district_name_official"}).copy()
    if districts.crs is None:
        districts = districts.set_crs(GEOGRAPHIC_CRS)
    return districts


def load_pois(path: Path) -> gpd.GeoDataFrame:
    """读取 POI 数据。"""
    pois = gpd.read_file(path)
    validate_columns(pois, ["geometry"], "POI 数据")
    if pois.crs is None:
        pois = pois.set_crs(GEOGRAPHIC_CRS)
    return pois


def attach_geometry(panel: pd.DataFrame, grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """按 grid_id 关联格网 geometry。"""
    grid_subset = grid[["grid_id", "district", "geometry"]].copy()
    merged = panel.merge(grid_subset, on="grid_id", how="left", validate="many_to_one")
    missing_geometry = int(merged["geometry"].isna().sum())
    if missing_geometry > 0:
        raise ValueError(f"有 {missing_geometry} 条记录未匹配到 geometry。")
    gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=grid.crs)
    gdf = gdf.rename(columns={"district": "district_name_grid"})
    return gdf


def attach_official_districts(gdf: gpd.GeoDataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """用格网质心核对官方区县归属。"""
    centroid_gdf = gdf[["grid_id", "geometry"]].drop_duplicates("grid_id").copy()
    centroid_gdf = centroid_gdf.to_crs(PROJECTED_CRS)
    centroid_gdf = centroid_gdf.set_geometry(centroid_gdf.geometry.centroid)
    centroid_gdf = centroid_gdf.to_crs(districts.crs)

    district_join = gpd.sjoin(
        centroid_gdf,
        districts[["district_name_official", "geometry"]],
        how="left",
        predicate="within",
    )
    district_join = district_join[["grid_id", "district_name_official"]].drop_duplicates("grid_id")

    enriched = gdf.merge(district_join, on="grid_id", how="left", validate="many_to_one")
    enriched["district_name_match_flag"] = (
        enriched["district_name"].fillna("").eq(enriched["district_name_official"].fillna(""))
    )
    return enriched


def aggregate_pois_to_grid(grid: gpd.GeoDataFrame, pois: gpd.GeoDataFrame) -> pd.DataFrame:
    """按格网聚合 POI。"""
    grid_proj = grid[["grid_id", "geometry"]].drop_duplicates("grid_id").to_crs(PROJECTED_CRS)
    pois_proj = pois.to_crs(PROJECTED_CRS)

    poi_join = gpd.sjoin(
        pois_proj[["geometry"]].copy(),
        grid_proj[["grid_id", "geometry"]],
        how="left",
        predicate="within",
    )
    poi_counts = (
        poi_join.dropna(subset=["grid_id"])
        .groupby("grid_id")
        .size()
        .rename("poi_count")
        .reset_index()
    )

    grid_proj["grid_area_sqkm"] = grid_proj.geometry.area / 1_000_000.0
    poi_features = grid_proj.merge(poi_counts, on="grid_id", how="left")
    poi_features["poi_count"] = poi_features["poi_count"].fillna(0).astype(int)
    poi_features["poi_density"] = (poi_features["poi_count"] / poi_features["grid_area_sqkm"]).fillna(0.0)
    return poi_features[["grid_id", "grid_area_sqkm", "poi_count", "poi_density"]].copy()


def minmax(series: pd.Series) -> pd.Series:
    """区间归一化。"""
    min_value = series.min()
    max_value = series.max()
    if pd.isna(min_value) or pd.isna(max_value) or max_value == min_value:
        return pd.Series(0.0, index=series.index)
    return (series - min_value) / (max_value - min_value)


def compute_core_and_fringe_metrics(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """基于 2019 年状态识别本地核心区并计算距离与圈层。"""
    enriched = gdf.copy()
    base_year = enriched[enriched["source_year"] == 2019].copy()
    if base_year.empty:
        raise ValueError("缺少 2019 年数据，无法识别本地核心区。")

    base_year["urbanity_score"] = 0.0
    for district_name, group in base_year.groupby("district_name", dropna=False):
        score = (
            minmax(pd.to_numeric(group["light"], errors="coerce").fillna(0.0))
            + minmax(pd.to_numeric(group["ndbi"], errors="coerce").fillna(0.0))
            + minmax(pd.to_numeric(group["poi_density"], errors="coerce").fillna(0.0))
        )
        base_year.loc[group.index, "urbanity_score"] = score

    base_year_proj = base_year.to_crs(PROJECTED_CRS).copy()
    district_cores: dict[str, object] = {}
    for district_name, group in base_year_proj.groupby("district_name", dropna=False):
        quantile_threshold = group["urbanity_score"].quantile(0.95)
        selected = group[group["urbanity_score"] >= quantile_threshold].copy()
        if selected.empty:
            selected = group.nlargest(1, "urbanity_score").copy()
        district_cores[str(district_name)] = selected.geometry.union_all()

    enriched_proj = enriched.to_crs(PROJECTED_CRS).copy()
    enriched_proj["dist_to_local_core"] = np.nan
    enriched_proj["local_core_id"] = pd.NA

    for district_name, core_geom in district_cores.items():
        mask = enriched_proj["district_name"].astype(str) == district_name
        if mask.any():
            enriched_proj.loc[mask, "dist_to_local_core"] = (
                enriched_proj.loc[mask, "geometry"].distance(core_geom)
            )
            enriched_proj.loc[mask, "local_core_id"] = f"{district_name}_core"

    def assign_flag(distance: float | None) -> str:
        if pd.isna(distance):
            return "Unknown"
        if distance <= 500:
            return "Core"
        if distance <= 3000:
            return "Fringe"
        return "Periphery"

    enriched["dist_to_local_core"] = enriched_proj["dist_to_local_core"].astype(float)
    enriched["local_core_id"] = enriched_proj["local_core_id"]
    enriched["core_fringe_flag"] = enriched["dist_to_local_core"].apply(assign_flag)
    return enriched


def export_outputs(gdf: gpd.GeoDataFrame, output_geojson: Path, output_csv: Path) -> None:
    """导出 GeoJSON 与 CSV。"""
    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    geojson_gdf = gdf.to_crs(GEOGRAPHIC_CRS).copy()
    geojson_gdf.to_file(output_geojson, driver="GeoJSON")

    csv_frame = pd.DataFrame(geojson_gdf.drop(columns="geometry"))
    centroid_proj = gdf.to_crs(PROJECTED_CRS).geometry.centroid
    centroid_geo = gpd.GeoSeries(centroid_proj, crs=PROJECTED_CRS).to_crs(GEOGRAPHIC_CRS)
    csv_frame["centroid_lon"] = centroid_geo.x
    csv_frame["centroid_lat"] = centroid_geo.y
    csv_frame["geometry_wkt"] = geojson_gdf.geometry.to_wkt()
    csv_frame.to_csv(output_csv, index=False, encoding="utf-8-sig")


def build_spatial_panel(
    base_panel_path: Path,
    grid_path: Path,
    districts_path: Path,
    pois_path: Path,
    output_geojson: Path,
    output_csv: Path,
) -> None:
    """执行 Q2 年度空间面板构建流程。"""
    validate_paths([base_panel_path, grid_path, districts_path, pois_path])

    base_panel = load_base_panel(base_panel_path)
    grid = load_grid(grid_path)
    districts = load_districts(districts_path)
    pois = load_pois(pois_path)

    spatial_panel = attach_geometry(base_panel, grid)
    spatial_panel = attach_official_districts(spatial_panel, districts)
    poi_features = aggregate_pois_to_grid(grid, pois)
    spatial_panel = spatial_panel.merge(poi_features, on="grid_id", how="left", validate="many_to_one")
    spatial_panel["poi_count"] = spatial_panel["poi_count"].fillna(0).astype(int)
    spatial_panel["poi_density"] = spatial_panel["poi_density"].fillna(0.0)
    spatial_panel["grid_area_sqkm"] = spatial_panel["grid_area_sqkm"].fillna(0.0)
    spatial_panel = compute_core_and_fringe_metrics(spatial_panel)

    ordered_columns = [
        "grid_id",
        "district_name",
        "district_name_grid",
        "district_name_official",
        "district_name_match_flag",
        "source_year",
        "rvri",
        "risk_state",
        "stock_pressure",
        "mismatch_gap",
        "ndbi",
        "light",
        "ndvi",
        "poi_count",
        "poi_density",
        "grid_area_sqkm",
        "local_core_id",
        "dist_to_local_core",
        "core_fringe_flag",
        "geometry",
    ]
    spatial_panel = spatial_panel[ordered_columns].sort_values(["source_year", "grid_id"]).reset_index(drop=True)

    export_outputs(spatial_panel, output_geojson, output_csv)

    print("Q2 第02步补强完成")
    print(f"- 基础面板输入: {base_panel_path}")
    print(f"- GeoJSON 输出: {output_geojson}")
    print(f"- CSV 输出: {output_csv}")
    print("- join 键: grid_id（基础面板 <-> 500m 格网）")
    print(f"- 坐标系处理: 原始统一为 {GEOGRAPHIC_CRS}，距离与面积计算投影到 {PROJECTED_CRS}")
    print("- POI 聚合方法: within 落格统计 poi_count，并换算 poi_density")
    print(f"- 唯一格网数: {spatial_panel['grid_id'].nunique()}")
    print(f"- 非空 dist_to_local_core 记录数: {int(spatial_panel['dist_to_local_core'].notna().sum())}")
    print(f"- core_fringe_flag 分布: {spatial_panel['core_fringe_flag'].value_counts(dropna=False).to_dict()}")


def main() -> None:
    """主入口。"""
    args = parse_args()
    build_spatial_panel(
        base_panel_path=args.base_panel,
        grid_path=args.grid,
        districts_path=args.districts,
        pois_path=args.pois,
        output_geojson=args.output_geojson,
        output_csv=args.output_csv,
    )


if __name__ == "__main__":
    main()
