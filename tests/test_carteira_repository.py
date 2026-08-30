from datetime import date
from pathlib import Path

import pytest

from venda_de_put.carteira.auth import AuthService
from venda_de_put.carteira.db import Database
from venda_de_put.carteira.models import (
    AssetClass,
    CashFlowInput,
    CashFlowKind,
    CustodyEntryInput,
    OptionKind,
    OptionOperationInput,
    OptionStatus,
    PortfolioEntryInput,
    TradeSide,
)
from venda_de_put.carteira.repository import CarteiraRepository, RepositoryConflict


def _repo_and_users(tmp_path: Path) -> tuple[CarteiraRepository, int, int]:
    db = Database(tmp_path / "carteira.sqlite3")
    db.migrate()
    auth = AuthService(db)
    user_a = auth.register("user_a", "senha-segura-a1").user
    user_b = auth.register("user_b", "senha-segura-b2").user
    return CarteiraRepository(db), user_a.user_id, user_b.user_id


def _portfolio_input(
    *,
    trade_date: date = date(2026, 8, 30),
    ticker: str = "petr4",
    note: str = "inicial",
) -> PortfolioEntryInput:
    return PortfolioEntryInput(
        trade_date=trade_date,
        ticker=ticker,
        asset_class=AssetClass.STOCK,
        side=TradeSide.BUY,
        quantity=100,
        price_cents=4_100,
        note=note,
    )


def _operation_input(
    *,
    sale_date: date = date(2026, 8, 1),
    option_ticker: str = "petru400",
    status: OptionStatus = OptionStatus.OPEN,
    close_cost_per_share_cents: int | None = None,
    repurchase_date: date | None = None,
) -> OptionOperationInput:
    return OptionOperationInput(
        sale_date=sale_date,
        underlying_ticker=" petr4 ",
        option_ticker=option_ticker,
        option_kind=OptionKind.PUT,
        quantity=100,
        strike_cents=4_000,
        expiry_date=date(2026, 9, 18),
        premium_per_share_cents=80,
        status=status,
        close_cost_per_share_cents=close_cost_per_share_cents,
        repurchase_date=repurchase_date,
    )


def _cash_flow_input(
    *,
    flow_date: date = date(2026, 8, 1),
    note: str = "inicial",
) -> CashFlowInput:
    return CashFlowInput(
        flow_date=flow_date,
        kind=CashFlowKind.CONTRIBUTION,
        amount_cents=500_000,
        note=note,
    )


def test_portfolio_crud_always_scopes_records_by_owner(tmp_path: Path):
    repo, user_a, user_b = _repo_and_users(tmp_path)
    later = repo.create_portfolio_entry(user_a, _portfolio_input())
    earlier = repo.create_portfolio_entry(
        user_a,
        _portfolio_input(trade_date=date(2026, 8, 1), ticker="vale3"),
    )

    assert later.ticker == "PETR4"
    assert repo.get_portfolio_entry(user_b, later.id) is None
    assert repo.list_portfolio_entries(user_b) == []
    assert repo.update_portfolio_entry(user_b, later.id, later.to_input()) is None
    assert repo.delete_portfolio_entry(user_b, later.id) is False
    assert repo.list_portfolio_entries(user_a) == [earlier, later]

    replacement = _portfolio_input(ticker="bbas3", note="corrigido")
    updated = repo.update_portfolio_entry(user_a, later.id, replacement)
    assert updated is not None
    assert updated.to_input() == replacement
    assert updated.created_at == later.created_at
    assert repo.delete_portfolio_entry(user_a, later.id) is True
    assert repo.get_portfolio_entry(user_a, later.id) is None


def test_option_operation_crud_always_scopes_records_by_owner(tmp_path: Path):
    repo, user_a, user_b = _repo_and_users(tmp_path)
    later = repo.create_option_operation(user_a, _operation_input())
    earlier = repo.create_option_operation(
        user_a,
        _operation_input(sale_date=date(2026, 7, 1), option_ticker="valeu500"),
    )

    assert later.underlying_ticker == "PETR4"
    assert later.option_ticker == "PETRU400"
    assert repo.get_option_operation(user_b, later.id) is None
    assert repo.list_option_operations(user_b) == []
    assert repo.update_option_operation(user_b, later.id, later.to_input()) is None
    assert repo.delete_option_operation(user_b, later.id) is False
    assert repo.list_option_operations(user_a) == [earlier, later]

    replacement = _operation_input(
        status=OptionStatus.CLOSED_EARLY,
        close_cost_per_share_cents=35,
        repurchase_date=date(2026, 8, 20),
    )
    updated = repo.update_option_operation(user_a, later.id, replacement)
    assert updated is not None
    assert updated.to_input() == replacement
    assert updated.created_at == later.created_at
    assert repo.delete_option_operation(user_a, later.id) is True
    assert repo.get_option_operation(user_a, later.id) is None


def test_custody_crud_always_scopes_records_by_owner(tmp_path: Path):
    repo, user_a, user_b = _repo_and_users(tmp_path)
    later = repo.create_custody_entry(
        user_a, CustodyEntryInput(date(2026, 8, 30), 510_000)
    )
    earlier = repo.create_custody_entry(
        user_a, CustodyEntryInput(date(2026, 8, 1), 500_000)
    )

    assert repo.get_custody_entry(user_b, later.id) is None
    assert repo.list_custody_entries(user_b) == []
    assert repo.update_custody_entry(user_b, later.id, later.to_input()) is None
    assert repo.delete_custody_entry(user_b, later.id) is False
    assert repo.list_custody_entries(user_a) == [earlier, later]

    replacement = CustodyEntryInput(date(2026, 8, 29), 515_000)
    updated = repo.update_custody_entry(user_a, later.id, replacement)
    assert updated is not None
    assert updated.to_input() == replacement
    assert updated.created_at == later.created_at
    assert repo.delete_custody_entry(user_a, later.id) is True
    assert repo.get_custody_entry(user_a, later.id) is None


def test_cash_flow_crud_always_scopes_records_by_owner(tmp_path: Path):
    repo, user_a, user_b = _repo_and_users(tmp_path)
    later = repo.create_cash_flow(user_a, _cash_flow_input())
    earlier = repo.create_cash_flow(
        user_a, _cash_flow_input(flow_date=date(2026, 7, 1), note="anterior")
    )

    assert repo.get_cash_flow(user_b, later.id) is None
    assert repo.list_cash_flows(user_b) == []
    assert repo.update_cash_flow(user_b, later.id, later.to_input()) is None
    assert repo.delete_cash_flow(user_b, later.id) is False
    assert repo.list_cash_flows(user_a) == [earlier, later]

    replacement = CashFlowInput(
        date(2026, 8, 2), CashFlowKind.WITHDRAWAL, 10_000, "resgate"
    )
    updated = repo.update_cash_flow(user_a, later.id, replacement)
    assert updated is not None
    assert updated.to_input() == replacement
    assert updated.created_at == later.created_at
    assert repo.delete_cash_flow(user_a, later.id) is True
    assert repo.get_cash_flow(user_a, later.id) is None


def test_cash_and_duplicate_custody_are_scoped_by_owner(tmp_path: Path):
    repo, user_a, user_b = _repo_and_users(tmp_path)

    assert repo.get_cash(user_a) is None
    assert repo.get_cash(user_b) is None
    assert repo.set_cash(user_a, 500_000) == 500_000
    assert repo.get_cash(user_a) == 500_000
    assert repo.get_cash(user_b) is None
    assert repo.set_cash(user_a, None) is None
    assert repo.get_cash(user_a) is None

    repo.create_custody_entry(
        user_a, CustodyEntryInput(date(2026, 8, 30), 510_000)
    )
    with pytest.raises(RepositoryConflict, match="já existe"):
        repo.create_custody_entry(
            user_a, CustodyEntryInput(date(2026, 8, 30), 520_000)
        )
    other = repo.create_custody_entry(
        user_b, CustodyEntryInput(date(2026, 8, 30), 1_000)
    )
    assert other.user_id == user_b


def test_load_inputs_returns_only_the_requested_owners_data(tmp_path: Path):
    repo, user_a, user_b = _repo_and_users(tmp_path)
    repo.set_cash(user_a, 500_000)
    portfolio = repo.create_portfolio_entry(user_a, _portfolio_input())
    operation = repo.create_option_operation(user_a, _operation_input())
    custody = repo.create_custody_entry(
        user_a, CustodyEntryInput(date(2026, 8, 30), 510_000)
    )
    flow = repo.create_cash_flow(user_a, _cash_flow_input())
    repo.set_cash(user_b, 1_000)
    repo.create_portfolio_entry(user_b, _portfolio_input(ticker="vale3"))

    inputs = repo.load_inputs(user_a)

    assert inputs.user_id == user_a
    assert inputs.cash_cents == 500_000
    assert inputs.portfolio_entries == [portfolio]
    assert inputs.option_operations == [operation]
    assert inputs.custody_entries == [custody]
    assert inputs.cash_flows == [flow]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _portfolio_input(ticker="  "), "ticker"),
        (
            lambda: PortfolioEntryInput(
                date(2026, 8, 30),
                "PETR4",
                AssetClass.STOCK,
                TradeSide.BUY,
                0,
                4_100,
                "",
            ),
            "quantidade",
        ),
        (
            lambda: PortfolioEntryInput(
                date(2026, 8, 30),
                "PETR4",
                AssetClass.STOCK,
                TradeSide.BUY,
                100,
                -1,
                "",
            ),
            "preço",
        ),
        (
            lambda: _operation_input(sale_date=date(2026, 9, 19)),
            "venda",
        ),
        (
            lambda: OptionOperationInput(
                date(2026, 8, 1),
                "PETR4",
                "PETRU400",
                OptionKind.PUT,
                100,
                0,
                date(2026, 9, 18),
                80,
                OptionStatus.OPEN,
                None,
                None,
            ),
            "strike",
        ),
        (
            lambda: OptionOperationInput(
                date(2026, 8, 1),
                "PETR4",
                "PETRU400",
                OptionKind.PUT,
                100,
                4_000,
                date(2026, 9, 18),
                -1,
                OptionStatus.OPEN,
                None,
                None,
            ),
            "prêmio",
        ),
        (
            lambda: _operation_input(status=OptionStatus.CLOSED_EARLY),
            "recompra",
        ),
        (
            lambda: _operation_input(
                status=OptionStatus.OPEN,
                close_cost_per_share_cents=35,
                repurchase_date=date(2026, 8, 20),
            ),
            "proíbem",
        ),
        (
            lambda: _operation_input(
                status=OptionStatus.CLOSED_EARLY,
                close_cost_per_share_cents=-1,
                repurchase_date=date(2026, 8, 20),
            ),
            "custo",
        ),
        (
            lambda: _operation_input(
                status=OptionStatus.CLOSED_EARLY,
                close_cost_per_share_cents=35,
                repurchase_date=date(2026, 9, 19),
            ),
            "entre venda e vencimento",
        ),
        (
            lambda: CashFlowInput(
                date(2026, 8, 1), CashFlowKind.CONTRIBUTION, 0, ""
            ),
            "fluxo",
        ),
        (lambda: _portfolio_input(note="x" * 501), "500"),
        (lambda: _cash_flow_input(note="x" * 501), "500"),
    ],
)
def test_inputs_reject_invalid_domain_states(factory, message: str):
    with pytest.raises(ValueError, match=message):
        factory()
