import sqlite3
from pathlib import Path

import pytest

from venda_de_put.carteira.db import Database


EXPECTED_TABLES = {
    "schema_migrations",
    "users",
    "user_sessions",
    "portfolio_state",
    "portfolio_entries",
    "option_operations",
    "custody_entries",
    "cash_flows",
}


def test_migration_v1_is_idempotent_and_enables_integrity(tmp_path: Path):
    db = Database(tmp_path / "carteira.sqlite3")
    db.migrate()
    db.migrate()

    with db.connection() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert EXPECTED_TABLES <= tables
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
        ).fetchone()[0] == 1


def test_option_operation_rejects_owner_or_enum_invalid(tmp_path: Path):
    db = Database(tmp_path / "carteira.sqlite3")
    db.migrate()
    with db.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO option_operations
                   (user_id, sale_date, underlying_ticker, option_ticker,
                    option_kind, quantity, strike_cents, expiry_date,
                    premium_per_share_cents, status, created_at, updated_at)
                   VALUES (999, '2026-08-30', 'PETR4', 'PETRU400', 'put',
                           100, 4000, '2026-09-18', 50, 'open', 'x', 'x')"""
            )


def test_option_operation_rejects_invalid_enum(tmp_path: Path):
    db = Database(tmp_path / "carteira.sqlite3")
    db.migrate()
    with db.connection() as conn:
        user_id = conn.execute(
            """INSERT INTO users
               (username, username_key, password_hash, created_at)
               VALUES ('Maria', 'maria', 'hash', '2026-08-30T00:00:00+00:00')"""
        ).lastrowid

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO option_operations
                   (user_id, sale_date, underlying_ticker, option_ticker,
                    option_kind, quantity, strike_cents, expiry_date,
                    premium_per_share_cents, status, created_at, updated_at)
                   VALUES (?, '2026-08-30', 'PETR4', 'PETRU400', 'future',
                           100, 4000, '2026-09-18', 50, 'open', 'x', 'x')""",
                (user_id,),
            )
