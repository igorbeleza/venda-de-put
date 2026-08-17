"""Compara indicadores no close Yahoo vs à vista do instante como último período."""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path

import httpx

from venda_de_put.config import load_config
from venda_de_put.indicators import (
    apply_spot_as_last_period,
    bollinger_lower,
    hv_log,
    rsi_wilder,
    sma,
)
from venda_de_put.models import AppConfig, TechnicalInput
from venda_de_put.scoring import apply_technical
from venda_de_put.scoring import score_fundamentals
from venda_de_put.models import AssetInput
from venda_de_put.sources.types import USER_AGENT
from venda_de_put.sources.yahoo import YAHOO_CHART
from venda_de_put.tz import TZ

ROOT = Path(__file__).resolve().parents[1]


def _raw_series(payload: dict) -> tuple[list, list, float | None]:
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError("sem result")
    meta = result.get("meta") or {}
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = [None if c is None else float(c) for c in (quotes.get("close") or [])]
    stamps = [None if t is None else int(t) for t in (result.get("timestamp") or [])]
    preco = meta.get("regularMarketPrice")
    return closes, stamps, None if preco is None else float(preco)


def _tech(closes, preco: float | None, cfg: AppConfig) -> TechnicalInput:
    return TechnicalInput(
        preco=preco,
        mm200=sma(closes, cfg.mm_periodos),
        ifr=rsi_wilder(closes, cfg.ifr_periodos),
        boll_inf=bollinger_lower(closes, cfg.boll_periodos, cfg.boll_desvios),
        iv=None,
        hv=hv_log(closes, cfg.hv_periodos),
    )


def _sinal(ticker: str, grupo: str, tech: TechnicalInput, cfg: AppConfig) -> str:
    fund = score_fundamentals(
        [AssetInput(ticker, grupo, None, None, None, None, None, None, None, None, None)]
    )[0]
    scored = apply_technical(fund, tech, cfg)
    return scored.sinal or "sem dado"


def main() -> int:
    cfg = load_config(ROOT / "data" / "config.json")
    universe = json.loads((ROOT / "data" / "universe.json").read_text(encoding="utf-8"))
    now = datetime.now(TZ)
    rows = []
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)
    try:
        for i, ticker in enumerate(universe):
            if i:
                time.sleep(random.uniform(0.15, 0.25))
            url = YAHOO_CHART.format(ticker=ticker)
            last_err = None
            payload = None
            for _ in range(2):
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    payload = resp.json()
                    last_err = None
                    break
                except Exception as exc:
                    last_err = exc
            if payload is None:
                rows.append({"ticker": ticker, "erro": str(last_err)})
                continue
            raw, stamps, preco = _raw_series(payload)
            last_close = next((v for v in reversed(raw) if v is not None), None)
            adj = apply_spot_as_last_period(raw, preco, stamps, now)
            old = _tech(raw, preco, cfg)
            new = _tech(adj, preco, cfg)
            drop_pct = None
            if preco is not None and last_close not in (None, 0):
                drop_pct = (preco - last_close) / last_close
            rows.append(
                {
                    "ticker": ticker,
                    "preco": preco,
                    "last_close": last_close,
                    "drop_pct": drop_pct,
                    "modo": "troca" if len(adj) == len(raw) else "anexa",
                    "mm200_old": old.mm200,
                    "mm200_new": new.mm200,
                    "ifr_old": old.ifr,
                    "ifr_new": new.ifr,
                    "boll_old": old.boll_inf,
                    "boll_new": new.boll_inf,
                    "hv_old": old.hv,
                    "hv_new": new.hv,
                    "sinal_old": _sinal(ticker, universe[ticker], old, cfg),
                    "sinal_new": _sinal(ticker, universe[ticker], new, cfg),
                }
            )
    finally:
        client.close()

    def _diff(a, b) -> bool:
        if a is None and b is None:
            return False
        if a is None or b is None:
            return True
        return abs(a - b) > 1e-6

    ok = [r for r in rows if "erro" not in r]
    price_moved = [
        r
        for r in ok
        if r["preco"] is not None
        and r["last_close"] is not None
        and abs(r["preco"] - r["last_close"]) > 0.005
    ]
    changed = [
        r
        for r in ok
        if _diff(r["ifr_old"], r["ifr_new"])
        or _diff(r["boll_old"], r["boll_new"])
        or _diff(r["mm200_old"], r["mm200_new"])
        or r["sinal_old"] != r["sinal_new"]
    ]
    changed.sort(key=lambda r: (r["drop_pct"] is None, r["drop_pct"] or 0.0))
    price_moved.sort(key=lambda r: (r["drop_pct"] is None, r["drop_pct"] or 0.0))

    print(
        f"coletado {now.isoformat()}  tickers={len(ok)}/{len(universe)}  "
        f"|preco-close|>0,5c={len(price_moved)}  indicadores mudaram={len(changed)}"
    )
    print(
        f"{'ticker':<8} {'Δ%':>7} {'modo':<5} {'IFR→':>14} {'Boll Inf→':>22} {'MM200→':>20} {'SINAL'}"
    )
    for r in changed[:40]:
        d = "sem" if r["drop_pct"] is None else f"{r['drop_pct']*100:+.2f}"
        ifr = f"{r['ifr_old']:.1f}→{r['ifr_new']:.1f}" if r["ifr_old"] is not None and r["ifr_new"] is not None else "sem dado"
        boll = (
            f"{r['boll_old']:.2f}→{r['boll_new']:.2f}"
            if r["boll_old"] is not None and r["boll_new"] is not None
            else "sem dado"
        )
        mm = (
            f"{r['mm200_old']:.2f}→{r['mm200_new']:.2f}"
            if r["mm200_old"] is not None and r["mm200_new"] is not None
            else "sem dado"
        )
        sinal = r["sinal_old"] if r["sinal_old"] == r["sinal_new"] else f"{r['sinal_old']}→{r['sinal_new']}"
        print(f"{r['ticker']:<8} {d:>7} {r['modo']:<5} {ifr:>14} {boll:>22} {mm:>20} {sinal}")

    if not changed:
        print("(nenhum indicador mudou além de 1e-6 — Yahoo já tinha o à vista na barra de hoje)")
    flips = [r for r in changed if r["sinal_old"] != r["sinal_new"]]
    print(f"\nSINAL mudou em {len(flips)}: {', '.join(r['ticker'] for r in flips) or '(nenhum)'}")
    fails = [r for r in rows if "erro" in r]
    if fails:
        print("falhas: " + ", ".join(f"{r['ticker']}" for r in fails))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
