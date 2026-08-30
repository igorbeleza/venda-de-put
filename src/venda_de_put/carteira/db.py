from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    username_key TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON user_sessions(expires_at);
CREATE TABLE IF NOT EXISTS portfolio_state (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    cash_cents INTEGER,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolio_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'margin')),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfolio_owner_date
    ON portfolio_entries(user_id, trade_date, id);
CREATE TABLE IF NOT EXISTS option_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sale_date TEXT NOT NULL,
    underlying_ticker TEXT NOT NULL,
    option_ticker TEXT NOT NULL,
    option_kind TEXT NOT NULL CHECK (option_kind IN ('call', 'put')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    strike_cents INTEGER NOT NULL CHECK (strike_cents > 0),
    expiry_date TEXT NOT NULL,
    premium_per_share_cents INTEGER NOT NULL CHECK (premium_per_share_cents >= 0),
    status TEXT NOT NULL CHECK (status IN ('open', 'expired', 'exercised', 'closed_early')),
    close_cost_per_share_cents INTEGER CHECK (
        close_cost_per_share_cents IS NULL OR close_cost_per_share_cents >= 0
    ),
    repurchase_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (sale_date <= expiry_date),
    CHECK (
      (status = 'closed_early' AND close_cost_per_share_cents IS NOT NULL AND repurchase_date IS NOT NULL)
      OR
      (status <> 'closed_early' AND close_cost_per_share_cents IS NULL AND repurchase_date IS NULL)
    ),
    CHECK (repurchase_date IS NULL OR (repurchase_date >= sale_date AND repurchase_date <= expiry_date))
);
CREATE INDEX IF NOT EXISTS idx_options_owner_date
    ON option_operations(user_id, sale_date, id);
CREATE INDEX IF NOT EXISTS idx_options_owner_status
    ON option_operations(user_id, status, expiry_date);
CREATE TABLE IF NOT EXISTS custody_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    as_of_date TEXT NOT NULL,
    total_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, as_of_date)
);
CREATE TABLE IF NOT EXISTS cash_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    flow_date TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('contribution', 'withdrawal')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cash_flows_owner_date
    ON cash_flows(user_id, flow_date, id);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if has_table and conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 1"
            ).fetchone():
                return
            applied_at = datetime.now(timezone.utc).isoformat().replace("'", "''")
            script = (
                "BEGIN IMMEDIATE;\n"
                + SCHEMA_V1
                + f"\nINSERT INTO schema_migrations(version, applied_at) VALUES (1, '{applied_at}');"
                + "\nCOMMIT;"
            )
            try:
                conn.executescript(script)
            except sqlite3.IntegrityError:
                conn.rollback()
                if conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = 1"
                ).fetchone():
                    return
                raise
            except Exception:
                conn.rollback()
                raise
