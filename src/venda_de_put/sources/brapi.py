from __future__ import annotations

import os
import httpx

from venda_de_put.sources.types import USER_AGENT

BRAPI_QUOTE = "https://brapi.dev/api/v2/stocks/quote"


def parse_brapi_quote(payload: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in payload.get("results") or []:
        sym = row.get("symbol")
        px = row.get("regularMarketPrice")
        if not sym or px is None:
            continue
        try:
            out[str(sym)] = float(px)
        except (TypeError, ValueError):
            continue
    return out


class BrapiSpotHttp:
    def __init__(
        self,
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if token is None:
            token = os.environ.get("VENDA_DE_PUT_BRAPI_TOKEN", "")
        self._token = (token or "").strip()
        self._client = client
        self._owns = client is None

    def fetch_spots(self, tickers: list[str]) -> dict[str, float]:
        if not self._token or not tickers:
            return {}
        client = self._client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30.0
        )
        try:
            resp = client.get(
                BRAPI_QUOTE,
                params={"symbols": ",".join(tickers)},
                headers={
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {self._token}",
                },
            )
            resp.raise_for_status()
            return parse_brapi_quote(resp.json())
        except Exception:
            return {}
        finally:
            if self._owns and self._client is None:
                client.close()
