import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from venda_de_put.config import AppConfig, save_config
from venda_de_put.models import CandleSeries, Fundamentals, IvPoint
from venda_de_put.scrape import run_scrape
from venda_de_put.snapshot import write_snapshot
from venda_de_put.tz import TZ
from venda_de_put.web.app import create_app, label_vencimento
from venda_de_put.models import Vencimento
from datetime import date


class FakePrice:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series

    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        return {t: self.series[t] for t in tickers if t in self.series}


class FakeIv:
    def __init__(self, pts: dict[str, IvPoint]):
        self.pts = pts

    def fetch(self) -> dict[str, IvPoint]:
        return self.pts


class FakeFund:
    def __init__(self, rows: list[Fundamentals]):
        self.rows = rows

    def fetch(self) -> list[Fundamentals]:
        return self.rows


def _fund(ticker: str, **kw) -> Fundamentals:
    defaults = dict(
        cotacao=40.0, pl=8.0, pvp=1.1, psr=None, dy=0.08,
        p_ativo=None, p_cap_giro=None, p_ebit=None, p_ativ_circ_liq=None,
        ev_ebit=None, ev_ebitda=5.0, mrg_bruta=None, mrg_ebit=None,
        mrg_liq=0.15, liq_corr=1.2, roic=0.12, roe=0.18, liq_2meses=None,
        patrim_liq=None, div_liq_patrim=0.3, cresc_rec_5a=0.08,
    )
    defaults.update(kw)
    return Fundamentals(ticker=ticker, **defaults)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    now = datetime(2026, 8, 13, 16, 0, tzinfo=TZ)
    universe = {
        "PETR4": "Petróleo e Gás",
        "VALE3": "Mineração e Siderurgia",
        "ITUB4": "Financeiro",
    }
    series = {}
    for t, preco in (("PETR4", 41.75), ("VALE3", 62.0), ("ITUB4", 35.0)):
        series[t] = CandleSeries(
            ticker=t,
            closes=[preco * 0.9] * 210,
            preco=preco,
            max_52=preco + 5,
            min_52=preco - 10,
            collected_at=now,
        )
    price = FakePrice(series)
    iv = FakeIv({
        t: IvPoint(t, iv=0.35, iv_rank=40, iv_percentile=0.55)
        for t in universe
    })
    fund = FakeFund([
        _fund("PETR4", pl=6.0, roe=0.22, ev_ebitda=4.0),
        _fund("VALE3", pl=7.0, roe=0.19, ev_ebitda=4.5),
        _fund("ITUB4", pl=9.0, roe=0.16, ev_ebitda=None),
    ])
    snap = run_scrape(price, iv, fund, AppConfig(), universe, holidays=set(), now=now)
    write_snapshot(snap, tmp_path / "current.json", tmp_path / "history", archive_if_1600=False)
    save_config(AppConfig(), tmp_path / "config.json")
    (tmp_path / "universe.json").write_text(
        json.dumps(universe, ensure_ascii=False), encoding="utf-8"
    )
    src_feriados = Path(__file__).resolve().parents[1] / "data" / "feriados.json"
    if src_feriados.is_file():
        shutil.copy(src_feriados, tmp_path / "feriados.json")
    else:
        (tmp_path / "feriados.json").write_text("[]\n", encoding="utf-8")
    return tmp_path


def test_refresh_does_not_scrape(data_dir, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("scrape called")
    monkeypatch.setattr("venda_de_put.scrape.run_scrape", boom)
    app = create_app(data_dir=data_dir)
    c = TestClient(app)
    r = c.post("/api/refresh")
    assert r.status_code == 200
    assert "coletado" in r.text.lower() or "generated_at" in r.json() or "stamps" in r.json()


def test_trocar_vencimento_nao_reordena(data_dir):
    app = create_app(data_dir=data_dir)
    c = TestClient(app)
    a = c.get("/api/dashboard", params={"vencimento": "2026-08-21", "so_mensais": 1}).json()
    b = c.get("/api/dashboard", params={"vencimento": "2026-09-18", "so_mensais": 1}).json()
    tickers = lambda payload, key: [x["ticker"] for x in payload["listas"][key]]
    assert tickers(a, "fundamentalista") == tickers(b, "fundamentalista")
    assert tickers(a, "tecnico") == tickers(b, "tecnico")
    assert tickers(a, "combinado") == tickers(b, "combinado")
    assert a["premio_alvo"] != b["premio_alvo"]
    assert a["vencimento"]["efetivo"] != b["vencimento"]["efetivo"]
    assert "label" in a["vencimento"]
    assert "MENSAL" in a["vencimento"]["label"]


def test_label_vencimento_formato():
    v = Vencimento(
        nominal=date(2026, 9, 18),
        efetivo=date(2026, 9, 18),
        tipo="MENSAL",
        feriado_na_sexta=False,
        dia_semana="sexta",
        dias_corridos=36,
        dias_uteis=25,
        status="",
    )
    assert label_vencimento(v) == "18/09/2026 · sex · 36 dias corridos · 25 úteis · MENSAL"


def test_config_put_recalculates_without_scrape(data_dir, monkeypatch):
    monkeypatch.setattr(
        "venda_de_put.scrape.run_scrape",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scrape")),
    )
    app = create_app(data_dir=data_dir)
    client = TestClient(app)
    before = client.get("/api/dashboard").json()
    cfg = client.get("/api/config").json()
    cfg["ifr_max"] = 45
    r = client.put("/api/config", json=cfg)
    assert r.status_code == 200
    dash = client.get("/api/dashboard").json()
    assert dash["stamps"] == before["stamps"]
    saved = client.get("/api/config").json()
    assert saved["ifr_max"] == 45


def test_instrucoes_ifr_sem_profit(data_dir):
    app = create_app(data_dir=data_dir)
    client = TestClient(app)
    text = client.get("/api/instrucoes").json()["texto"]
    assert "10" in text and "50" in text
    assert "Profit" not in text
    assert "RTD" not in text


def test_feriados_put_muda_vencimentos(data_dir):
    app = create_app(data_dir=data_dir)
    client = TestClient(app)
    before = client.get("/api/vencimentos").json()
    feriados = client.get("/api/feriados").json()
    items = feriados if isinstance(feriados, list) else feriados.get("feriados", feriados)
    extra = {"date": "2026-08-21", "descricao": "teste"}
    if isinstance(items, list):
        payload = items + [extra]
    else:
        payload = [extra]
    r = client.put("/api/feriados", json=payload)
    assert r.status_code == 200
    after = client.get("/api/vencimentos").json()
    assert after != before


def test_app_py_does_not_import_scrape():
    src = Path(__file__).resolve().parents[1] / "src" / "venda_de_put" / "web" / "app.py"
    text = src.read_text(encoding="utf-8")
    assert "run_scrape" not in text
    assert "venda_de_put.scrape" not in text


def test_ativos_calculo0_strips_ranks_from_item_root(data_dir):
    app = create_app(data_dir=data_dir)
    client = TestClient(app)
    items = client.get("/api/ativos", params={"calculo": 0}).json()["ativos"]
    assert items
    for it in items:
        assert "n_roe" not in it
        assert "n_pl" not in it
        assert "n_roe" not in it.get("fund", {})
        assert "n_pl" not in it.get("fund", {})


def test_ativos_calculo1_includes_n_roe(data_dir):
    app = create_app(data_dir=data_dir)
    client = TestClient(app)
    items = client.get("/api/ativos", params={"calculo": 1}).json()["ativos"]
    assert items
    assert any("n_roe" in it for it in items)


def test_ativos_roe_is_fundamentals_not_rank(data_dir):
    app = create_app(data_dir=data_dir)
    client = TestClient(app)
    items = client.get("/api/ativos", params={"calculo": 0}).json()["ativos"]
    petr = next(it for it in items if it["ticker"] == "PETR4")
    # seeded fixture: _fund("PETR4", pl=6.0, roe=0.22, ...)
    assert petr["roe"] == 0.22
    assert petr["pl"] == 6.0
