from __future__ import annotations

import os
from pathlib import Path

_REPO_DATA = Path(__file__).resolve().parents[2] / "data"


def data_dir(explicit: Path | str | None = None) -> Path:
    if explicit is not None and str(explicit).strip():
        return Path(explicit)
    env = os.environ.get("VENDA_DE_PUT_DATA")
    if env:
        return Path(env)
    return _REPO_DATA


def snapshot_current(root: Path | None = None) -> Path:
    return data_dir(root) / "snapshots" / "current.json"


def snapshot_history(root: Path | None = None) -> Path:
    return data_dir(root) / "snapshots" / "history"
