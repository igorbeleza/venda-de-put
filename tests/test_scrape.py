from datetime import datetime
from pathlib import Path

from venda_de_put.config import AppConfig
from venda_de_put.models import CandleSeries, Fundamentals, IvPoint
from venda_de_put.scrape import run_scrape
from venda_de_put.snapshot import read_snapshot, write_snapshot
from venda_de_put.tz import TZ


class FakePrice:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series
        self.calls = 0

    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        self.calls += 1
        return {t: self.series[t] for t in tickers if t in self.series}


class FakeIv:
    def __init__(self, pts: dict[str, IvPoint], fail: bool = False):
        self.pts = pts
        self.fail = fail
        self.calls = 0

    def fetch(self) -> dict[str, IvPoint]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("oplab down")
        return self.pts


class FakeFund:
    def __init__(self, rows: list[Fundamentals]):
        self.rows = rows
        self.calls = 0

    def fetch(self) -> list[Fundamentals]:
        self.calls += 1
        return self.rows


def _petr_inputs():
    now = datetime(2026, 8, 13, 16, 0, tzinfo=TZ)
    price = FakePrice({
        "PETR4": CandleSeries(
            ticker="PETR4",
            closes=[30.0] * 210,
            preco=41.75,
            max_52=45.0,
            min_52=28.0,
            collected_at=now,
        )
    })
    iv = FakeIv({"PETR4": IvPoint("PETR4", iv=0.35, iv_rank=40, iv_percentile=0.55)})
    fund = FakeFund([
        Fundamentals(
            ticker="PETR4", cotacao=41.75, pl=6.0, pvp=1.2, psr=None, dy=0.1,
            p_ativo=None, p_cap_giro=None, p_ebit=None, p_ativ_circ_liq=None,
            ev_ebit=None, ev_ebitda=4.0, mrg_bruta=None, mrg_ebit=None,
            mrg_liq=0.2, liq_corr=1.1, roic=0.15, roe=0.22, liq_2meses=None,
            patrim_liq=None, div_liq_patrim=0.4, cresc_rec_5a=0.1,
        )
    ])
    universe = {"PETR4": "Petróleo e Gás"}
    return price, iv, fund, universe, now


def test_write_and_read_roundtrip(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    snap = run_scrape(price, iv, fund, AppConfig(), universe, holidays=set(), now=now)
    path = tmp_path / "current.json"
    write_snapshot(snap, path, tmp_path / "history", archive_if_1600=False)
    back = read_snapshot(path)
    assert back.assets[0].ticker == "PETR4"
    assert back.assets[0].technicals.iv == 0.35


def test_run_scrape_uses_adapters_once():
    price, iv, fund, universe, now = _petr_inputs()
    snap = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    assert price.calls == 1 and iv.calls == 1 and fund.calls == 1
    assert snap.lists.fundamentalista[0].ticker == "PETR4"


def test_failed_source_keeps_previous_block(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    write_snapshot(first, tmp_path / "current.json", tmp_path / "history", False)
    iv2 = FakeIv({}, fail=True)
    second = run_scrape(price, iv2, fund, AppConfig(), universe, set(), now, previous=first)
    assert iv2.calls == 1
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.iv == 0.35
    stamp = next(s for s in second.stamps if s.source == "oplab")
    assert stamp.ok is False
    assert stamp.stale is True


def test_empty_yahoo_fetch_stamps_failed_and_reuses_previous():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    assert petr_first.technicals is not None
    assert petr_first.technicals.iv == 0.35
    assert petr_first.technicals.preco == 41.75

    empty_price = FakePrice({})
    second = run_scrape(
        empty_price, iv, fund, AppConfig(), universe, set(), now, previous=first
    )
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.stale is True
    assert stamp.error
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals is not None
    assert petr.technicals.iv == 0.35
    assert petr.technicals.preco == 41.75
    assert petr.technicals.mm200 == petr_first.technicals.mm200
    assert petr.technicals.ifr == petr_first.technicals.ifr
