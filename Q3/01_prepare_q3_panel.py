from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
REPO_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from q3_utils import LOGGER, OUTPUT_DIR, prepare_q3_panel, save_q3_panel_outputs, setup_logging, update_summary


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="准备 Q3 年度面板与状态转移样本。")
    parser.add_argument(
        "--input",
        default=None,
        help="可选，自定义 Q1 主结果路径。未指定时会自动优先读取正式年度表。",
    )
    return parser


def main() -> None:
    setup_logging()
    args = build_argparser().parse_args()
    LOGGER.info("开始执行 Q3 Step 1：准备年度面板与状态转移样本。")
    panel, transition, metadata = prepare_q3_panel(input_path=args.input)
    save_q3_panel_outputs(panel=panel, transition=transition, metadata=metadata)

    summary_payload = {
        "panel_path": str((OUTPUT_DIR / "q3_panel.csv").relative_to(REPO_DIR)),
        "transition_path": str((OUTPUT_DIR / "q3_transition_panel.csv").relative_to(REPO_DIR)),
        **metadata,
    }
    update_summary("panel_preparation", summary_payload)
    LOGGER.info("Q3 Step 1 完成，面板与转移样本已更新到输出目录。")

    print("Q3 年度面板准备完成。")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
