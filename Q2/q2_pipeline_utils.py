from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def resolve_existing_file(base_dir: Path, candidate_names: list[str]) -> Path | None:
    """按候选名称顺序寻找第一个存在的文件。"""
    for name in candidate_names:
        path = base_dir / name
        if path.exists():
            return path
    return None


def ensure_parent(path: Path) -> None:
    """确保父目录存在。"""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_step_log(log_path: Path, payload: dict) -> None:
    """写出步骤日志。"""
    ensure_parent(log_path)
    content = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    with log_path.open("w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

