from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
REPO_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from q3_utils import (
    LOGGER,
    SPATIAL_WEIGHT_EDGES_PATH,
    SPATIAL_WEIGHT_NODES_PATH,
    build_spatial_weights,
    load_grid,
    save_spatial_weights_outputs,
    setup_logging,
    update_summary,
)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建 Q3 Queen 邻接空间权重。")
    parser.add_argument(
        "--grid",
        default=None,
        help="可选，自定义 scientific_grid_500m.geojson 路径。",
    )
    return parser


def main() -> None:
    setup_logging()
    args = build_argparser().parse_args()
    LOGGER.info("开始执行 Q3 Step 2：构建空间权重。")
    grid = load_grid(grid_path=args.grid)
    nodes, edges, summary = build_spatial_weights(grid=grid)
    save_spatial_weights_outputs(nodes=nodes, edges=edges, summary=summary)

    summary_payload = {
        **summary,
        "nodes_path": str(SPATIAL_WEIGHT_NODES_PATH.relative_to(REPO_DIR)),
        "edges_path": str(SPATIAL_WEIGHT_EDGES_PATH.relative_to(REPO_DIR)),
    }
    update_summary("spatial_weights", summary_payload)
    LOGGER.info("Q3 Step 2 完成，空间权重已更新到输出目录。")

    print("Q3 空间权重构建完成。")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
