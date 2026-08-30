from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from venda_de_put.models import Snapshot


def _money_to_cents(value: float) -> int:
    reais = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(reais * 100)


@dataclass(frozen=True)
class MarketView:
    asset_prices_cents: dict[str, int]
    option_prices_cents: dict[str, int]
    generated_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "asset_prices_cents",
            {str(ticker).strip().upper(): int(cents)
             for ticker, cents in self.asset_prices_cents.items()},
        )
        object.__setattr__(
            self,
            "option_prices_cents",
            {str(ticker).strip().upper(): int(cents)
             for ticker, cents in self.option_prices_cents.items()},
        )

    @classmethod
    def empty(cls) -> MarketView:
        return cls({}, {}, None)


def build_market_view(snapshot: Snapshot | None) -> MarketView:
    if snapshot is None:
        return MarketView.empty()
    assets = {
        asset.ticker: _money_to_cents(asset.technicals.preco)
        for asset in snapshot.assets
        if asset.technicals is not None
        and asset.technicals.preco is not None
        and asset.technicals.preco > 0
    }
    options = {
        quote.symbol.upper(): _money_to_cents(quote.last)
        for chain in snapshot.chains.values()
        for quote in chain
        if quote.symbol and quote.last is not None and quote.last > 0
    }
    return MarketView(assets, options, snapshot.generated_at)
