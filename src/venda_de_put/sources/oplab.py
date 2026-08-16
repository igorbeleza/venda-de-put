from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional

import httpx

from venda_de_put.models import IvPoint, PutQuote
from venda_de_put.sources.types import USER_AGENT
from venda_de_put.strike import MAX_CHAIN_DAYS

OPLAB_URL = "https://opcoes.oplab.com.br/mercado-de-opcoes"
OPLAB_CHAIN_URL = "https://opcoes.oplab.com.br/mercado/acoes/opcoes/{ticker}"

_NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _opt_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _opt_pct(val: Any) -> Optional[float]:
    n = _opt_float(val)
    if n is None:
        return None
    if n > 1:
        return n / 100.0
    return n


def parse_oplab_next_data(html: str) -> dict[str, IvPoint]:
    m = _NEXT_DATA.search(html)
    if not m:
        raise ValueError("OpLab: script #__NEXT_DATA__ ausente")
    data = json.loads(m.group(1))
    stocks = ((data.get("props") or {}).get("pageProps") or {}).get("stocks")
    if stocks is None:
        raise ValueError("OpLab: props.pageProps.stocks ausente")
    out: dict[str, IvPoint] = {}
    for row in stocks:
        symbol = (row or {}).get("symbol")
        if not symbol:
            continue
        ticker = str(symbol)
        out[ticker] = IvPoint(
            ticker=ticker,
            iv=_opt_float(row.get("iv_current")),
            iv_rank=_opt_float(row.get("iv_1y_rank")),
            iv_percentile=_opt_float(row.get("iv_1y_percentile")),
        )
    return out


def parse_oplab_chain(html: str, today: date, max_days: int = MAX_CHAIN_DAYS) -> list[PutQuote]:
    m = _NEXT_DATA.search(html)
    if not m:
        raise ValueError("OpLab cadeia: script #__NEXT_DATA__ ausente")
    data = json.loads(m.group(1))
    series = ((data.get("props") or {}).get("pageProps") or {}).get("series")
    if series is None:
        raise ValueError("OpLab cadeia: props.pageProps.series ausente")
    out: list[PutQuote] = []
    for ser in series:
        if not ser:
            continue
        raw_due = ser.get("due_date")
        if not raw_due:
            continue
        try:
            due = date.fromisoformat(str(raw_due)[:10])
        except ValueError:
            continue
        dias = (due - today).days
        if dias <= 0 or dias > max_days:
            continue
        for row in ser.get("strikes") or []:
            if not row:
                continue
            strike = _opt_float(row.get("strike"))
            if strike is None:
                continue
            put = row.get("put") or {}
            bs = put.get("bs") or {}
            symbol = put.get("symbol")
            out.append(
                PutQuote(
                    due_date=due,
                    strike=strike,
                    bid=_opt_float(put.get("bid")),
                    ask=_opt_float(put.get("ask")),
                    delta=_opt_float(bs.get("delta")),
                    poe=_opt_pct(bs.get("poe")),
                    volume=_opt_float(put.get("volume")),
                    last=_opt_float(put.get("close")),
                    symbol=None if not symbol else str(symbol),
                )
            )
    return out


class OplabHttp:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self) -> dict[str, IvPoint]:
        client = self._client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)
        owns = self._client is None
        try:
            resp = client.get(OPLAB_URL, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return parse_oplab_next_data(resp.text)
        finally:
            if owns:
                client.close()

    def fetch_chain(self, ticker: str, today: date | None = None) -> list[PutQuote]:
        client = self._client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0)
        owns = self._client is None
        try:
            url = OPLAB_CHAIN_URL.format(ticker=ticker)
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return parse_oplab_chain(resp.text, today or date.today())
        finally:
            if owns:
                client.close()
