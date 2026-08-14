from __future__ import annotations

from typing import Optional

import httpx
from bs4 import BeautifulSoup

from venda_de_put.models import Fundamentals
from venda_de_put.sources.types import USER_AGENT

FUNDAMENTUS_URL = "https://fundamentus.com.br/resultado.php"

_FIELD_ORDER = (
    "ticker",
    "cotacao",
    "pl",
    "pvp",
    "psr",
    "dy",
    "p_ativo",
    "p_cap_giro",
    "p_ebit",
    "p_ativ_circ_liq",
    "ev_ebit",
    "ev_ebitda",
    "mrg_bruta",
    "mrg_ebit",
    "mrg_liq",
    "liq_corr",
    "roic",
    "roe",
    "liq_2meses",
    "patrim_liq",
    "div_liq_patrim",
    "cresc_rec_5a",
)

# Colunas que o site publica com "%". O app guarda fração (17,72% → 0.1772).
PCT_FIELDS = frozenset({
    "dy",
    "mrg_bruta",
    "mrg_ebit",
    "mrg_liq",
    "roic",
    "roe",
    "cresc_rec_5a",
})


def parse_pt_br_number(text: str) -> Optional[float]:
    s = (text or "").strip()
    if not s or s in {"-", "–", "—"}:
        return None
    s = s.replace("%", "").strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_fundamentus_html(raw: bytes) -> list[Fundamentals]:
    html = raw.decode("iso-8859-1")
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    rows: list[Fundamentals] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 22:
            continue
        texts = [c.get_text(strip=True) for c in cells[:22]]
        papel = texts[0]
        if not papel:
            continue
        nums = [parse_pt_br_number(t) for t in texts[1:]]
        kwargs = {"ticker": papel}
        for name, val in zip(_FIELD_ORDER[1:], nums):
            if name in PCT_FIELDS and val is not None:
                val = val / 100.0
            kwargs[name] = val
        rows.append(Fundamentals(**kwargs))
    return rows


class FundamentusHttp:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self) -> list[Fundamentals]:
        client = self._client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)
        owns = self._client is None
        try:
            resp = client.get(FUNDAMENTUS_URL, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return parse_fundamentus_html(resp.content)
        finally:
            if owns:
                client.close()
