from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from venda_de_put.carteira.db import Database
from venda_de_put.carteira.models import (
    AssetClass,
    CashFlow,
    CashFlowInput,
    CashFlowKind,
    CustodyEntry,
    CustodyEntryInput,
    OptionKind,
    OptionOperation,
    OptionOperationInput,
    OptionStatus,
    PersonalInputs,
    PortfolioEntry,
    PortfolioEntryInput,
    TradeSide,
)


class RepositoryConflict(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _portfolio_from_row(row: sqlite3.Row) -> PortfolioEntry:
    return PortfolioEntry(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        trade_date=date.fromisoformat(row["trade_date"]),
        ticker=row["ticker"],
        asset_class=AssetClass(row["asset_class"]),
        side=TradeSide(row["side"]),
        quantity=int(row["quantity"]),
        price_cents=int(row["price_cents"]),
        note=row["note"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _option_from_row(row: sqlite3.Row) -> OptionOperation:
    repurchase_date = row["repurchase_date"]
    close_cost = row["close_cost_per_share_cents"]
    return OptionOperation(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        sale_date=date.fromisoformat(row["sale_date"]),
        underlying_ticker=row["underlying_ticker"],
        option_ticker=row["option_ticker"],
        option_kind=OptionKind(row["option_kind"]),
        quantity=int(row["quantity"]),
        strike_cents=int(row["strike_cents"]),
        expiry_date=date.fromisoformat(row["expiry_date"]),
        premium_per_share_cents=int(row["premium_per_share_cents"]),
        status=OptionStatus(row["status"]),
        close_cost_per_share_cents=(
            None if close_cost is None else int(close_cost)
        ),
        repurchase_date=(
            None if repurchase_date is None else date.fromisoformat(repurchase_date)
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _custody_from_row(row: sqlite3.Row) -> CustodyEntry:
    return CustodyEntry(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        as_of_date=date.fromisoformat(row["as_of_date"]),
        total_cents=int(row["total_cents"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _cash_flow_from_row(row: sqlite3.Row) -> CashFlow:
    return CashFlow(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        flow_date=date.fromisoformat(row["flow_date"]),
        kind=CashFlowKind(row["kind"]),
        amount_cents=int(row["amount_cents"]),
        note=row["note"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _raise_custody_conflict(error: sqlite3.IntegrityError) -> None:
    if "custody_entries.user_id, custody_entries.as_of_date" in str(error):
        raise RepositoryConflict(
            "já existe uma posição de custódia para esta data"
        ) from error
    raise error


class CarteiraRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_cash(self, user_id: int) -> int | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT cash_cents FROM portfolio_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None or row["cash_cents"] is None:
            return None
        return int(row["cash_cents"])

    def set_cash(self, user_id: int, cash_cents: int | None) -> int | None:
        updated_at = _now().isoformat()
        with self.db.connection() as conn:
            conn.execute(
                """UPDATE portfolio_state
                   SET cash_cents = ?, updated_at = ?
                   WHERE user_id = ?""",
                (cash_cents, updated_at, user_id),
            )
            conn.commit()
        return cash_cents

    def create_portfolio_entry(
        self, user_id: int, value: PortfolioEntryInput
    ) -> PortfolioEntry:
        now = _now().isoformat()
        with self.db.connection() as conn:
            entry_id = conn.execute(
                """INSERT INTO portfolio_entries
                   (user_id, trade_date, ticker, asset_class, side, quantity,
                    price_cents, note, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    value.trade_date.isoformat(),
                    value.ticker,
                    value.asset_class.value,
                    value.side.value,
                    value.quantity,
                    value.price_cents,
                    value.note,
                    now,
                    now,
                ),
            ).lastrowid
            row = conn.execute(
                "SELECT * FROM portfolio_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("falha ao criar lançamento da carteira")
        return _portfolio_from_row(row)

    def get_portfolio_entry(
        self, user_id: int, entry_id: int
    ) -> PortfolioEntry | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM portfolio_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
        return None if row is None else _portfolio_from_row(row)

    def list_portfolio_entries(self, user_id: int) -> list[PortfolioEntry]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM portfolio_entries
                   WHERE user_id = ? ORDER BY trade_date, id""",
                (user_id,),
            ).fetchall()
        return [_portfolio_from_row(row) for row in rows]

    def update_portfolio_entry(
        self, user_id: int, entry_id: int, value: PortfolioEntryInput
    ) -> PortfolioEntry | None:
        updated_at = _now().isoformat()
        with self.db.connection() as conn:
            cursor = conn.execute(
                """UPDATE portfolio_entries
                   SET trade_date = ?, ticker = ?, asset_class = ?, side = ?,
                       quantity = ?, price_cents = ?, note = ?, updated_at = ?
                   WHERE id = ? AND user_id = ?""",
                (
                    value.trade_date.isoformat(),
                    value.ticker,
                    value.asset_class.value,
                    value.side.value,
                    value.quantity,
                    value.price_cents,
                    value.note,
                    updated_at,
                    entry_id,
                    user_id,
                ),
            )
            row = None
            if cursor.rowcount == 1:
                row = conn.execute(
                    "SELECT * FROM portfolio_entries WHERE id = ? AND user_id = ?",
                    (entry_id, user_id),
                ).fetchone()
            conn.commit()
        return None if row is None else _portfolio_from_row(row)

    def delete_portfolio_entry(self, user_id: int, entry_id: int) -> bool:
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM portfolio_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            )
            conn.commit()
        return cursor.rowcount == 1

    def create_option_operation(
        self, user_id: int, value: OptionOperationInput
    ) -> OptionOperation:
        now = _now().isoformat()
        with self.db.connection() as conn:
            operation_id = conn.execute(
                """INSERT INTO option_operations
                   (user_id, sale_date, underlying_ticker, option_ticker,
                    option_kind, quantity, strike_cents, expiry_date,
                    premium_per_share_cents, status,
                    close_cost_per_share_cents, repurchase_date,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    value.sale_date.isoformat(),
                    value.underlying_ticker,
                    value.option_ticker,
                    value.option_kind.value,
                    value.quantity,
                    value.strike_cents,
                    value.expiry_date.isoformat(),
                    value.premium_per_share_cents,
                    value.status.value,
                    value.close_cost_per_share_cents,
                    None
                    if value.repurchase_date is None
                    else value.repurchase_date.isoformat(),
                    now,
                    now,
                ),
            ).lastrowid
            row = conn.execute(
                "SELECT * FROM option_operations WHERE id = ? AND user_id = ?",
                (operation_id, user_id),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("falha ao criar operação de opção")
        return _option_from_row(row)

    def get_option_operation(
        self, user_id: int, operation_id: int
    ) -> OptionOperation | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM option_operations WHERE id = ? AND user_id = ?",
                (operation_id, user_id),
            ).fetchone()
        return None if row is None else _option_from_row(row)

    def list_option_operations(self, user_id: int) -> list[OptionOperation]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM option_operations
                   WHERE user_id = ? ORDER BY sale_date, id""",
                (user_id,),
            ).fetchall()
        return [_option_from_row(row) for row in rows]

    def update_option_operation(
        self, user_id: int, operation_id: int, value: OptionOperationInput
    ) -> OptionOperation | None:
        updated_at = _now().isoformat()
        with self.db.connection() as conn:
            cursor = conn.execute(
                """UPDATE option_operations
                   SET sale_date = ?, underlying_ticker = ?, option_ticker = ?,
                       option_kind = ?, quantity = ?, strike_cents = ?,
                       expiry_date = ?, premium_per_share_cents = ?, status = ?,
                       close_cost_per_share_cents = ?, repurchase_date = ?,
                       updated_at = ?
                   WHERE id = ? AND user_id = ?""",
                (
                    value.sale_date.isoformat(),
                    value.underlying_ticker,
                    value.option_ticker,
                    value.option_kind.value,
                    value.quantity,
                    value.strike_cents,
                    value.expiry_date.isoformat(),
                    value.premium_per_share_cents,
                    value.status.value,
                    value.close_cost_per_share_cents,
                    None
                    if value.repurchase_date is None
                    else value.repurchase_date.isoformat(),
                    updated_at,
                    operation_id,
                    user_id,
                ),
            )
            row = None
            if cursor.rowcount == 1:
                row = conn.execute(
                    "SELECT * FROM option_operations WHERE id = ? AND user_id = ?",
                    (operation_id, user_id),
                ).fetchone()
            conn.commit()
        return None if row is None else _option_from_row(row)

    def delete_option_operation(self, user_id: int, operation_id: int) -> bool:
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM option_operations WHERE id = ? AND user_id = ?",
                (operation_id, user_id),
            )
            conn.commit()
        return cursor.rowcount == 1

    def create_custody_entry(
        self, user_id: int, value: CustodyEntryInput
    ) -> CustodyEntry:
        now = _now().isoformat()
        try:
            with self.db.connection() as conn:
                entry_id = conn.execute(
                    """INSERT INTO custody_entries
                       (user_id, as_of_date, total_cents, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        value.as_of_date.isoformat(),
                        value.total_cents,
                        now,
                        now,
                    ),
                ).lastrowid
                row = conn.execute(
                    "SELECT * FROM custody_entries WHERE id = ? AND user_id = ?",
                    (entry_id, user_id),
                ).fetchone()
                conn.commit()
        except sqlite3.IntegrityError as error:
            _raise_custody_conflict(error)
        if row is None:
            raise RuntimeError("falha ao criar posição de custódia")
        return _custody_from_row(row)

    def get_custody_entry(
        self, user_id: int, entry_id: int
    ) -> CustodyEntry | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM custody_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
        return None if row is None else _custody_from_row(row)

    def list_custody_entries(self, user_id: int) -> list[CustodyEntry]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM custody_entries
                   WHERE user_id = ? ORDER BY as_of_date, id""",
                (user_id,),
            ).fetchall()
        return [_custody_from_row(row) for row in rows]

    def update_custody_entry(
        self, user_id: int, entry_id: int, value: CustodyEntryInput
    ) -> CustodyEntry | None:
        updated_at = _now().isoformat()
        try:
            with self.db.connection() as conn:
                cursor = conn.execute(
                    """UPDATE custody_entries
                       SET as_of_date = ?, total_cents = ?, updated_at = ?
                       WHERE id = ? AND user_id = ?""",
                    (
                        value.as_of_date.isoformat(),
                        value.total_cents,
                        updated_at,
                        entry_id,
                        user_id,
                    ),
                )
                row = None
                if cursor.rowcount == 1:
                    row = conn.execute(
                        """SELECT * FROM custody_entries
                           WHERE id = ? AND user_id = ?""",
                        (entry_id, user_id),
                    ).fetchone()
                conn.commit()
        except sqlite3.IntegrityError as error:
            _raise_custody_conflict(error)
        return None if row is None else _custody_from_row(row)

    def delete_custody_entry(self, user_id: int, entry_id: int) -> bool:
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM custody_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            )
            conn.commit()
        return cursor.rowcount == 1

    def create_cash_flow(
        self, user_id: int, value: CashFlowInput
    ) -> CashFlow:
        now = _now().isoformat()
        with self.db.connection() as conn:
            flow_id = conn.execute(
                """INSERT INTO cash_flows
                   (user_id, flow_date, kind, amount_cents, note,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    value.flow_date.isoformat(),
                    value.kind.value,
                    value.amount_cents,
                    value.note,
                    now,
                    now,
                ),
            ).lastrowid
            row = conn.execute(
                "SELECT * FROM cash_flows WHERE id = ? AND user_id = ?",
                (flow_id, user_id),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("falha ao criar fluxo de caixa")
        return _cash_flow_from_row(row)

    def get_cash_flow(self, user_id: int, flow_id: int) -> CashFlow | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cash_flows WHERE id = ? AND user_id = ?",
                (flow_id, user_id),
            ).fetchone()
        return None if row is None else _cash_flow_from_row(row)

    def list_cash_flows(self, user_id: int) -> list[CashFlow]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM cash_flows
                   WHERE user_id = ? ORDER BY flow_date, id""",
                (user_id,),
            ).fetchall()
        return [_cash_flow_from_row(row) for row in rows]

    def update_cash_flow(
        self, user_id: int, flow_id: int, value: CashFlowInput
    ) -> CashFlow | None:
        updated_at = _now().isoformat()
        with self.db.connection() as conn:
            cursor = conn.execute(
                """UPDATE cash_flows
                   SET flow_date = ?, kind = ?, amount_cents = ?, note = ?,
                       updated_at = ?
                   WHERE id = ? AND user_id = ?""",
                (
                    value.flow_date.isoformat(),
                    value.kind.value,
                    value.amount_cents,
                    value.note,
                    updated_at,
                    flow_id,
                    user_id,
                ),
            )
            row = None
            if cursor.rowcount == 1:
                row = conn.execute(
                    "SELECT * FROM cash_flows WHERE id = ? AND user_id = ?",
                    (flow_id, user_id),
                ).fetchone()
            conn.commit()
        return None if row is None else _cash_flow_from_row(row)

    def delete_cash_flow(self, user_id: int, flow_id: int) -> bool:
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM cash_flows WHERE id = ? AND user_id = ?",
                (flow_id, user_id),
            )
            conn.commit()
        return cursor.rowcount == 1

    def load_inputs(self, user_id: int) -> PersonalInputs:
        return PersonalInputs(
            user_id=user_id,
            cash_cents=self.get_cash(user_id),
            portfolio_entries=self.list_portfolio_entries(user_id),
            option_operations=self.list_option_operations(user_id),
            custody_entries=self.list_custody_entries(user_id),
            cash_flows=self.list_cash_flows(user_id),
        )
