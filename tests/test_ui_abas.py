import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from venda_de_put.config import AppConfig, save_config
from venda_de_put.models import CandleSeries, Fundamentals
from venda_de_put.scrape import run_scrape
from venda_de_put.snapshot import write_snapshot
from venda_de_put.auth import create_session_token
from venda_de_put.tz import TZ
from venda_de_put.web.app import create_app


class FakePrice:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series

    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        return {t: self.series[t] for t in tickers if t in self.series}


class FakeIv:
    def __init__(self, pts):
        self.pts = pts

    def fetch(self):
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
    from venda_de_put.models import IvPoint

    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
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
    iv = FakeIv({t: IvPoint(t, iv=0.35, iv_rank=40, iv_percentile=0.55) for t in universe})
    fund = FakeFund([
        _fund("PETR4", pl=6.0, roe=0.22, ev_ebitda=4.0),
        _fund("VALE3", pl=7.0, roe=0.19, ev_ebitda=4.5),
        _fund("ITUB4", pl=9.0, roe=0.16, ev_ebitda=None),
    ])
    snap = run_scrape(price, iv, fund, AppConfig(), universe, holidays=set(), now=now)
    write_snapshot(snap, tmp_path / "current.json", tmp_path / "history", archive_if_1600=False)
    save_config(AppConfig(), tmp_path / "config.json")
    (tmp_path / "universe.json").write_text(json.dumps(universe, ensure_ascii=False), encoding="utf-8")
    src_feriados = Path(__file__).resolve().parents[1] / "data" / "feriados.json"
    if src_feriados.is_file():
        shutil.copy(src_feriados, tmp_path / "feriados.json")
    else:
        (tmp_path / "feriados.json").write_text("[]\n", encoding="utf-8")
    return tmp_path


def test_config_put_recalculates_without_scrape(tmp_path, monkeypatch, data_dir):
    monkeypatch.setattr(
        "venda_de_put.scrape.run_scrape",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scrape")),
    )
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    client.cookies.set("session", create_session_token())
    before = client.get("/api/dashboard").json()
    cfg = client.get("/api/config").json()
    cfg["ifr_max"] = 45
    r = client.put("/api/config", json=cfg)
    assert r.status_code == 200
    dash = client.get("/api/dashboard").json()
    assert dash["stamps"] == before["stamps"]
    saved = client.get("/api/config").json()
    assert saved["ifr_max"] == 45


def test_instrucoes_corrigem_ifr_e_tiram_profit(data_dir):
    client = TestClient(create_app(data_dir=data_dir))
    html = client.get("/").text
    assert "Instruções" in html
    text = client.get("/api/instrucoes").json()["texto"]
    assert "10" in text and "50" in text
    assert "Profit" not in text
    assert "RTD" not in text


def test_home_markup_has_seven_panes_and_mobile_css(data_dir):
    client = TestClient(create_app(data_dir=data_dir))
    html = client.get("/").text
    for pane in (
        "pane-ativos",
        "pane-dados",
        "pane-setores",
        "pane-config",
        "pane-vencimentos",
        "pane-feriados",
        "pane-instrucoes",
    ):
        assert pane in html
    css = client.get("/static/app.css").text
    assert "max-width: 720px" in css
    assert "data-label" in css or "attr(data-label)" in css
    assert "#eee6d4" in css
    js = client.get("/static/app.js").text
    assert "/api/ativos" in js
    assert '["mm200", "MM200"]' in js
    assert '["ifr", "IFR"]' in js
    assert '["boll_inf", "Boll Inf"]' in js
    assert js.index('["mm200", "MM200"]') < js.index('["ifr", "IFR"]')
    assert js.index('["ifr", "IFR"]') < js.index('["boll_inf", "Boll Inf"]')
    assert '["iv", "IV"]' in js
    assert '["hv", "HV"]' in js
    assert '["iv_hv", "IV/HV"]' in js
    assert js.index('["iv", "IV"]') < js.index('["hv", "HV"]')
    assert '["iv_rank", "IV Rank"]' not in js
    assert '["iv_percentile", "IV Percentil"]' not in js
    assert "/api/config" in js
    assert "mostrar" in js.lower() or "calculo" in js
    assert "ifr_max" in js
    assert "RTD" not in js
    assert "Preço atual" in js
    assert "Meta venc." in js
    assert "Vencimento" in js
    assert "Distância" in js
    assert "premio_bid" in js
    assert "option_symbol" in js
    assert "Prêmio (últ.)" in js
    assert "strike" in js
    assert "meta_premio_30d" in js
    assert "Calculadora de prêmio-alvo" in html
    assert 'id="calc-meta-30d"' in html
    assert 'id="calc-alvo"' in html
    meta_input = html.split('id="calc-meta-30d"', 1)[1].split(">", 1)[0]
    assert 'type="number"' not in meta_input
    assert "function parsePct" in js
    assert 'k === "meta_premio_30d"' in js
    assert 'num(v, "pct")' in js
    assert "parsePct(el.value)" in js
    assert "parsePct(metaEl.value)" in js
    assert "GRUPO_ABREV" in js
    assert "Utilities (Energia/Saneamento)" in js
    assert "tbl-dados" in js
    assert "tbl-setores" in js
    assert "nextSort" in js
    assert 'dir: 0' in js or "dir = 0" in js
    assert "aria-sort" in js
    assert "sort-asc" in css
    assert "sort-desc" in css
    assert "sort-ind" in css
    assert "colTitle" in js
    assert '["ticker", "ticker"]' in js
    assert "nROE" in js
    assert "tbl-vencimentos" in js
    assert "tbl-feriados" in js
    assert "vencLabel(raw)" in js
    assert "row-mensal" in js
    assert "chip-mensal" in js
    assert "row-mensal" in css
    assert 'placeholder="dd/mm/aaaa"' in html
    assert 'id="feriado-data"' in html
    assert 'type="date"' not in html.split('id="feriado-data"')[1][:80]
    assert "function parseBrDate" in js
    assert "function maskBrDate" in js
    assert "feriado-data-cal" in html
    assert "showPicker" in js
