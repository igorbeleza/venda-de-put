import os
from pathlib import Path

from venda_de_put.paths import load_dotenv


def test_load_dotenv_sets_env_without_overriding(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VENDA_DE_PUT_ADMIN_PASSWORD=segredo\n"
        "# comentario\n"
        "\n"
        'VENDA_DE_PUT_SECRET_KEY="chave entre aspas"\n'
        "JA_DEFINIDA=novo\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("VENDA_DE_PUT_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("VENDA_DE_PUT_SECRET_KEY", raising=False)
    monkeypatch.setenv("JA_DEFINIDA", "original")

    load_dotenv(env_file)

    assert os.environ["VENDA_DE_PUT_ADMIN_PASSWORD"] == "segredo"
    assert os.environ["VENDA_DE_PUT_SECRET_KEY"] == "chave entre aspas"
    assert os.environ["JA_DEFINIDA"] == "original"


def test_load_dotenv_missing_file_is_noop(tmp_path: Path):
    load_dotenv(tmp_path / "nao-existe.env")
