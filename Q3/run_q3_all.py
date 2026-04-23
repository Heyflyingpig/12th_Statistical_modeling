from __future__ import annotations

import runpy
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent


def main() -> None:
    scripts = [
        "01_prepare_q3_panel.py",
        "02_build_spatial_weights.py",
        "03_spatial_autocorr.py",
        "04_markov_transition.py",
        "05_spatial_markov.py",
        "06_low_to_high_predict.py",
    ]
    for script_name in scripts:
        script_path = CURRENT_DIR / script_name
        print(f"[Q3] Running {script_name} ...")
        runpy.run_path(str(script_path), run_name="__main__")
    print("[Q3] 全流程执行完成。")


if __name__ == "__main__":
    main()
