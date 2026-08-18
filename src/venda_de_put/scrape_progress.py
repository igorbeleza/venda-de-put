from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

RETRY_MAX_AGE = timedelta(hours=1)

STEPS: tuple[tuple[str, str], ...] = (
    ("yahoo", "Yahoo"),
    ("oplab", "OpLab"),
    ("fundamentus", "Fundamentus"),
    ("oplab_cadeia", "Cadeia"),
)

STATUSES = ("pendente", "raspando", "ok", "falhou", "pulado")

RETRY_FROM: dict[str, tuple[str, ...]] = {
    "yahoo": ("yahoo", "oplab", "fundamentus", "oplab_cadeia"),
    "oplab": ("oplab", "oplab_cadeia"),
    "fundamentus": ("fundamentus", "oplab_cadeia"),
    "oplab_cadeia": ("oplab_cadeia",),
}


def retry_from(step: str) -> tuple[str, ...]:
    if step not in RETRY_FROM:
        raise ValueError(f"passo desconhecido: {step}")
    return RETRY_FROM[step]


def retry_is_full(generated_at: datetime | None, now: datetime) -> bool:
    if generated_at is None:
        return False
    gen = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)
    current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return (current - gen) > RETRY_MAX_AGE


def progress_path(root: Path) -> Path:
    return Path(root) / "snapshots" / "scrape_progress.json"


def _blank_passos() -> list[dict[str, Any]]:
    return [{"id": sid, "label": label, "status": "pendente", "erro": None} for sid, label in STEPS]


def _write(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def begin_progress(path: Path) -> dict[str, Any]:
    data = {"passos": _blank_passos()}
    _write(path, data)
    return data


def read_progress(path: Path) -> Optional[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("passos"), list):
        return None
    return raw


def mark_step(path: Path, source: str, status: str, erro: str | None = None) -> None:
    data = read_progress(path) or begin_progress(path)
    found = False
    for step in data["passos"]:
        if step.get("id") == source:
            step["status"] = status
            step["erro"] = None if status in ("ok", "pendente", "raspando", "pulado") else erro
            if status == "falhou":
                step["erro"] = erro
            found = True
            break
    if not found:
        label = next((lab for sid, lab in STEPS if sid == source), source)
        data["passos"].append({"id": source, "label": label, "status": status, "erro": erro})
    _write(path, data)


def start_retry(path: Path, sources: tuple[str, ...] | list[str]) -> dict[str, Any]:
    data = read_progress(path) or begin_progress(path)
    wanted = set(sources)
    for step in data["passos"]:
        if step.get("id") in wanted:
            step["status"] = "raspando"
            step["erro"] = None
    _write(path, data)
    return data


def fail_running(path: Path, erro: str) -> None:
    data = read_progress(path)
    if data is None:
        return
    for step in data["passos"]:
        if step.get("status") == "raspando":
            step["status"] = "falhou"
            step["erro"] = erro
    _write(path, data)


def passos_from_stamps(stamps: list[Any]) -> list[dict[str, Any]]:
    by = {getattr(s, "source", None): s for s in stamps}
    out: list[dict[str, Any]] = []
    for sid, label in STEPS:
        s = by.get(sid)
        if s is None:
            status = "pulado" if sid == "fundamentus" else "sem dado"
            out.append({"id": sid, "label": label, "status": status, "erro": None})
            continue
        if getattr(s, "ok", False):
            out.append({"id": sid, "label": label, "status": "ok", "erro": None})
        else:
            out.append({
                "id": sid,
                "label": label,
                "status": "falhou",
                "erro": getattr(s, "error", None),
            })
    return out


class FileProgress:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def mark(self, source: str, status: str, erro: str | None = None) -> None:
        mark_step(self.path, source, status, erro)
