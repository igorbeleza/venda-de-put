from datetime import date, datetime
from pathlib import Path

from venda_de_put.config import AppConfig
from venda_de_put.models import CandleSeries, Fundamentals, IvPoint, PutQuote
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
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
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
    assert back.assets[0].technicals.iv_rank == 40
    assert back.assets[0].technicals.iv_percentile == 0.55


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
    assert petr.technicals.iv_rank == 40
    assert petr.technicals.iv_percentile == 0.55
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


def test_yahoo_half_tickers_stamps_failed_and_merges_previous():
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    universe = {"PETR4": "A", "VALE3": "B", "ITUB4": "C"}
    series = {
        t: CandleSeries(t, [30.0] * 210, 40.0, 45.0, 20.0, now)
        for t in universe
    }
    first = run_scrape(
        FakePrice(series),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(),
        universe,
        set(),
        now,
    )
    second = run_scrape(
        FakePrice({"PETR4": series["PETR4"]}),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(),
        universe,
        set(),
        now,
        previous=first,
    )
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    vale = next(a for a in second.assets if a.ticker == "VALE3")
    assert vale.technicals is not None
    assert vale.technicals.preco == 40.0


def test_fundamentus_not_fetched_at_1100_when_previous_exists():
    price, iv, fund, universe, now16 = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now16)
    assert fund.calls == 1
    later = datetime(2026, 8, 15, 11, 0, tzinfo=TZ)
    fund2 = FakeFund(fund.rows)
    second = run_scrape(price, iv, fund2, AppConfig(), universe, set(), later, previous=first)
    assert fund2.calls == 0
    assert second.fundamentus_rows == first.fundamentus_rows


class FakeChain:
    def __init__(self, data, fail=None):
        self.data = data
        self.fail = set(fail or [])
        self.calls: list[str] = []

    def fetch_chain(self, ticker: str):
        self.calls.append(ticker)
        if ticker in self.fail:
            raise RuntimeError("cadeia down")
        return list(self.data.get(ticker, []))


def test_scrape_guarda_cadeia_dos_recomendados_e_sobrevive_roundtrip(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    puts = [
        PutQuote(date(2026, 8, 21), 40.86, 0.28, 0.32, -0.266, 0.279, 120.0, 0.28, "PETRX406"),
    ]
    chain = FakeChain({"PETR4": puts})
    snap = run_scrape(
        price, iv, fund, AppConfig(), universe, set(), now, chain_source=chain
    )
    assert chain.calls == ["PETR4"]
    assert snap.chains["PETR4"][0].bid == 0.28
    path = tmp_path / "current.json"
    write_snapshot(snap, path, tmp_path / "history", archive_if_1600=False)
    back = read_snapshot(path)
    assert back.chains["PETR4"][0].strike == 40.86
    assert back.chains["PETR4"][0].due_date == date(2026, 8, 21)
    assert back.chains["PETR4"][0].last == 0.28
    assert back.chains["PETR4"][0].symbol == "PETRX406"


def test_scrape_cadeia_falha_mantem_anterior():
    price, iv, fund, universe, now = _petr_inputs()
    puts = [PutQuote(date(2026, 8, 21), 40.86, 0.28, 0.32, -0.266, 0.279, 10.0, 0.28, "PETRX406")]
    first = run_scrape(
        price, iv, fund, AppConfig(), universe, set(), now,
        chain_source=FakeChain({"PETR4": puts}),
    )
    second = run_scrape(
        price, iv, fund, AppConfig(), universe, set(), now,
        previous=first,
        chain_source=FakeChain({}, fail={"PETR4"}),
    )
    assert second.chains["PETR4"][0].bid == 0.28
    stamp = next(s for s in second.stamps if s.source == "oplab_cadeia")
    assert stamp.ok is False


def test_fundamentus_fetched_on_first_scrape_when_no_previous():
    price, iv, fund, universe, _ = _petr_inputs()
    now = datetime(2026, 8, 13, 11, 0, tzinfo=TZ)  # not day 1 or 15
    snap = run_scrape(price, iv, fund, AppConfig(), universe, set(), now, previous=None)
    assert fund.calls == 1
    assert snap.fundamentus_rows == fund.rows


def test_force_fundamentus_true_forces_fetch():
    price, iv, fund, universe, now16 = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now16)
    assert fund.calls == 1

    # Mesmo dia e horário fora da janela, com previous existente: normal seria pular
    later = datetime(2026, 8, 15, 11, 0, tzinfo=TZ)
    fund2 = FakeFund(fund.rows)
    second = run_scrape(
        price, iv, fund2, AppConfig(), universe, set(), later,
        previous=first, force_fundamentus=True,
    )
    assert fund2.calls == 1


def test_force_fundamentus_false_skips_fetch():
    price, iv, fund, universe, _ = _petr_inputs()
    # Dia 1 às 07:00 (janela normal de fetch do fundamentus)
    now1 = datetime(2026, 8, 1, 7, 0, tzinfo=TZ)
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now1)
    assert fund.calls == 1

    fund2 = FakeFund(fund.rows)
    second = run_scrape(
        price, iv, fund2, AppConfig(), universe, set(), now1,
        previous=first, force_fundamentus=False,
    )
    assert fund2.calls == 0
    assert second.fundamentus_rows == first.fundamentus_rows


def test_force_fundamentus_none_keeps_default_behavior():
    price, iv, fund, universe, now16 = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now16)
    assert fund.calls == 1

    later = datetime(2026, 8, 15, 11, 0, tzinfo=TZ)
    fund2 = FakeFund(fund.rows)
    second = run_scrape(
        price, iv, fund2, AppConfig(), universe, set(), later,
        previous=first, force_fundamentus=None,
    )
    assert fund2.calls == 0

