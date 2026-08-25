from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from venda_de_put.config import AppConfig
from venda_de_put.models import CandleSeries, Fundamentals, IvPoint, PutQuote
from venda_de_put.scrape import run_scrape
from venda_de_put.scrape_progress import FileProgress, PRICE_NOTICE, read_progress
from venda_de_put.snapshot import read_snapshot, write_snapshot
from venda_de_put.tz import TZ

class FakePrice:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series
        self.calls = 0

    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        self.calls += 1
        return {t: self.series[t] for t in tickers if t in self.series}

class FakeSpot:
    def __init__(self, spots: dict[str, float]):
        self.spots = spots
        self.calls: list[list[str]] = []

    def fetch_spots(self, tickers: list[str]) -> dict[str, float]:
        self.calls.append(list(tickers))
        return {t: self.spots[t] for t in tickers if t in self.spots}


class BoomSpot:
    def __init__(self):
        self.calls: list[list[str]] = []

    def fetch_spots(self, tickers: list[str]) -> dict[str, float]:
        self.calls.append(list(tickers))
        raise RuntimeError("brapi down")


class FakeHistory:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series
        self.calls: list[list[str]] = []

    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]:
        self.calls.append(list(tickers))
        return {t: self.series[t] for t in tickers if t in self.series}


class BoomPrice:
    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        raise RuntimeError("yahoo down")


def _serie_ontem(ticker: str, now: datetime, preco: float = 40.0) -> CandleSeries:
    yesterday = int(datetime(2026, 8, 14, 18, 0, tzinfo=TZ).timestamp())
    return CandleSeries(
        ticker=ticker,
        closes=[30.0] * 210,
        preco=preco,
        max_52=45.0,
        min_52=20.0,
        collected_at=now,
        timestamps=[yesterday] * 210,
    )

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


def test_run_scrape_marca_passos_ok_e_fundamentus_pulado(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    path = tmp_path / "scrape_progress.json"
    progress = FileProgress(path)
    later = now.replace(hour=13)
    run_scrape(
        price, iv, fund, AppConfig(), universe, set(), later,
        previous=first, progress=progress, force_fundamentus=False,
    )
    by = {s["id"]: s for s in read_progress(path)["passos"]}
    assert by["yahoo"]["status"] == "ok"
    assert by["oplab"]["status"] == "ok"
    assert by["fundamentus"]["status"] == "pulado"
    assert by["oplab_cadeia"]["status"] == "pulado"


def test_run_scrape_marca_oplab_falhou(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    path = tmp_path / "scrape_progress.json"
    progress = FileProgress(path)
    run_scrape(
        price, FakeIv({}, fail=True), fund, AppConfig(), universe, set(), now,
        previous=first, progress=progress, force_fundamentus=False,
    )
    by = {s["id"]: s for s in read_progress(path)["passos"]}
    assert by["oplab"]["status"] == "falhou"
    assert "oplab down" in (by["oplab"]["erro"] or "")


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
    assert stamp.error == PRICE_NOTICE
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
    assert stamp.error == PRICE_NOTICE
    vale = next(a for a in second.assets if a.ticker == "VALE3")
    assert vale.technicals is not None
    assert vale.technicals.preco == 40.0


def test_yahoo_cobre_todos_nao_chama_spot_nem_history():
    price, iv, fund, universe, now = _petr_inputs()
    spot = FakeSpot({"PETR4": 99.0})
    hist = FakeHistory({})
    snap = run_scrape(
        price, iv, fund, AppConfig(), universe, set(), now,
        spot=spot, history=hist,
    )
    assert spot.calls == []
    assert hist.calls == []
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert stamp.error is None


def test_yahoo_perde_com_tecnico_anterior_brapi_atualiza_preco():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    spot = FakeSpot({"PETR4": 50.0})
    hist = FakeHistory({})
    second = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=spot, history=hist,
    )
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 50.0
    assert petr.technicals.mm200 == petr_first.technicals.mm200
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert spot.calls[0] == ["PETR4"]
    assert hist.calls == []


def test_yahoo_perde_brapi_vazio_reusa_tudo_e_avisa():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    second = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=FakeSpot({}),
    )
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == petr_first.technicals.preco
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
    assert stamp.stale is True


def test_sem_anterior_cotahist_mais_spot_calcula_na_serie():
    price, iv, fund, universe, now = _petr_inputs()
    hist = FakeHistory({"PETR4": _serie_ontem("PETR4", now)})
    spot = FakeSpot({"PETR4": 41.75})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=spot, history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 41.75
    assert petr.technicals.mm200 is not None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert hist.calls[0] == ["PETR4"]


def test_sem_anterior_cotahist_falha_sem_spot_sem_dado():
    price, iv, fund, universe, now = _petr_inputs()
    hist = FakeHistory({})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=FakeSpot({}), history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco is None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE

def test_sem_anterior_sem_cotahist_brapi_preenche_preco_sem_indicadores():
    price, iv, fund, universe, now = _petr_inputs()
    spot = FakeSpot({"PETR4": 50.0})
    hist = FakeHistory({})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=spot, history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 50.0
    assert petr.technicals.mm200 is None
    assert petr.technicals.ifr is None
    assert petr.technicals.boll_inf is None
    assert petr.technicals.hv is None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert stamp.error is None



def test_price_fetch_excecao_ainda_chama_brapi():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    spot = FakeSpot({"PETR4": 50.0})
    second = run_scrape(
        BoomPrice(), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=spot,
    )
    assert spot.calls
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 50.0
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is True


def test_sem_anterior_cotahist_sem_spot_avisa():
    price, iv, fund, universe, now = _petr_inputs()
    hist = FakeHistory({"PETR4": _serie_ontem("PETR4", now, preco=40.0)})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=FakeSpot({}), history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 40.0
    assert petr.technicals.mm200 is not None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
    assert hist.calls[0] == ["PETR4"]


def test_snapshot_sem_dado_ainda_e_frio_na_proxima():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=FakeSpot({}), history=FakeHistory({}),
    )
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    assert petr_first.technicals.preco is None
    assert petr_first.technicals.mm200 is None
    hist = FakeHistory({"PETR4": _serie_ontem("PETR4", now, preco=40.0)})
    second = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=FakeSpot({}), history=hist,
    )
    assert hist.calls == [["PETR4"]]
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 40.0
    assert petr.technicals.mm200 is not None
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE


def test_dois_de_tres_yahoo_sem_brapi_avisa():
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
        AppConfig(), universe, set(), now,
    )
    second = run_scrape(
        FakePrice({"PETR4": series["PETR4"], "VALE3": series["VALE3"]}),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(), universe, set(), now, previous=first,
    )
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
    itub = next(a for a in second.assets if a.ticker == "ITUB4")
    assert itub.technicals.preco == 40.0


def test_yahoo_perde_um_brapi_cobre_passo_ok():
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
        AppConfig(), universe, set(), now,
    )
    second = run_scrape(
        FakePrice({"PETR4": series["PETR4"], "VALE3": series["VALE3"]}),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(), universe, set(), now, previous=first,
        spot=FakeSpot({"ITUB4": 41.0}),
    )
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is True
    itub = next(a for a in second.assets if a.ticker == "ITUB4")
    assert itub.technicals.preco == 41.0
    assert itub.technicals.mm200 == next(
        a.technicals.mm200 for a in first.assets if a.ticker == "ITUB4"
    )

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


def test_run_scrape_retry_oplab_nao_toca_yahoo_nem_fundamentus():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    price2 = FakePrice(price.series)
    fund2 = FakeFund(fund.rows)
    later = now.replace(hour=13)
    second = run_scrape(
        price2, iv, fund2, AppConfig(), universe, set(), later,
        previous=first, force_fundamentus=True, only_steps=("oplab", "oplab_cadeia"),
    )
    assert price2.calls == 0
    assert fund2.calls == 0
    assert iv.calls == 2
    yahoo = next(s for s in second.stamps if s.source == "yahoo")
    fund_st = next(s for s in second.stamps if s.source == "fundamentus")
    assert yahoo.ok is True
    assert fund_st.ok is True
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 41.75


def test_run_scrape_retry_cadeia_so_busca_cadeia():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    price2 = FakePrice(price.series)
    iv2 = FakeIv(iv.pts)
    fund2 = FakeFund(fund.rows)
    chain = FakeChain({})
    run_scrape(
        price2, iv2, fund2, AppConfig(), universe, set(), now,
        previous=first, chain_source=chain, only_steps=("oplab_cadeia",),
    )
    assert price2.calls == 0
    assert iv2.calls == 0
    assert fund2.calls == 0
    assert chain.calls


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


def test_cli_scrape_instancia_brapi_e_cotahist():
    src = Path("src/venda_de_put/scrape.py").read_text(encoding="utf-8")
    assert "BrapiSpotHttp" in src
    assert "CotahistBootstrap" in src
    assert "spot=BrapiSpotHttp()" in src
    assert 'CotahistBootstrap(root / "cotahist"' in src
    assert "history=CotahistBootstrap" in src
    assert "history_dir = snapshot_history(root)" in src
    assert "write_snapshot(snap, current, history_dir" in src
    assert "history = snapshot_history(root)" not in src


def test_env_example_documenta_brapi_token():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "VENDA_DE_PUT_BRAPI_TOKEN=" in text
