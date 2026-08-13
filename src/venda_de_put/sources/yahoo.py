from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Optional

import httpx

from venda_de_put.models import CandleSeries
from venda_de_put.sources.types import USER_AGENT
from venda_de_put.tz import TZ

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.SA?range=2y&interval=1d"


def parse_yahoo_chart(payload: dict, ticker: str) -> CandleSeries:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise ValueError(f"Yahoo chart sem result para {ticker}")
    result = results[0]
    meta = result.get("meta") or {}
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes_raw = quotes.get("close") or []
    closes: list[Optional[float]] = []
    for c in closes_raw:
        closes.append(None if c is None else float(c))
    high = meta.get("fiftyTwoWeekHigh")
    low = meta.get("fiftyTwoWeekLow")
    preco = meta.get("regularMarketPrice")
    return CandleSeries(
        ticker=ticker,
        closes=closes,
        preco=None if preco is None else float(preco),
        max_52=None if high is None else float(high),
        min_52=None if low is None else float(low),
        collected_at=datetime.now(TZ),
    )


class YahooHttp:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._owns = client is None

    def _client_or(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)

    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        client = self._client_or()
        out: dict[str, CandleSeries] = {}
        try:
            for i, ticker in enumerate(tickers):
                if i:
                    time.sleep(random.uniform(0.15, 0.25))
                url = YAHOO_CHART.format(ticker=ticker)
                if "range=max" in url:
                    raise ValueError("Yahoo URL não pode usar range=max")
                last_err: Exception | None = None
                for _attempt in range(2):
                    try:
                        resp = client.get(url, headers={"User-Agent": USER_AGENT})
                        resp.raise_for_status()
                        out[ticker] = parse_yahoo_chart(resp.json(), ticker)
                        last_err = None
                        break
                    except Exception as exc:
                        last_err = exc
                if last_err is not None:
                    continue
        finally:
            if self._owns and self._client is None:
                client.close()
        return out
