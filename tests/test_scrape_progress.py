from datetime import datetime, timedelta
from pathlib import Path

from venda_de_put.scrape_progress import (
    STEPS,
    begin_progress,
    fail_running,
    mark_step,
    read_progress,
    retry_from,
    retry_is_full,
    start_retry,
)
from venda_de_put.tz import TZ


def test_begin_progress_deixa_todos_pendentes(tmp_path: Path):
    path = tmp_path / "scrape_progress.json"
    begin_progress(path)
    data = read_progress(path)
    assert [s["id"] for s in data["passos"]] == [sid for sid, _ in STEPS]
    assert all(s["status"] == "pendente" for s in data["passos"])
    assert all(s["erro"] is None for s in data["passos"])


def test_mark_step_grava_status_e_erro(tmp_path: Path):
    path = tmp_path / "scrape_progress.json"
    begin_progress(path)
    mark_step(path, "yahoo", "ok")
    mark_step(path, "oplab", "raspando")
    mark_step(path, "fundamentus", "pulado")
    mark_step(path, "oplab_cadeia", "falhou", "The read operation timed out")
    by = {s["id"]: s for s in read_progress(path)["passos"]}
    assert by["yahoo"]["status"] == "ok"
    assert by["oplab"]["status"] == "raspando"
    assert by["fundamentus"]["status"] == "pulado"
    assert by["oplab_cadeia"]["status"] == "falhou"
    assert by["oplab_cadeia"]["erro"] == "The read operation timed out"


def test_fail_running_marca_so_os_em_andamento(tmp_path: Path):
    path = tmp_path / "scrape_progress.json"
    begin_progress(path)
    mark_step(path, "yahoo", "ok")
    mark_step(path, "oplab", "raspando")
    fail_running(path, "processo saiu com código 1")
    by = {s["id"]: s for s in read_progress(path)["passos"]}
    assert by["yahoo"]["status"] == "ok"
    assert by["oplab"]["status"] == "falhou"
    assert by["oplab"]["erro"] == "processo saiu com código 1"
    assert by["fundamentus"]["status"] == "pendente"


def test_read_progress_ausente_retorna_none(tmp_path: Path):
    assert read_progress(tmp_path / "nao-existe.json") is None


def test_retry_from_inclui_dependentes():
    assert retry_from("yahoo") == ("yahoo", "oplab", "fundamentus", "oplab_cadeia")
    assert retry_from("oplab") == ("oplab", "oplab_cadeia")
    assert retry_from("fundamentus") == ("fundamentus", "oplab_cadeia")
    assert retry_from("oplab_cadeia") == ("oplab_cadeia",)


def test_retry_is_full_depois_de_uma_hora():
    now = datetime(2026, 8, 18, 12, 0, tzinfo=TZ)
    assert retry_is_full(None, now) is False
    assert retry_is_full(now - timedelta(minutes=59), now) is False
    assert retry_is_full(now - timedelta(hours=1), now) is False
    assert retry_is_full(now - timedelta(hours=1, seconds=1), now) is True


def test_start_retry_marca_so_dependentes_como_raspando(tmp_path: Path):
    path = tmp_path / "scrape_progress.json"
    begin_progress(path)
    mark_step(path, "yahoo", "ok")
    mark_step(path, "oplab", "falhou", "timeout")
    mark_step(path, "fundamentus", "ok")
    mark_step(path, "oplab_cadeia", "ok")
    start_retry(path, retry_from("oplab"))
    by = {s["id"]: s for s in read_progress(path)["passos"]}
    assert by["yahoo"]["status"] == "ok"
    assert by["fundamentus"]["status"] == "ok"
    assert by["oplab"]["status"] == "raspando"
    assert by["oplab_cadeia"]["status"] == "raspando"
