from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_validation_module():
    module_path = (
        Path(__file__).resolve().parents[2] / "Q1" / "03_RVRI_Advanced_Validation.py"
    )
    spec = spec_from_file_location("annual_validation", module_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _build_grid_geojson(path: Path, grid_ids: list[str]) -> None:
    features = []
    for idx, grid_id in enumerate(grid_ids):
        col = idx % 4
        row = idx // 4
        x0 = float(col)
        y0 = float(row)
        features.append(
            {
                "type": "Feature",
                "properties": {"grid_id": grid_id},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x0, y0],
                            [x0 + 1.0, y0],
                            [x0 + 1.0, y0 + 1.0],
                            [x0, y0 + 1.0],
                            [x0, y0],
                        ]
                    ],
                },
            }
        )

    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def _build_poi_geojson(path: Path) -> None:
    poi_features = [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0.2, 0.2]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [1.2, 0.2]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [2.2, 0.2]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [3.2, 0.2]}},
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": poi_features}), encoding="utf-8")


def _build_district_geojson(path: Path) -> None:
    features = [
        {
            "type": "Feature",
            "properties": {"name": "A"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [4.0, 0.0], [4.0, 2.0], [0.0, 2.0], [0.0, 0.0]]],
            },
        }
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def test_assess_method_effectiveness_accepts_builtup_negative_light_pattern():
    module = load_validation_module()

    df = pd.DataFrame(
        {
            "source_year": [2023] * 8,
            "grid_id": [f"g{i}" for i in range(8)],
            "ndbi": [0.1, 0.15, 0.2, 0.25, 0.7, 0.75, 0.8, 0.85],
            "ndvi": [0.8, 0.78, 0.75, 0.73, 0.35, 0.3, 0.25, 0.2],
            "light": [0.0, 0.0, 0.0, 0.0, 3.0, 2.5, 1.5, 1.0],
            "rvri": [0.2, 0.25, 0.3, 0.35, 0.4, 0.55, 0.75, 0.9],
            "mismatch_gap": [-0.2, -0.1, 0.0, 0.1, 0.3, 0.45, 0.7, 0.9],
        }
    )

    summary = module.assess_method_effectiveness(df, urban_quantile=0.5, core_quantile=0.75)

    assert summary["works_for_q1"] is True
    assert summary["full_sample"]["corr_rvri_light"] > -0.2
    assert summary["urban_subset"]["corr_rvri_light"] < -0.3
    assert summary["urban_subset"]["corr_rvri_mismatch"] > 0.5


def test_build_affine_grid_index_recovers_integer_lattice():
    module = load_validation_module()

    features = [
        {
            "type": "Feature",
            "properties": {"grid_id": "g00"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"grid_id": "g10"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.0, 0.0], [4.0, 0.0], [4.0, 1.0], [2.0, 1.0], [2.0, 0.0]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"grid_id": "g01"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 1.0], [2.0, 1.0], [2.0, 2.0], [0.0, 2.0], [0.0, 1.0]]],
            },
        },
    ]

    grid = module.build_affine_grid_index(features)
    coords = {
        row.grid_id: (int(row.col), int(row.row))
        for row in grid[["grid_id", "col", "row"]].itertuples(index=False)
    }

    assert coords == {"g00": (0, 0), "g10": (1, 0), "g01": (0, 1)}


def test_count_pois_by_grid_assigns_points_and_polygon_centroids():
    module = load_validation_module()

    grid = pd.DataFrame(
        {
            "grid_id": ["g00", "g10"],
            "col": [0, 1],
            "row": [0, 0],
        }
    )
    lattice = {
        "origin": np.array([0.0, 0.0]),
        "matrix_inv": np.array([[1.0, 0.0], [0.0, 1.0]]),
        "coord_to_grid": {(0, 0): "g00", (1, 0): "g10"},
    }
    pois = [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0.2, 0.3]}},
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1.1, 0.1], [1.4, 0.1], [1.4, 0.4], [1.1, 0.4], [1.1, 0.1]]],
            },
        },
    ]

    counts = module.count_pois_by_grid(grid, lattice, pois)

    assert counts.to_dict() == {"g00": 1, "g10": 1}


def test_select_residential_candidates_excludes_barren_remote_cells_but_keeps_dark_urban_neighbors():
    module = load_validation_module()

    snapshot = pd.DataFrame(
        {
            "grid_id": ["g0", "g1", "g2", "g3"],
            "col": [0, 1, 2, 3],
            "row": [0, 0, 0, 0],
            "ndbi": [0.42, 0.38, 0.34, -0.10],
            "ndvi": [0.03, 0.31, 0.28, 0.60],
            "light": [0.0, 1.5, 0.0, 0.0],
            "rvri": [0.95, 0.72, 0.68, 0.10],
        }
    )
    poi_counts = pd.Series({"g3": 1.0}, name="poi_count", dtype=float)

    result = module.select_residential_candidate_snapshot(
        snapshot=snapshot,
        poi_counts=poi_counts,
        urban_quantile=0.25,
        min_ndvi=0.1,
    )

    candidate_ids = set(result["snapshot"]["grid_id"].tolist())
    assert candidate_ids == {"g1", "g2"}
    assert result["summary"]["excluded_barren_or_remote_rows"] == 2


def test_select_residential_candidates_can_relax_settlement_context_for_display():
    module = load_validation_module()

    snapshot = pd.DataFrame(
        {
            "grid_id": ["g0", "g1", "g2", "g3"],
            "col": [0, 3, 4, 5],
            "row": [1, 0, 0, 0],
            "ndbi": [0.42, 0.38, 0.34, -0.10],
            "ndvi": [0.20, 0.31, 0.28, 0.60],
            "light": [0.0, 1.5, 0.0, 0.0],
            "rvri": [0.95, 0.72, 0.68, 0.10],
        }
    )

    strict_result = module.select_residential_candidate_snapshot(
        snapshot=snapshot,
        poi_counts=pd.Series(dtype=float),
        urban_quantile=0.25,
        min_ndvi=0.1,
        require_settlement_context=True,
    )
    relaxed_result = module.select_residential_candidate_snapshot(
        snapshot=snapshot,
        poi_counts=pd.Series(dtype=float),
        urban_quantile=0.25,
        min_ndvi=0.1,
        require_settlement_context=False,
    )

    assert set(strict_result["snapshot"]["grid_id"].tolist()) == {"g1", "g2"}
    assert set(relaxed_result["snapshot"]["grid_id"].tolist()) == {"g0", "g1", "g2"}


def test_extract_boundary_rings_supports_polygon_and_multipolygon():
    module = load_validation_module()

    features = [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
        },
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[2, 0], [3, 0], [3, 1], [2, 1], [2, 0]]]],
            },
        },
    ]

    rings = module.extract_boundary_rings(features)
    assert len(rings) == 2
    assert rings[0].shape[0] == 5
    assert rings[1].shape[0] == 5


def test_run_validation_by_year_writes_year_directories_and_summary(tmp_path: Path):
    module = load_validation_module()

    grid_ids = [f"g{i}" for i in range(8)]
    panel_rows = []
    base_ndbi = [0.10, 0.15, 0.20, 0.25, 0.72, 0.78, 0.84, 0.90]
    base_ndvi = [0.80, 0.78, 0.75, 0.73, 0.34, 0.30, 0.26, 0.22]
    base_light = [0.0, 0.1, 0.2, 0.3, 3.0, 2.5, 1.5, 1.0]
    base_rvri = [0.20, 0.24, 0.28, 0.32, 0.42, 0.58, 0.76, 0.92]
    base_gap = [-0.2, -0.1, 0.0, 0.1, 0.3, 0.45, 0.7, 0.9]

    for year, offset in [(2022, 0.00), (2023, 0.03)]:
        for idx, grid_id in enumerate(grid_ids):
            panel_rows.append(
                {
                    "source_year": year,
                    "grid_id": grid_id,
                    "time": str(year),
                    "time_grain": "annual",
                    "ndbi": base_ndbi[idx] + offset,
                    "ndvi": base_ndvi[idx] - offset,
                    "light": base_light[idx],
                    "rvri": min(base_rvri[idx] + offset, 0.99),
                    "mismatch_gap": base_gap[idx] + offset,
                }
            )

    panel_path = tmp_path / "annual_panel.csv"
    pd.DataFrame(panel_rows).to_csv(panel_path, index=False)

    grid_path = tmp_path / "grid.geojson"
    poi_path = tmp_path / "pois.geojson"
    output_dir = tmp_path / "validation_output"
    _build_grid_geojson(grid_path, grid_ids)
    _build_poi_geojson(poi_path)

    report = module.run_validation_by_year(
        annual_csv_path=panel_path,
        grid_geojson_path=grid_path,
        poi_geojson_path=poi_path,
        output_root_dir=output_dir,
    )

    assert report["years"] == [2022, 2023]
    assert set(report["year_reports"].keys()) == {"2022", "2023"}

    for year in ["2022", "2023"]:
        year_dir = output_dir / "by_year" / year
        assert year_dir.exists()
        assert (year_dir / "Q1_Diagnostic_Full_Report.json").exists()
        assert (year_dir / "validation_report.json").exists()
        assert (year_dir / "Q1_LISA_Map.png").exists()

    summary_path = output_dir / "by_year" / "by_year_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["years"] == [2022, 2023]


def test_run_validation_reports_unified_analysis_domain_for_spatial_autocorr(tmp_path: Path):
    module = load_validation_module()

    grid_ids = [f"g{i}" for i in range(8)]
    rows = []
    ndbi = [0.30, 0.28, 0.26, 0.24, 0.22, 0.20, -0.10, -0.12]
    ndvi = [0.02, 0.30, 0.32, 0.29, 0.33, 0.31, 0.70, 0.72]
    light = [0.0, 1.5, 0.0, 1.2, 0.8, 0.0, 0.0, 0.0]
    rvri = [0.95, 0.82, 0.76, 0.71, 0.66, 0.61, 0.15, 0.10]
    gap = [0.9, 0.6, 0.55, 0.5, 0.45, 0.4, -0.2, -0.25]
    for idx, grid_id in enumerate(grid_ids):
        rows.append(
            {
                "source_year": 2023,
                "grid_id": grid_id,
                "time": "2023",
                "time_grain": "annual",
                "ndbi": ndbi[idx],
                "ndvi": ndvi[idx],
                "light": light[idx],
                "rvri": rvri[idx],
                "mismatch_gap": gap[idx],
            }
        )

    panel_path = tmp_path / "annual_panel.csv"
    pd.DataFrame(rows).to_csv(panel_path, index=False)
    grid_path = tmp_path / "grid.geojson"
    poi_path = tmp_path / "pois.geojson"
    _build_grid_geojson(grid_path, grid_ids)
    _build_poi_geojson(poi_path)

    report = module.run_validation(
        annual_csv_path=panel_path,
        grid_geojson_path=grid_path,
        poi_geojson_path=poi_path,
        output_dir=tmp_path / "validation_output",
    )

    assert report["spatial_autocorr"]["rows"] < report["data_basis"]["snapshot_rows"]
    assert report["analysis_domain_filter"]["total_domain_rows"] == report["spatial_autocorr"]["rows"]
    assert report["strict_residential_candidate_filter"]["candidate_rows"] <= report["spatial_autocorr"]["rows"]


def test_plot_lisa_like_map_writes_frame_and_excluded_layers(tmp_path: Path):
    module = load_validation_module()

    full_snapshot = pd.DataFrame(
        {
            "grid_id": ["g0", "g1", "g2", "g3"],
            "cx": [0.5, 1.5, 2.5, 3.5],
            "cy": [0.5, 0.5, 0.5, 0.5],
        }
    )
    candidate_snapshot = pd.DataFrame(
        {
            "grid_id": ["g1", "g2"],
            "cx": [1.5, 2.5],
            "cy": [0.5, 0.5],
            "cluster": ["HH", "LL"],
        }
    )
    display_snapshot = pd.DataFrame(
        {
            "grid_id": ["g0", "g1", "g2"],
            "cx": [0.5, 1.5, 2.5],
            "cy": [0.5, 0.5, 0.5],
        }
    )
    district_path = tmp_path / "districts.geojson"
    output_path = tmp_path / "lisa.png"
    _build_district_geojson(district_path)

    module.plot_lisa_like_map(
        candidate_snapshot=candidate_snapshot,
        display_snapshot=display_snapshot,
        full_snapshot=full_snapshot,
        output_path=output_path,
        year=2023,
        moran_i=0.5,
        district_geojson_path=district_path,
    )

    assert output_path.exists()
