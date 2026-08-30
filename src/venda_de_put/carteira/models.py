from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class AssetClass(StrEnum):
    STOCK = "stock"
    MARGIN = "margin"


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OptionKind(StrEnum):
    CALL = "call"
    PUT = "put"


class OptionStatus(StrEnum):
    OPEN = "open"
    EXPIRED = "expired"
    EXERCISED = "exercised"
    CLOSED_EARLY = "closed_early"


class CashFlowKind(StrEnum):
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"


def _normalized_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not ticker:
        raise ValueError("ticker não pode ficar vazio")
    return ticker


def _validate_note(note: str) -> None:
    if len(note) > 500:
        raise ValueError("observação deve ter no máximo 500 caracteres")


@dataclass(frozen=True)
class PortfolioEntryInput:
    trade_date: date
    ticker: str
    asset_class: AssetClass
    side: TradeSide
    quantity: int
    price_cents: int
    note: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", _normalized_ticker(self.ticker))
        if self.quantity <= 0:
            raise ValueError("quantidade deve ser positiva")
        if self.price_cents < 0:
            raise ValueError("preço não pode ser negativo")
        _validate_note(self.note)


@dataclass(frozen=True)
class OptionOperationInput:
    sale_date: date
    underlying_ticker: str
    option_ticker: str
    option_kind: OptionKind
    quantity: int
    strike_cents: int
    expiry_date: date
    premium_per_share_cents: int
    status: OptionStatus
    close_cost_per_share_cents: int | None
    repurchase_date: date | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "underlying_ticker", _normalized_ticker(self.underlying_ticker)
        )
        object.__setattr__(
            self, "option_ticker", _normalized_ticker(self.option_ticker)
        )
        if self.quantity <= 0:
            raise ValueError("quantidade deve ser positiva")
        if self.strike_cents <= 0:
            raise ValueError("strike deve ser positivo")
        if self.premium_per_share_cents < 0:
            raise ValueError("prêmio não pode ser negativo")
        if self.close_cost_per_share_cents is not None and (
            self.close_cost_per_share_cents < 0
        ):
            raise ValueError("custo de recompra não pode ser negativo")
        if self.sale_date > self.expiry_date:
            raise ValueError("data da venda não pode ser posterior ao vencimento")

        is_closed_early = self.status is OptionStatus.CLOSED_EARLY
        has_close_cost = self.close_cost_per_share_cents is not None
        has_repurchase_date = self.repurchase_date is not None
        if is_closed_early and not (has_close_cost and has_repurchase_date):
            raise ValueError(
                "encerramento antecipado exige custo e data da recompra"
            )
        if not is_closed_early and (has_close_cost or has_repurchase_date):
            raise ValueError(
                "outros status proíbem custo e data da recompra"
            )
        if self.repurchase_date is not None and not (
            self.sale_date <= self.repurchase_date <= self.expiry_date
        ):
            raise ValueError(
                "data da recompra deve ficar entre venda e vencimento"
            )


@dataclass(frozen=True)
class CustodyEntryInput:
    as_of_date: date
    total_cents: int


@dataclass(frozen=True)
class CashFlowInput:
    flow_date: date
    kind: CashFlowKind
    amount_cents: int
    note: str

    def __post_init__(self) -> None:
        if self.amount_cents <= 0:
            raise ValueError("valor do fluxo deve ser positivo")
        _validate_note(self.note)


@dataclass(frozen=True)
class PortfolioEntry:
    id: int
    user_id: int
    trade_date: date
    ticker: str
    asset_class: AssetClass
    side: TradeSide
    quantity: int
    price_cents: int
    note: str
    created_at: datetime
    updated_at: datetime

    def to_input(self) -> PortfolioEntryInput:
        return PortfolioEntryInput(
            trade_date=self.trade_date,
            ticker=self.ticker,
            asset_class=self.asset_class,
            side=self.side,
            quantity=self.quantity,
            price_cents=self.price_cents,
            note=self.note,
        )


@dataclass(frozen=True)
class OptionOperation:
    id: int
    user_id: int
    sale_date: date
    underlying_ticker: str
    option_ticker: str
    option_kind: OptionKind
    quantity: int
    strike_cents: int
    expiry_date: date
    premium_per_share_cents: int
    status: OptionStatus
    close_cost_per_share_cents: int | None
    repurchase_date: date | None
    created_at: datetime
    updated_at: datetime

    def to_input(self) -> OptionOperationInput:
        return OptionOperationInput(
            sale_date=self.sale_date,
            underlying_ticker=self.underlying_ticker,
            option_ticker=self.option_ticker,
            option_kind=self.option_kind,
            quantity=self.quantity,
            strike_cents=self.strike_cents,
            expiry_date=self.expiry_date,
            premium_per_share_cents=self.premium_per_share_cents,
            status=self.status,
            close_cost_per_share_cents=self.close_cost_per_share_cents,
            repurchase_date=self.repurchase_date,
        )


@dataclass(frozen=True)
class CustodyEntry:
    id: int
    user_id: int
    as_of_date: date
    total_cents: int
    created_at: datetime
    updated_at: datetime

    def to_input(self) -> CustodyEntryInput:
        return CustodyEntryInput(
            as_of_date=self.as_of_date,
            total_cents=self.total_cents,
        )


@dataclass(frozen=True)
class CashFlow:
    id: int
    user_id: int
    flow_date: date
    kind: CashFlowKind
    amount_cents: int
    note: str
    created_at: datetime
    updated_at: datetime

    def to_input(self) -> CashFlowInput:
        return CashFlowInput(
            flow_date=self.flow_date,
            kind=self.kind,
            amount_cents=self.amount_cents,
            note=self.note,
        )


@dataclass(frozen=True)
class PersonalInputs:
    user_id: int
    cash_cents: int | None
    portfolio_entries: list[PortfolioEntry]
    option_operations: list[OptionOperation]
    custody_entries: list[CustodyEntry]
    cash_flows: list[CashFlow]
