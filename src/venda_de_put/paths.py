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


def load_dotenv(path: Path | str | None = None) -> None:
    """Lê pares VAR=valor de um .env para os.environ, sem sobrescrever
    variáveis já definidas (no processo ou herdadas do ambiente). Usado pra
    ADMIN_PASSWORD/SECRET_KEY locais sem precisar exportar toda vez; em
    produção o mesmo arquivo é copiado pro WorkingDirectory do systemd.
    Ausência do arquivo é um no-op silencioso."""
    candidate = Path(path) if path is not None else Path.cwd() / ".env"
    if not candidate.is_file():
        return
    for line in candidate.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
