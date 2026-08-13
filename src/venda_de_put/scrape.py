from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from venda_de_put.calendar_b3 import load_holidays
from venda_de_put.config import load_config
from venda_de_put.indicators import bollinger_lower, hv_log, rsi_wilder, sma
from venda_de_put.models import (
    AppConfig,
    AssetInput,
    Fundamentals,
    IvPoint,
    Snapshot,
    SourceStamp,
    TechnicalInput,
)
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
from venda_de_put.snapshot import read_snapshot, write_snapshot
from venda_de_put.sources.types import FundamentalsSource, IvSource, PriceSource
from venda_de_put.tz import TZ

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CURRENT = DATA / "snapshots" / "current.json"
HISTORY = DATA / "snapshots" / "history"


def run_scrape(
    price: PriceSource,
    iv: IvSource,
    fundamentals: FundamentalsSource,
    cfg: AppConfig,
    universe: dict[str, str],
    holidays: set[date],
    now: datetime,
    previous: Snapshot | None = None,
) -> Snapshot:
    tickers = list(universe.keys())
    stamps: list[SourceStamp] = []

    series: dict = {}
    try:
        series = price.fetch(tickers)
        # YahooHttp swallows per-ticker failures and may return {}; treat zero
        # matches as a failed source so the stamp is not ok=True on total outage.
        if not any(t in series for t in tickers):
            series = {}
            stamps.append(
                SourceStamp(
                    "yahoo",
                    now,
                    False,
                    "no series for requested tickers",
                    True,
                )
            )
        else:
            stamps.append(SourceStamp("yahoo", now, True, None, False))
    except Exception as e:
        stamps.append(SourceStamp("yahoo", now, False, str(e), True))

    iv_pts: dict[str, IvPoint] = {}
    try:
        iv_pts = iv.fetch()
        stamps.append(SourceStamp("oplab", now, True, None, False))
    except Exception as e:
        stamps.append(SourceStamp("oplab", now, False, str(e), True))
        if previous is not None:
            for a in previous.assets:
                if a.technicals and a.technicals.iv is not None:
                    iv_pts[a.ticker] = IvPoint(
                        a.ticker, a.technicals.iv, None, None
                    )

    fund_rows: list[Fundamentals] = []
    try:
        fund_rows = fundamentals.fetch()
        stamps.append(SourceStamp("fundamentus", now, True, None, False))
    except Exception as e:
        stamps.append(SourceStamp("fundamentus", now, False, str(e), True))
        if previous is not None:
            fund_rows = list(previous.fundamentus_rows)

    by_ticker = {r.ticker: r for r in fund_rows}
    prev_tech = {}
    if previous is not None:
        prev_tech = {a.ticker: a.technicals for a in previous.assets if a.technicals}

    inputs: list[AssetInput] = []
    for ticker, grupo in universe.items():
        row = by_ticker.get(ticker)
        inputs.append(
            AssetInput(
                ticker=ticker,
                grupo=grupo,
                pl=None if row is None else row.pl,
                pvp=None if row is None else row.pvp,
                ev_ebitda=None if row is None else row.ev_ebitda,
                mrg_liq=None if row is None else row.mrg_liq,
                liq_corr=None if row is None else row.liq_corr,
                roic=None if row is None else row.roic,
                roe=None if row is None else row.roe,
                div_pat=None if row is None else row.div_liq_patrim,
                cresc=None if row is None else row.cresc_rec_5a,
            )
        )

    funds = score_fundamentals(inputs)
    assets = []
    for fund in funds:
        candle = series.get(fund.ticker)
        prev = prev_tech.get(fund.ticker)
        ivp = iv_pts.get(fund.ticker)
        if candle is not None:
            mm200 = sma(candle.closes, cfg.mm_periodos)
            ifr = rsi_wilder(candle.closes, cfg.ifr_periodos)
            boll = bollinger_lower(candle.closes, cfg.boll_periodos, cfg.boll_desvios)
            hv = hv_log(candle.closes, cfg.hv_periodos)
            preco = candle.preco
        elif prev is not None:
            mm200, ifr, boll, hv, preco = (
                prev.mm200,
                prev.ifr,
                prev.boll_inf,
                prev.hv,
                prev.preco,
            )
        else:
            mm200 = ifr = boll = hv = preco = None
        iv_val = ivp.iv if ivp is not None else (prev.iv if prev is not None else None)
        tech = TechnicalInput(
            preco=preco,
            mm200=mm200,
            ifr=ifr,
            boll_inf=boll,
            iv=iv_val,
            hv=hv,
        )
        assets.append(apply_technical(fund, tech, cfg))

    lists = build_lists(assets)
    return Snapshot(
        generated_at=now,
        stamps=stamps,
        assets=assets,
        lists=lists,
        fundamentus_rows=fund_rows,
    )


def cli_scrape() -> int:
    cfg = load_config(DATA / "config.json")
    universe = json.loads((DATA / "universe.json").read_text(encoding="utf-8"))
    holidays = load_holidays(DATA / "feriados.json")
    now = datetime.now(TZ)
    previous: Optional[Snapshot] = None
    if CURRENT.is_file():
        previous = read_snapshot(CURRENT)
    from venda_de_put.sources.fundamentus import FundamentusHttp
    from venda_de_put.sources.oplab import OplabHttp
    from venda_de_put.sources.yahoo import YahooHttp

    snap = run_scrape(
        YahooHttp(),
        OplabHttp(),
        FundamentusHttp(),
        cfg,
        universe,
        holidays,
        now,
        previous=previous,
    )
    write_snapshot(snap, CURRENT, HISTORY, archive_if_1600=True)
    return 0
