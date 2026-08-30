from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from venda_de_put.carteira.market import MarketView
from venda_de_put.carteira.models import (
    AssetClass,
    CashFlow,
    CashFlowKind,
    CustodyEntry,
    OptionKind,
    OptionOperation,
    OptionStatus,
    PersonalInputs,
    PortfolioEntry,
    TradeSide,
)


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _format_brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    whole_txt = f"{whole:,}".replace(",", ".")
    return f"{sign}R$ {whole_txt},{frac:02d}"


def _format_qty(quantity: int) -> str:
    return f"{quantity:,}".replace(",", ".")


def _format_date(value: date | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d/%m/%Y")


@dataclass(frozen=True)
class OperationPerformance:
    operation: OptionOperation
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


@dataclass(frozen=True)
class AssetPerformance:
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


@dataclass(frozen=True)
class AllocationPoint:
    label: str
    value_cents: int


@dataclass(frozen=True)
class EvolutionPoint:
    as_of_date: date
    custody_cents: int
    net_contributions_cents: int
    period_flow_cents: int
    total_result_cents: int
    period_profit_cents: int
    period_return: float | None
    cumulative_return: float | None


@dataclass(frozen=True)
class PersonalSummary:
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
    open_operations: list[OperationPerformance]
    assets: list[AssetPerformance]
    monthly_premiums_cents: list[int]
    stock_allocation: list[AllocationPoint]
    put_risk_allocation: list[AllocationPoint]
    evolution: list[EvolutionPoint]
    market_generated_at: datetime | None
    missing_quotes: list[str]


def _operation_narrative(op: OptionOperation, premium_total: int, net_result: int) -> str:
    if op.status is OptionStatus.OPEN:
        return (
            f"Em aberto. Você já recebeu {_format_brl(premium_total)} de prêmio. "
            "Aguarde o vencimento."
        )
    if op.status is OptionStatus.EXPIRED:
        if op.option_kind is OptionKind.CALL:
            return "A call virou pó: ficou com o prêmio e continua com as ações."
        return "A put virou pó: ficou com o prêmio e não comprou nada."
    if op.status is OptionStatus.EXERCISED:
        strike = _format_brl(op.strike_cents)
        qty = _format_qty(op.quantity)
        if op.option_kind is OptionKind.CALL:
            return (
                f"Exercida: você VENDEU {qty} ações a {strike}. "
                "Lance a Venda na Carteira."
            )
        real = _format_brl(op.strike_cents - op.premium_per_share_cents)
        return (
            f"Exercida: você COMPROU {qty} ações a {strike}. "
            f"Lance a Compra na Carteira. Preço real c/ prêmio: {real}."
        )
    return (
        "Encerrada antes do vencimento (recompra em "
        f"{_format_date(op.repurchase_date)}). "
        f"Resultado líquido: {_format_brl(net_result)}."
    )


def compute_operation(
    operation: OptionOperation,
    market: MarketView,
    today: date,
) -> OperationPerformance:
    op = operation
    premium_total = op.quantity * op.premium_per_share_cents
    close_total = (
        0
        if op.close_cost_per_share_cents is None
        else op.quantity * op.close_cost_per_share_cents
    )
    net_result = premium_total - close_total
    if op.status is OptionStatus.CLOSED_EARLY:
        closing_date = op.repurchase_date
    elif op.status in {OptionStatus.EXPIRED, OptionStatus.EXERCISED}:
        closing_date = op.expiry_date
    else:
        closing_date = None

    underlying = market.asset_prices_cents.get(op.underlying_ticker)
    option_price = market.option_prices_cents.get(op.option_ticker)
    distance_cents = None if underlying is None else underlying - op.strike_cents
    distance_fraction = (
        None
        if distance_cents is None
        else float(Decimal(distance_cents) / Decimal(op.strike_cents))
    )
    if underlying is None:
        moneyness = None
    elif underlying == op.strike_cents:
        moneyness = "ATM"
    elif op.option_kind is OptionKind.PUT:
        moneyness = "ITM" if underlying < op.strike_cents else "OTM"
    else:
        moneyness = "ITM" if underlying > op.strike_cents else "OTM"

    open_profit_cents = (
        None
        if option_price is None or op.status is not OptionStatus.OPEN
        else (op.premium_per_share_cents - option_price) * op.quantity
    )
    open_profit_fraction = (
        None
        if open_profit_cents is None or op.premium_per_share_cents == 0
        else float(
            Decimal(op.premium_per_share_cents - option_price)
            / Decimal(op.premium_per_share_cents)
        )
    )

    days_to_expiry = (op.expiry_date - today).days
    if days_to_expiry < 0:
        expiry_state = "overdue"
    elif days_to_expiry == 0:
        expiry_state = "today"
    else:
        expiry_state = "future"

    return OperationPerformance(
        operation=op,
        premium_total_cents=premium_total,
        closing_date=closing_date,
        net_result_cents=net_result,
        underlying_price_cents=underlying,
        option_price_cents=option_price,
        distance_cents=distance_cents,
        distance_fraction=distance_fraction,
        moneyness=moneyness,
        open_profit_cents=open_profit_cents,
        open_profit_fraction=open_profit_fraction,
        days_to_expiry=days_to_expiry,
        expiry_state=expiry_state,
        narrative=_operation_narrative(op, premium_total, net_result),
    )


@dataclass
class _PositionBook:
    bought_quantity: int = 0
    bought_total_cents: int = 0
    sold_quantity: int = 0
    sold_total_cents: int = 0

    @property
    def shares(self) -> int:
        return self.bought_quantity - self.sold_quantity


def _books_by_class(
    entries: list[PortfolioEntry],
) -> tuple[dict[str, _PositionBook], dict[str, _PositionBook]]:
    stocks: dict[str, _PositionBook] = defaultdict(_PositionBook)
    margin: dict[str, _PositionBook] = defaultdict(_PositionBook)
    for entry in entries:
        target = margin if entry.asset_class is AssetClass.MARGIN else stocks
        book = target[entry.ticker]
        total = entry.quantity * entry.price_cents
        if entry.side is TradeSide.BUY:
            book.bought_quantity += entry.quantity
            book.bought_total_cents += total
        else:
            book.sold_quantity += entry.quantity
            book.sold_total_cents += total
    return stocks, margin


def _position_metrics(book: _PositionBook, spot: int | None) -> tuple[
    Decimal | None, int | None, int | None, int | None, int
]:
    shares = book.shares
    average_buy_price = (
        None
        if book.bought_quantity == 0
        else Decimal(book.bought_total_cents) / Decimal(book.bought_quantity)
    )
    average_buy_price_cents = (
        None if average_buy_price is None else _round_cents(average_buy_price)
    )
    market_value_cents = None if shares <= 0 or spot is None else shares * spot
    unrealized_cents = (
        None
        if shares <= 0 or spot is None or average_buy_price is None
        else _round_cents((Decimal(spot) - average_buy_price) * shares)
    )
    realized_stock_cents = book.sold_total_cents - (
        0
        if average_buy_price is None
        else _round_cents(average_buy_price * book.sold_quantity)
    )
    return (
        average_buy_price,
        average_buy_price_cents,
        market_value_cents,
        unrealized_cents,
        realized_stock_cents,
    )


def _sum_or_none(values: list[int | None], required: bool) -> int | None:
    if required:
        return None
    return sum(0 if item is None else item for item in values)


def _coverage(shares: int, open_call_quantity: int) -> str:
    if open_call_quantity == 0:
        return "no_calls"
    if shares >= open_call_quantity:
        return "covered"
    return "uncovered"


def compute_evolution(
    custody_entries: list[CustodyEntry],
    cash_flows: list[CashFlow],
) -> list[EvolutionPoint]:
    ordered_custody = sorted(
        custody_entries, key=lambda item: (item.as_of_date, item.id)
    )
    ordered_flows = sorted(
        cash_flows, key=lambda item: (item.flow_date, item.id)
    )
    points: list[EvolutionPoint] = []
    previous_custody = 0
    previous_net = 0
    previous_return: float | None = 0.0
    for entry in ordered_custody:
        net = 0
        for flow in ordered_flows:
            if flow.flow_date > entry.as_of_date:
                continue
            if flow.kind is CashFlowKind.CONTRIBUTION:
                net += flow.amount_cents
            else:
                net -= flow.amount_cents
        period_flow = net - previous_net
        total_result = entry.total_cents - net
        period_profit = (entry.total_cents - previous_custody) - period_flow
        denominator = previous_custody + period_flow
        if denominator == 0:
            period_return: float | None = None
            cumulative_return = None
        else:
            period_return = float(
                Decimal(entry.total_cents) / Decimal(denominator) - 1
            )
            if previous_return is None:
                cumulative_return = None
            else:
                cumulative_return = (1 + previous_return) * (1 + period_return) - 1
        points.append(
            EvolutionPoint(
                as_of_date=entry.as_of_date,
                custody_cents=entry.total_cents,
                net_contributions_cents=net,
                period_flow_cents=period_flow,
                total_result_cents=total_result,
                period_profit_cents=period_profit,
                period_return=period_return,
                cumulative_return=cumulative_return,
            )
        )
        previous_custody = entry.total_cents
        previous_net = net
        previous_return = cumulative_return
    return points


def compute_personal_summary(
    inputs: PersonalInputs,
    market: MarketView,
    today: date,
    year: int,
) -> PersonalSummary:
    operations = [
        compute_operation(op, market, today) for op in inputs.option_operations
    ]
    open_operations = [
        item for item in operations if item.operation.status is OptionStatus.OPEN
    ]
    missing: set[str] = set()

    for item in operations:
        op = item.operation
        if item.underlying_price_cents is None:
            missing.add(op.underlying_ticker)
        if op.status is OptionStatus.OPEN and item.option_price_cents is None:
            missing.add(op.option_ticker)

    premium_received_cents = sum(item.premium_total_cents for item in operations)
    option_net_result_cents = sum(item.net_result_cents for item in operations)

    monthly = [0] * 12
    for op in inputs.option_operations:
        if op.sale_date.year == year:
            monthly[op.sale_date.month - 1] += op.quantity * op.premium_per_share_cents

    stock_books, margin_books = _books_by_class(inputs.portfolio_entries)

    ops_by_ticker: dict[str, list[OptionOperation]] = defaultdict(list)
    for op in inputs.option_operations:
        ops_by_ticker[op.underlying_ticker].append(op)

    tickers = sorted(set(stock_books) | set(ops_by_ticker))
    assets: list[AssetPerformance] = []
    stock_unrealized: list[int | None] = []
    stock_unrealized_missing = False
    stock_values: list[int | None] = []
    stock_value_missing = False

    for ticker in tickers:
        book = stock_books.get(ticker, _PositionBook())
        spot = market.asset_prices_cents.get(ticker)
        if book.shares > 0 and spot is None:
            missing.add(ticker)
            stock_value_missing = True
            stock_unrealized_missing = True
        (
            _avg,
            average_buy_price_cents,
            market_value_cents,
            unrealized_cents,
            realized_stock_cents,
        ) = _position_metrics(book, spot)

        ticker_ops = ops_by_ticker.get(ticker, [])
        open_calls = [
            op for op in ticker_ops
            if op.option_kind is OptionKind.CALL and op.status is OptionStatus.OPEN
        ]
        open_puts = [
            op for op in ticker_ops
            if op.option_kind is OptionKind.PUT and op.status is OptionStatus.OPEN
        ]
        open_call_quantity = sum(op.quantity for op in open_calls)
        open_put_quantity = sum(op.quantity for op in open_puts)
        put_risk_cents = sum(op.quantity * op.strike_cents for op in open_puts)
        premium_on_ticker = sum(
            op.quantity * op.premium_per_share_cents for op in ticker_ops
        )
        coverage = _coverage(book.shares, open_call_quantity)
        assets.append(
            AssetPerformance(
                ticker=ticker,
                spot_cents=spot,
                shares=book.shares,
                average_buy_price_cents=average_buy_price_cents,
                market_value_cents=market_value_cents,
                unrealized_cents=unrealized_cents,
                open_call_quantity=open_call_quantity,
                coverage=coverage,
                open_put_quantity=open_put_quantity,
                put_risk_cents=put_risk_cents,
                premium_received_cents=premium_on_ticker,
                realized_stock_cents=realized_stock_cents,
                total_profit_cents=premium_on_ticker + realized_stock_cents,
            )
        )
        if book.shares > 0:
            stock_values.append(market_value_cents)
            stock_unrealized.append(unrealized_cents)

    realized_stock_cents = sum(asset.realized_stock_cents for asset in assets)
    put_capital_at_risk_cents = sum(
        op.quantity * op.strike_cents
        for op in inputs.option_operations
        if op.option_kind is OptionKind.PUT and op.status is OptionStatus.OPEN
    )

    margin_values: list[int | None] = []
    margin_missing = False
    for ticker, book in margin_books.items():
        if book.shares <= 0:
            continue
        spot = market.asset_prices_cents.get(ticker)
        if spot is None:
            missing.add(ticker)
            margin_missing = True
            margin_values.append(None)
        else:
            margin_values.append(book.shares * spot)

    option_values: list[int | None] = []
    option_missing = False
    for item in open_operations:
        if item.option_price_cents is None:
            option_missing = True
            option_values.append(None)
        else:
            option_values.append(
                item.option_price_cents * item.operation.quantity
            )

    stock_market_value_cents = _sum_or_none(stock_values, stock_value_missing)
    margin_market_value_cents = _sum_or_none(margin_values, margin_missing)
    if not margin_books or all(
        book.shares <= 0 for book in margin_books.values()
    ):
        margin_market_value_cents = 0 if not margin_missing else None
    unrealized_result_cents = _sum_or_none(
        stock_unrealized, stock_unrealized_missing
    )
    if not any(book.shares > 0 for book in stock_books.values()):
        unrealized_result_cents = 0 if not stock_unrealized_missing else None
        if not stock_value_missing:
            stock_market_value_cents = 0

    open_option_market_value_cents = _sum_or_none(option_values, option_missing)
    if not open_operations:
        open_option_market_value_cents = 0

    cash_cents = inputs.cash_cents
    headroom_cents = (
        None
        if cash_cents is None or margin_market_value_cents is None
        else cash_cents + margin_market_value_cents - put_capital_at_risk_cents
    )
    net_worth_cents = (
        None
        if (
            cash_cents is None
            or stock_market_value_cents is None
            or margin_market_value_cents is None
            or open_option_market_value_cents is None
        )
        else (
            cash_cents
            + stock_market_value_cents
            + margin_market_value_cents
            - open_option_market_value_cents
        )
    )

    stock_allocation = sorted(
        [
            AllocationPoint(asset.ticker, asset.market_value_cents)
            for asset in assets
            if asset.market_value_cents is not None and asset.market_value_cents > 0
        ],
        key=lambda point: (-point.value_cents, point.label),
    )
    put_risk_allocation = sorted(
        [
            AllocationPoint(asset.ticker, asset.put_risk_cents)
            for asset in assets
            if asset.put_risk_cents > 0
        ],
        key=lambda point: (-point.value_cents, point.label),
    )

    return PersonalSummary(
        premium_received_cents=premium_received_cents,
        option_net_result_cents=option_net_result_cents,
        realized_stock_cents=realized_stock_cents,
        realized_total_cents=option_net_result_cents + realized_stock_cents,
        unrealized_result_cents=unrealized_result_cents,
        stock_market_value_cents=stock_market_value_cents,
        put_capital_at_risk_cents=put_capital_at_risk_cents,
        operation_count=len(operations),
        open_operation_count=len(open_operations),
        uncovered_call_count=sum(
            1 for asset in assets if asset.coverage == "uncovered"
        ),
        cash_cents=cash_cents,
        margin_market_value_cents=margin_market_value_cents,
        headroom_cents=headroom_cents,
        open_option_market_value_cents=open_option_market_value_cents,
        net_worth_cents=net_worth_cents,
        open_operations=open_operations,
        assets=assets,
        monthly_premiums_cents=monthly,
        stock_allocation=stock_allocation,
        put_risk_allocation=put_risk_allocation,
        evolution=compute_evolution(inputs.custody_entries, inputs.cash_flows),
        market_generated_at=market.generated_at,
        missing_quotes=sorted(missing),
    )
