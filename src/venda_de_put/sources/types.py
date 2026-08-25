from typing import Protocol

from venda_de_put.models import CandleSeries, Fundamentals, IvPoint, PutQuote

USER_AGENT = "venda-de-put/1.0 (+uso-pessoal)"


class PriceSource(Protocol):
    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]: ...


class IvSource(Protocol):
    def fetch(self) -> dict[str, IvPoint]: ...


class FundamentalsSource(Protocol):
    def fetch(self) -> list[Fundamentals]: ...


class ChainSource(Protocol):
    def fetch_chain(self, ticker: str) -> list[PutQuote]: ...


class SpotSource(Protocol):
    def fetch_spots(self, tickers: list[str]) -> dict[str, float]: ...


class HistoryBootstrap(Protocol):
    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]: ...
