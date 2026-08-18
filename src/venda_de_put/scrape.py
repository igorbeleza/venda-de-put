from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
import time
from typing import Optional

from venda_de_put.calendar_b3 import load_holidays
from venda_de_put.config import load_config
from venda_de_put.indicators import bollinger_lower, hv_log, rsi_wilder, sma
from venda_de_put.models import (
    AppConfig,
    AssetInput,
    Fundamentals,
    IvPoint,
    PutQuote,
    Snapshot,
    SourceStamp,
    TechnicalInput,
)
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
from venda_de_put.paths import data_dir as resolve_data_dir
from venda_de_put.paths import snapshot_current, snapshot_history
from venda_de_put.snapshot import read_snapshot, write_snapshot
from venda_de_put.sources.types import ChainSource, FundamentalsSource, IvSource, PriceSource
from venda_de_put.strike import recommended_tickers
from venda_de_put.tz import TZ


def _around_hhmm(now: datetime, hhmm: str, window_min: int = 30) -> bool:
    parts = str(hhmm).split(":")
    h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return abs((now - target).total_seconds()) <= window_min * 60


def should_fetch_fundamentus(
    now: datetime,
    cfg: AppConfig,
    previous: Snapshot | None,
    force_fundamentus: bool | None = None,
) -> bool:
    if force_fundamentus is True:
        return True
    if force_fundamentus is False:
        return False
    if previous is None or not previous.fundamentus_rows:
        return True
    local = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    if local.day not in cfg.fundamentus_days:
        return False
    has_today = False
    for s in previous.stamps:
        if s.source != "fundamentus":
            continue
        collected = s.collected_at
        if collected.tzinfo is None:
            collected = collected.replace(tzinfo=TZ)
        if collected.astimezone(TZ).date() == local.date():
            has_today = True
            break
    return _around_hhmm(local, cfg.fundamentus_time) or not has_today


def run_scrape(
    price: PriceSource,
    iv: IvSource,
    fundamentals: FundamentalsSource,
    cfg: AppConfig,
    universe: dict[str, str],
    holidays: set[date],
    now: datetime,
    previous: Snapshot | None = None,
    chain_source: ChainSource | None = None,
    chain_pause: float = 0.0,
    force_fundamentus: bool | None = None,
) -> Snapshot:
    tickers = list(universe.keys())
    stamps: list[SourceStamp] = []

    series: dict = {}
    try:
        series = price.fetch(tickers)
        # YahooHttp swallows per-ticker failures and may return {}; treat zero
        # matches as a failed source so the stamp is not ok=True on total outage.
        matched = sum(1 for t in tickers if t in series)
        if not tickers or matched * 2 < len(tickers):
            stamps.append(
                SourceStamp(
                    "yahoo",
                    now,
                    False,
                    "fewer than half of requested tickers" if tickers else "no tickers",
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
                t = a.technicals
                if t is not None and (
                    t.iv is not None or t.iv_rank is not None or t.iv_percentile is not None
                ):
                    iv_pts[a.ticker] = IvPoint(
                        a.ticker, t.iv, t.iv_rank, t.iv_percentile
                    )

    fund_rows: list[Fundamentals] = []
    if should_fetch_fundamentus(now, cfg, previous, force_fundamentus=force_fundamentus):
        try:
            fund_rows = fundamentals.fetch()
            stamps.append(SourceStamp("fundamentus", now, True, None, False))
        except Exception as e:
            stamps.append(SourceStamp("fundamentus", now, False, str(e), True))
            if previous is not None:
                fund_rows = list(previous.fundamentus_rows)
    else:
        if previous is not None:
            fund_rows = list(previous.fundamentus_rows)
            prev_stamp = next((s for s in previous.stamps if s.source == "fundamentus"), None)
            if prev_stamp is not None:
                stamps.append(prev_stamp)

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
        if ivp is not None:
            iv_val, iv_rank, iv_pct = ivp.iv, ivp.iv_rank, ivp.iv_percentile
        elif prev is not None:
            iv_val, iv_rank, iv_pct = prev.iv, prev.iv_rank, prev.iv_percentile
        else:
            iv_val = iv_rank = iv_pct = None
        tech = TechnicalInput(
            preco=preco,
            mm200=mm200,
            ifr=ifr,
            boll_inf=boll,
            iv=iv_val,
            hv=hv,
            iv_rank=iv_rank,
            iv_percentile=iv_pct,
        )
        assets.append(apply_technical(fund, tech, cfg))

    lists = build_lists(assets)
    prev_chains: dict[str, list[PutQuote]] = {}
    if previous is not None:
        prev_chains = dict(previous.chains)
    chains = _fetch_chains(
        chain_source,
        recommended_tickers(lists),
        prev_chains,
        stamps,
        now,
        chain_pause,
    )
    return Snapshot(
        generated_at=now,
        stamps=stamps,
        assets=assets,
        lists=lists,
        fundamentus_rows=fund_rows,
        chains=chains,
    )


def _fetch_chains(
    chain_source: ChainSource | None,
    tickers: list[str],
    previous: dict[str, list[PutQuote]],
    stamps: list[SourceStamp],
    now: datetime,
    pause: float,
) -> dict[str, list[PutQuote]]:
    if chain_source is None:
        return previous
    out: dict[str, list[PutQuote]] = dict(previous)
    failed: list[str] = []
    ok_n = 0
    for i, ticker in enumerate(tickers):
        if i and pause > 0:
            time.sleep(pause)
        try:
            out[ticker] = chain_source.fetch_chain(ticker)
            ok_n += 1
        except Exception:
            failed.append(ticker)
            if ticker not in out and ticker in previous:
                out[ticker] = previous[ticker]
    if tickers:
        stamps.append(
            SourceStamp(
                "oplab_cadeia",
                now,
                ok_n > 0,
                None if not failed else "falha: " + ",".join(failed),
                ok_n == 0,
            )
        )
    return out


def cli_scrape(
    data_dir: Path | str | None = None,
    force_fundamentus: bool | None = None,
) -> int:
    root = resolve_data_dir(data_dir)
    current = snapshot_current(root)
    history = snapshot_history(root)
    cfg = load_config(root / "config.json")
    universe = json.loads((root / "universe.json").read_text(encoding="utf-8"))
    holidays = load_holidays(root / "feriados.json")
    now = datetime.now(TZ)
    previous: Optional[Snapshot] = None
    legacy = root / "current.json"
    if current.is_file():
        previous = read_snapshot(current)
    elif legacy.is_file():
        previous = read_snapshot(legacy)
    from venda_de_put.sources.fundamentus import FundamentusHttp
    from venda_de_put.sources.oplab import OplabHttp
    from venda_de_put.sources.yahoo import YahooHttp

    oplab = OplabHttp()
    snap = run_scrape(
        YahooHttp(),
        oplab,
        FundamentusHttp(),
        cfg,
        universe,
        holidays,
        now,
        previous=previous,
        chain_source=oplab,
        chain_pause=0.35,
        force_fundamentus=force_fundamentus,
    )
    write_snapshot(snap, current, history, archive_if_1600=True)
    return 0
