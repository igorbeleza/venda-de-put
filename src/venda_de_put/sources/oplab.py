from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from venda_de_put.models import IvPoint
from venda_de_put.sources.types import USER_AGENT

OPLAB_URL = "https://opcoes.oplab.com.br/mercado-de-opcoes"

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
