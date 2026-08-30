from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from venda_de_put.carteira.models import (
    AssetClass,
    CashFlow,
    CashFlowInput,
    CashFlowKind,
    CustodyEntry,
    CustodyEntryInput,
    OptionKind,
    OptionOperationInput,
    OptionStatus,
    PortfolioEntry,
    PortfolioEntryInput,
    TradeSide,
)
from venda_de_put.carteira.performance import (
    AllocationPoint,
    AssetPerformance,
    EvolutionPoint,
    OperationPerformance,
    PersonalSummary,
)


class RegisterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


class AccountBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cash_cents: int | None


class PortfolioEntryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trade_date: date
    ticker: str = Field(min_length=1, max_length=16)
    asset_class: Literal["stock", "margin"]
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    price_cents: int = Field(ge=0)
    note: str = Field(default="", max_length=500)

    def to_domain(self) -> PortfolioEntryInput:
        return PortfolioEntryInput(
            trade_date=self.trade_date,
            ticker=self.ticker,
            asset_class=AssetClass(self.asset_class),
            side=TradeSide(self.side),
            quantity=self.quantity,
            price_cents=self.price_cents,
            note=self.note,
        )


class OptionOperationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sale_date: date
    underlying_ticker: str = Field(min_length=1, max_length=16)
    option_ticker: str = Field(min_length=1, max_length=32)
    option_kind: Literal["call", "put"]
    quantity: int = Field(gt=0)
    strike_cents: int = Field(gt=0)
    expiry_date: date
    premium_per_share_cents: int = Field(ge=0)
    status: Literal["open", "expired", "exercised", "closed_early"]
    close_cost_per_share_cents: int | None = Field(default=None, ge=0)
    repurchase_date: date | None = None

    @model_validator(mode="after")
    def validate_dates_and_close(self) -> Self:
        if self.sale_date > self.expiry_date:
            raise ValueError("data da venda não pode ser posterior ao vencimento")
        is_early = self.status == "closed_early"
        if is_early and (
            self.close_cost_per_share_cents is None or self.repurchase_date is None
        ):
            raise ValueError("encerramento antecipado exige custo e data da recompra")
        if not is_early and (
            self.close_cost_per_share_cents is not None
            or self.repurchase_date is not None
        ):
            raise ValueError(
                "encerramento antecipado exige custo e data da recompra; "
                "outros status proíbem esses campos"
            )
        if self.repurchase_date is not None and not (
            self.sale_date <= self.repurchase_date <= self.expiry_date
        ):
            raise ValueError("data da recompra deve ficar entre venda e vencimento")
        return self

    def to_domain(self) -> OptionOperationInput:
        return OptionOperationInput(
            sale_date=self.sale_date,
            underlying_ticker=self.underlying_ticker,
            option_ticker=self.option_ticker,
            option_kind=OptionKind(self.option_kind),
            quantity=self.quantity,
            strike_cents=self.strike_cents,
            expiry_date=self.expiry_date,
            premium_per_share_cents=self.premium_per_share_cents,
            status=OptionStatus(self.status),
            close_cost_per_share_cents=self.close_cost_per_share_cents,
            repurchase_date=self.repurchase_date,
        )


class CustodyEntryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of_date: date
    total_cents: int

    def to_domain(self) -> CustodyEntryInput:
        return CustodyEntryInput(
            as_of_date=self.as_of_date,
            total_cents=self.total_cents,
        )


class CashFlowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_date: date
    kind: Literal["contribution", "withdrawal"]
    amount_cents: int = Field(gt=0)
    note: str = Field(default="", max_length=500)

    def to_domain(self) -> CashFlowInput:
        return CashFlowInput(
            flow_date=self.flow_date,
            kind=CashFlowKind(self.kind),
            amount_cents=self.amount_cents,
            note=self.note,
        )


class AccountOut(BaseModel):
    cash_cents: int | None


class MeOut(BaseModel):
    authenticated: bool
    username: str | None = None


class AuthSessionOut(BaseModel):
    username: str
    csrf_token: str


class PortfolioEntryOut(BaseModel):
    id: int
    trade_date: date
    ticker: str
    asset_class: str
    side: str
    quantity: int
    price_cents: int
    note: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, entry: PortfolioEntry) -> PortfolioEntryOut:
        return cls(
            id=entry.id,
            trade_date=entry.trade_date,
            ticker=entry.ticker,
            asset_class=entry.asset_class.value,
            side=entry.side.value,
            quantity=entry.quantity,
            price_cents=entry.price_cents,
            note=entry.note,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


class OperationPerformanceOut(BaseModel):
    id: int
    sale_date: date
    underlying_ticker: str
    option_ticker: str
    option_kind: str
    quantity: int
    strike_cents: int
    expiry_date: date
    premium_per_share_cents: int
    status: str
    close_cost_per_share_cents: int | None
    repurchase_date: date | None
    created_at: datetime
    updated_at: datetime
    premium_total_cents: int
    closing_date: date | None
    net_result_cents: int
    underlying_price_cents: int | None
    option_price_cents: int | None
    distance_cents: int | None
    distance_fraction: float | None
    moneyness: str | None
    open_profit_cents: int | None
    open_profit_fraction: float | None
    days_to_expiry: int
    expiry_state: str
    narrative: str

    @classmethod
    def from_domain(cls, item: OperationPerformance) -> OperationPerformanceOut:
        op = item.operation
        return cls(
            id=op.id,
            sale_date=op.sale_date,
            underlying_ticker=op.underlying_ticker,
            option_ticker=op.option_ticker,
            option_kind=op.option_kind.value,
            quantity=op.quantity,
            strike_cents=op.strike_cents,
            expiry_date=op.expiry_date,
            premium_per_share_cents=op.premium_per_share_cents,
            status=op.status.value,
            close_cost_per_share_cents=op.close_cost_per_share_cents,
            repurchase_date=op.repurchase_date,
            created_at=op.created_at,
            updated_at=op.updated_at,
            premium_total_cents=item.premium_total_cents,
            closing_date=item.closing_date,
            net_result_cents=item.net_result_cents,
            underlying_price_cents=item.underlying_price_cents,
            option_price_cents=item.option_price_cents,
            distance_cents=item.distance_cents,
            distance_fraction=item.distance_fraction,
            moneyness=item.moneyness,
            open_profit_cents=item.open_profit_cents,
            open_profit_fraction=item.open_profit_fraction,
            days_to_expiry=item.days_to_expiry,
            expiry_state=item.expiry_state,
            narrative=item.narrative,
        )


class CustodyEntryOut(BaseModel):
    id: int
    as_of_date: date
    total_cents: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, entry: CustodyEntry) -> CustodyEntryOut:
        return cls(
            id=entry.id,
            as_of_date=entry.as_of_date,
            total_cents=entry.total_cents,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


class CashFlowOut(BaseModel):
    id: int
    flow_date: date
    kind: str
    amount_cents: int
    note: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, flow: CashFlow) -> CashFlowOut:
        return cls(
            id=flow.id,
            flow_date=flow.flow_date,
            kind=flow.kind.value,
            amount_cents=flow.amount_cents,
            note=flow.note,
            created_at=flow.created_at,
            updated_at=flow.updated_at,
        )


class AssetPerformanceOut(BaseModel):
    ticker: str
    spot_cents: int | None
    shares: int
    average_buy_price_cents: int | None
    market_value_cents: int | None
    unrealized_cents: int | None
    open_call_quantity: int
    coverage: str
    open_put_quantity: int
    put_risk_cents: int
    premium_received_cents: int
    realized_stock_cents: int
    total_profit_cents: int

    @classmethod
    def from_domain(cls, item: AssetPerformance) -> AssetPerformanceOut:
        return cls(
            ticker=item.ticker,
            spot_cents=item.spot_cents,
            shares=item.shares,
            average_buy_price_cents=item.average_buy_price_cents,
            market_value_cents=item.market_value_cents,
            unrealized_cents=item.unrealized_cents,
            open_call_quantity=item.open_call_quantity,
            coverage=item.coverage,
            open_put_quantity=item.open_put_quantity,
            put_risk_cents=item.put_risk_cents,
            premium_received_cents=item.premium_received_cents,
            realized_stock_cents=item.realized_stock_cents,
            total_profit_cents=item.total_profit_cents,
        )


class AllocationPointOut(BaseModel):
    label: str
    value_cents: int

    @classmethod
    def from_domain(cls, item: AllocationPoint) -> AllocationPointOut:
        return cls(label=item.label, value_cents=item.value_cents)


class EvolutionPointOut(BaseModel):
    as_of_date: date
    custody_cents: int
    net_contributions_cents: int
    period_flow_cents: int
    total_result_cents: int
    period_profit_cents: int
    period_return: float | None
    cumulative_return: float | None

    @classmethod
    def from_domain(cls, item: EvolutionPoint) -> EvolutionPointOut:
        return cls(
            as_of_date=item.as_of_date,
            custody_cents=item.custody_cents,
            net_contributions_cents=item.net_contributions_cents,
            period_flow_cents=item.period_flow_cents,
            total_result_cents=item.total_result_cents,
            period_profit_cents=item.period_profit_cents,
            period_return=item.period_return,
            cumulative_return=item.cumulative_return,
        )


class PersonalSummaryOut(BaseModel):
    premium_received_cents: int
    option_net_result_cents: int
    realized_stock_cents: int
    realized_total_cents: int
    unrealized_result_cents: int | None
    stock_market_value_cents: int | None
    put_capital_at_risk_cents: int
    operation_count: int
    open_operation_count: int
    uncovered_call_count: int
    cash_cents: int | None
    margin_market_value_cents: int | None
    headroom_cents: int | None
    open_option_market_value_cents: int | None
    net_worth_cents: int | None
    open_operations: list[OperationPerformanceOut]
    assets: list[AssetPerformanceOut]
    monthly_premiums_cents: list[int]
    stock_allocation: list[AllocationPointOut]
    put_risk_allocation: list[AllocationPointOut]
    evolution: list[EvolutionPointOut]
    market_generated_at: datetime | None
    missing_quotes: list[str]

    @classmethod
    def from_domain(cls, summary: PersonalSummary) -> PersonalSummaryOut:
        return cls(
            premium_received_cents=summary.premium_received_cents,
            option_net_result_cents=summary.option_net_result_cents,
            realized_stock_cents=summary.realized_stock_cents,
            realized_total_cents=summary.realized_total_cents,
            unrealized_result_cents=summary.unrealized_result_cents,
            stock_market_value_cents=summary.stock_market_value_cents,
            put_capital_at_risk_cents=summary.put_capital_at_risk_cents,
            operation_count=summary.operation_count,
            open_operation_count=summary.open_operation_count,
            uncovered_call_count=summary.uncovered_call_count,
            cash_cents=summary.cash_cents,
            margin_market_value_cents=summary.margin_market_value_cents,
            headroom_cents=summary.headroom_cents,
            open_option_market_value_cents=summary.open_option_market_value_cents,
            net_worth_cents=summary.net_worth_cents,
            open_operations=[
                OperationPerformanceOut.from_domain(item)
                for item in summary.open_operations
            ],
            assets=[AssetPerformanceOut.from_domain(item) for item in summary.assets],
            monthly_premiums_cents=list(summary.monthly_premiums_cents),
            stock_allocation=[
                AllocationPointOut.from_domain(item)
                for item in summary.stock_allocation
            ],
            put_risk_allocation=[
                AllocationPointOut.from_domain(item)
                for item in summary.put_risk_allocation
            ],
            evolution=[
                EvolutionPointOut.from_domain(item) for item in summary.evolution
            ],
            market_generated_at=summary.market_generated_at,
            missing_quotes=list(summary.missing_quotes),
        )
