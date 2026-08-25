from datetime import date, datetime
from pathlib import Path
import io
import os
import time
import zipfile

import httpx

from venda_de_put.models import CandleSeries
from venda_de_put.sources.cotahist import (
    COTAHIST_URL,
    CotahistBootstrap,
    parse_cotahist_line,
    parse_cotahist_text,
)
from venda_de_put.tz import TZ


def _line(
    d: str,
    ticker: str,
    close: float,
    *,
    tipreg: str = "01",
    bdi: str = "02",
    tpmerc: str = "010",
) -> str:
    chars = [" "] * 245
    chars[0:2] = list(tipreg)
    chars[2:10] = list(d)
    chars[10:12] = list(bdi)
    chars[12:24] = list(ticker.ljust(12))
    chars[24:27] = list(tpmerc)
    chars[108:121] = list(f"{int(round(close * 100)):013d}")
    return "".join(chars)


def test_parse_cotahist_linha_vista_lote_padrao():
    row = parse_cotahist_line(_line("20260815", "PETR4", 41.75))
    assert row == (date(2026, 8, 15), "PETR4", 41.75)


def test_parse_cotahist_ignora_opcao_e_header():
    header = _line("20260815", "PETR4", 1.0, tipreg="00")
    opcao = _line("20260815", "PETR4", 2.0, tpmerc="070")
    frac = _line("20260815", "PETR4", 3.0, bdi="12")
    ok = _line("20260815", "PETR4", 41.75)
    text = "\n".join([header, opcao, frac, ok])
    by = parse_cotahist_text(text, ["PETR4"])
    assert by["PETR4"] == [(date(2026, 8, 15), 41.75)]


def _zip_bytes(year: int, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"COTAHIST_A{year}.TXT", text)
    return buf.getvalue()


def test_cotahist_cache_hit_nao_baixa(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    n = {"get": 0}
    text = _line("20250815", "PETR4", 30.0) + "\n" + _line("20260814", "PETR4", 40.0)
    (tmp_path / "COTAHIST_A2025.ZIP").write_bytes(_zip_bytes(2025, text))
    (tmp_path / "COTAHIST_A2026.ZIP").write_bytes(_zip_bytes(2026, text))

    def handler(request: httpx.Request) -> httpx.Response:
        n["get"] += 1
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert n["get"] == 0
    assert "PETR4" in out
    assert out["PETR4"].closes[-1] == 40.0
    assert out["PETR4"].preco == 40.0
    assert len(out["PETR4"].timestamps) == len(out["PETR4"].closes)


def test_cotahist_ano_corrente_velho_dispara_get(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(_zip_bytes(2026, _line("20260102", "PETR4", 10.0) + "\n"))
    old_mtime = time.time() - 86400 - 5
    os.utime(p2026, (old_mtime, old_mtime))

    n = {"urls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        n["urls"].append(str(request.url))
        body = _zip_bytes(2026, _line("20260814", "PETR4", 40.0) + "\n")
        return httpx.Response(200, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert any("COTAHIST_A2026.ZIP" in u for u in n["urls"])
    assert not any("COTAHIST_A2025.ZIP" in u for u in n["urls"])
    assert out["PETR4"].preco == 40.0
    assert n["urls"][0] == COTAHIST_URL.format(year=2026)


def test_cotahist_get_falho_reusa_zip(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(_zip_bytes(2026, _line("20260814", "PETR4", 40.0) + "\n"))
    os.utime(p2026, (time.time() - 86400 - 5, time.time() - 86400 - 5))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out["PETR4"].preco == 40.0


def test_cotahist_get_404_sem_cache_omite(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out == {}


def test_cotahist_200_invalido_nao_envenena_cache(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(_zip_bytes(2026, _line("20260814", "PETR4", 40.0) + "\n"))
    os.utime(p2026, (time.time() - 86400 - 5, time.time() - 86400 - 5))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>erro da B3</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out["PETR4"].preco == 40.0
    assert zipfile.is_zipfile(p2026)


def test_cotahist_zip_corrupto_num_ano_nao_descarta_o_outro(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(b"not a zip")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out["PETR4"].preco == 30.0
