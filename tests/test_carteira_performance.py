import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from venda_de_put.carteira.market import MarketView, build_market_view
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
from venda_de_put.carteira.performance import (
    compute_evolution,
    compute_operation,
    compute_personal_summary,
)
from venda_de_put.models import (
    FundScore,
    Lists,
    PutQuote,
    ScoredAsset,
    Snapshot,
    TechnicalInput,
)


CASES = json.loads(
    Path("tests/fixtures/carteira_planilha_cases.json").read_text(encoding="utf-8")
)
NOW = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def _operation(i: int, row: dict) -> OptionOperation:
    return OptionOperation(
        id=i, user_id=1, sale_date=date(2026, 7, 15),
        underlying_ticker=row["underlying"], option_ticker=row["option"],
        option_kind=OptionKind.PUT, quantity=row["quantity"],
        strike_cents=row["strike_cents"], expiry_date=date(2026, 9, 18),
        premium_per_share_cents=row["premium_cents"], status=OptionStatus.OPEN,
        close_cost_per_share_cents=None, repurchase_date=None,
        created_at=NOW, updated_at=NOW,
    )


def _empty_inputs(operations: list[OptionOperation]) -> PersonalInputs:
    return PersonalInputs(
        user_id=1, cash_cents=None, portfolio_entries=[],
        option_operations=operations, custody_entries=[], cash_flows=[],
    )


def test_open_put_totals_match_workbook_cases():
    rows = CASES["open_puts"]
    operations = [_operation(i + 1, row) for i, row in enumerate(rows)]
    market = MarketView(
        asset_prices_cents={r["underlying"]: r["underlying_price_cents"] for r in rows},
        option_prices_cents={r["option"]: r["option_price_cents"] for r in rows},
        generated_at=None,
    )
    summary = compute_personal_summary(
        _empty_inputs(operations),
        market,
        today=date(2026, 7, 30),
        year=2026,
    )
    assert summary.premium_received_cents == CASES["expected"]["premium_total_cents"]
    assert summary.put_capital_at_risk_cents == CASES["expected"]["capital_at_risk_cents"]
    assert sum(x.open_profit_cents for x in summary.open_operations) == CASES["expected"]["open_profit_cents"]
    assert summary.open_option_market_value_cents == CASES["expected"]["open_option_market_value_cents"]


def test_missing_quote_is_none_not_zero():
    op = _operation(1, CASES["open_puts"][0])
    summary = compute_personal_summary(
        _empty_inputs([op]),
        MarketView.empty(), date(2026, 7, 30), 2026,
    )
    assert summary.open_operations[0].underlying_price_cents is None
    assert summary.open_operations[0].option_price_cents is None
    assert summary.open_operations[0].open_profit_cents is None
    assert summary.open_option_market_value_cents is None
    assert summary.put_capital_at_risk_cents == 1_039_000
    assert set(summary.missing_quotes) == {"PSSA3", "PSSAU523"}


def _op(
    *,
    option_kind: OptionKind = OptionKind.PUT,
    status: OptionStatus = OptionStatus.OPEN,
    strike_cents: int = 4000,
    premium_cents: int = 80,
    quantity: int = 100,
    close_cost_per_share_cents: int | None = None,
    repurchase_date: date | None = None,
    expiry_date: date = date(2026, 9, 18),
    sale_date: date = date(2026, 8, 1),
    option_ticker: str = "PETRU400",
) -> OptionOperation:
    return OptionOperation(
        id=1,
        user_id=1,
        sale_date=sale_date,
        underlying_ticker="PETR4",
        option_ticker=option_ticker,
        option_kind=option_kind,
        quantity=quantity,
        strike_cents=strike_cents,
        expiry_date=expiry_date,
        premium_per_share_cents=premium_cents,
        status=status,
        close_cost_per_share_cents=close_cost_per_share_cents,
        repurchase_date=repurchase_date,
        created_at=NOW,
        updated_at=NOW,
    )


def _market(spot: int | None = 4100, option: int | None = 30) -> MarketView:
    assets = {} if spot is None else {"PETR4": spot}
    options = {} if option is None else {"PETRU400": option}
    return MarketView(assets, options, generated_at=None)


def test_put_and_call_moneyness_and_expiry_state():
    today = date(2026, 8, 30)
    otm_put = compute_operation(_op(strike_cents=4000), _market(spot=4100), today)
    assert otm_put.moneyness == "OTM"
    assert otm_put.distance_cents == 100
    assert otm_put.expiry_state == "future"
    assert otm_put.days_to_expiry == 19

    itm_put = compute_operation(_op(strike_cents=4000), _market(spot=3900), today)
    assert itm_put.moneyness == "ITM"

    atm = compute_operation(_op(strike_cents=4000), _market(spot=4000), today)
    assert atm.moneyness == "ATM"

    itm_call = compute_operation(
        _op(option_kind=OptionKind.CALL, option_ticker="PETRV400"),
        MarketView({"PETR4": 4100}, {"PETRV400": 30}, None),
        today,
    )
    assert itm_call.moneyness == "ITM"

    otm_call = compute_operation(
        _op(option_kind=OptionKind.CALL, option_ticker="PETRV400"),
        MarketView({"PETR4": 3900}, {"PETRV400": 30}, None),
        today,
    )
    assert otm_call.moneyness == "OTM"

    overdue = compute_operation(
        _op(expiry_date=date(2026, 8, 29)), _market(), date(2026, 8, 30)
    )
    assert overdue.expiry_state == "overdue"
    assert overdue.days_to_expiry == -1

    due_today = compute_operation(
        _op(expiry_date=date(2026, 8, 30)), _market(), date(2026, 8, 30)
    )
    assert due_today.expiry_state == "today"
    assert due_today.days_to_expiry == 0

    missing = compute_operation(_op(), MarketView.empty(), today)
    assert missing.moneyness is None
    assert missing.distance_cents is None
    assert missing.distance_fraction is None


def test_status_closing_date_narrative_and_open_profit():
    today = date(2026, 8, 30)
    opened = compute_operation(_op(status=OptionStatus.OPEN), _market(), today)
    assert opened.closing_date is None
    assert opened.premium_total_cents == 8000
    assert opened.net_result_cents == 8000
    assert opened.open_profit_cents == 5000
    assert opened.narrative.startswith("Em aberto.")
    assert "R$ 80,00" in opened.narrative
    assert "0,00" not in opened.narrative or "80,00" in opened.narrative

    expired = compute_operation(
        _op(status=OptionStatus.EXPIRED), _market(), today
    )
    assert expired.closing_date == date(2026, 9, 18)
    assert expired.open_profit_cents is None
    assert expired.net_result_cents == 8000
    assert "virou pó" in expired.narrative
    assert "não comprou nada" in expired.narrative

    exercised = compute_operation(
        _op(status=OptionStatus.EXERCISED), _market(), today
    )
    assert exercised.closing_date == date(2026, 9, 18)
    assert exercised.open_profit_cents is None
    assert "COMPROU" in exercised.narrative
    assert "R$ 40,00" in exercised.narrative

    closed = compute_operation(
        _op(
            status=OptionStatus.CLOSED_EARLY,
            close_cost_per_share_cents=20,
            repurchase_date=date(2026, 8, 20),
        ),
        _market(),
        today,
    )
    assert closed.closing_date == date(2026, 8, 20)
    assert closed.net_result_cents == 6000
    assert closed.open_profit_cents is None
    assert "20/08/2026" in closed.narrative
    assert "R$ 60,00" in closed.narrative


def test_build_market_view_converts_snapshot_floats_without_volume_filter():
    generated = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    fund = FundScore(
        ticker="PETR4", n_roe=None, n_roic=None, n_mrgl=None, n_div=None,
        n_liqc=None, n_pl=None, n_pvp=None, n_eveb=None, n_crsc=None,
        qualid=None, saude=None, valuat=None, consist=None,
        score_f=None, pct_f=None,
    )
    snapshot = Snapshot(
        generated_at=generated,
        stamps=[],
        assets=[
            ScoredAsset(
                ticker="PETR4", fund=fund, tendencia=None, timing=None,
                sinal=None, score_t=None, score_c=None, iv_hv=None,
                technicals=TechnicalInput(
                    preco=41.005, mm200=None, ifr=None, boll_inf=None,
                    iv=None, hv=None,
                ),
            )
        ],
        lists=Lists(fundamentalista=[], tecnico=[], combinado=[]),
        fundamentus_rows=[],
        chains={
            "PETR4": [
                PutQuote(
                    due_date=date(2026, 9, 18), strike=40.0, bid=None, ask=None,
                    delta=None, poe=None, volume=0, last=0.805, symbol="petru400",
                )
            ]
        },
    )
    view = build_market_view(snapshot)
    assert view.asset_prices_cents["PETR4"] == 4101
    assert view.option_prices_cents["PETRU400"] == 81
    assert view.generated_at == generated
    assert build_market_view(None) == MarketView.empty()


def test_stock_coverage_and_missing_market_aggregates():
    stock = PortfolioEntry(
        id=1, user_id=1, trade_date=date(2026, 8, 1), ticker="PETR4",
        asset_class=AssetClass.STOCK, side=TradeSide.BUY, quantity=100,
        price_cents=4000, note="", created_at=NOW, updated_at=NOW,
    )
    call = _op(
        option_kind=OptionKind.CALL, option_ticker="PETRV400",
        quantity=200, status=OptionStatus.OPEN,
    )
    inputs = PersonalInputs(
        user_id=1, cash_cents=50_000, portfolio_entries=[stock],
        option_operations=[call], custody_entries=[], cash_flows=[],
    )
    summary = compute_personal_summary(
        inputs, MarketView.empty(), date(2026, 8, 30), 2026,
    )
    asset = next(item for item in summary.assets if item.ticker == "PETR4")
    assert asset.shares == 100
    assert asset.coverage == "uncovered"
    assert asset.market_value_cents is None
    assert asset.unrealized_cents is None
    assert summary.uncovered_call_count == 1
    assert summary.stock_market_value_cents is None
    assert summary.margin_market_value_cents == 0
    assert summary.headroom_cents == 50_000
    assert summary.net_worth_cents is None
    assert "PETR4" in summary.missing_quotes
    assert "PETRV400" in summary.missing_quotes


def test_evolution_matches_spreadsheet_time_weighted_formula():
    flows = [
        CashFlow(1, 1, date(2026, 1, 1), CashFlowKind.CONTRIBUTION, 100_000, "", NOW, NOW),
        CashFlow(2, 1, date(2026, 1, 2), CashFlowKind.CONTRIBUTION, 10_000, "", NOW, NOW),
        CashFlow(3, 1, date(2026, 1, 3), CashFlowKind.WITHDRAWAL, 5_000, "", NOW, NOW),
    ]
    custody = [
        CustodyEntry(1, 1, date(2026, 1, 1), 100_000, NOW, NOW),
        CustodyEntry(2, 1, date(2026, 1, 2), 121_000, NOW, NOW),
        CustodyEntry(3, 1, date(2026, 1, 3), 121_800, NOW, NOW),
    ]
    points = compute_evolution(custody, flows)
    assert [p.net_contributions_cents for p in points] == [100_000, 110_000, 105_000]
    assert [p.period_flow_cents for p in points] == [100_000, 10_000, -5_000]
    assert [p.total_result_cents for p in points] == [0, 11_000, 16_800]
    assert [p.period_profit_cents for p in points] == [0, 11_000, 5_800]
    assert points[0].period_return == pytest.approx(0.0)
    assert points[1].period_return == pytest.approx(0.10)
    assert points[2].period_return == pytest.approx(0.05)
    assert points[2].cumulative_return == pytest.approx(0.155)


def test_evolution_zero_denominator_is_none_not_zero():
    points = compute_evolution(
        [CustodyEntry(1, 1, date(2026, 1, 1), 0, NOW, NOW)],
        [],
    )
    assert points[0].net_contributions_cents == 0
    assert points[0].period_flow_cents == 0
    assert points[0].period_return is None
    assert points[0].cumulative_return is None
