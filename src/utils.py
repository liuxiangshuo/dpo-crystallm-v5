from __future__ import annotations
import os
import json
from datetime import datetime
from pathlib import Path

def make_run_dir(outputs_dir: str = "outputs", tag: str = "run") -> Path:
    """Create outputs/<tag>_YYYYmmdd_HHMMSS/ and return its path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(outputs_dir) / f"{tag}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir

def save_json(obj, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def env_info() -> dict:
    """Capture minimal environment info for reproducibility."""
    info = {}
    info["cwd"] = os.getcwd()
    info["python"] = os.popen("python -V").read().strip()
    info["which_python"] = os.popen("which python").read().strip()
    info["pip_freeze_head"] = os.popen("python -m pip freeze | head -n 20").read().splitlines()
    return info
