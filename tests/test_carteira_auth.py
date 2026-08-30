from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from venda_de_put.carteira.auth import (
    AuthError,
    AuthService,
    hash_password,
    normalize_username,
    verify_password,
)
from venda_de_put.carteira import auth as auth_module
from venda_de_put.carteira.db import Database


CANONICAL_PASSWORD_HASH = (
    "scrypt$n=32768,r=8,p=1$MDEyMzQ1Njc4OWFiY2RlZg$"
    "oPucAxz7QQoMkztLxXQVv8kdqpjXLj-_GClXlphseGY"
)


def _service(tmp_path: Path, now: datetime) -> AuthService:
    db = Database(tmp_path / "carteira.sqlite3")
    db.migrate()
    return AuthService(db, now=lambda: now)


def test_password_scrypt_round_trip_and_wrong_password():
    encoded = hash_password("uma-senha-bem-longa", salt=b"0123456789abcdef")
    assert encoded == CANONICAL_PASSWORD_HASH
    assert "uma-senha-bem-longa" not in encoded
    assert verify_password("uma-senha-bem-longa", encoded) is True
    assert verify_password("senha-errada", encoded) is False
    assert verify_password("x", "formato-invalido") is False


@pytest.mark.parametrize("salt", [b"", b"x", b"x" * 15, b"x" * 17])
def test_hash_password_rejects_caller_salt_that_is_not_16_bytes(salt: bytes):
    with pytest.raises(AuthError, match="salt deve ter 16 bytes"):
        hash_password("uma-senha-bem-longa", salt=salt)


def test_verify_password_rejects_matching_hash_with_one_byte_salt():
    encoded = (
        "scrypt$n=32768,r=8,p=1$eA$"
        "8ERBnD718cambwGBNYCoMJPmXUXHGj2GrAMl2Ndn8Hc"
    )
    assert verify_password("uma-senha-bem-longa", encoded) is False


def test_verify_password_rejects_wrong_digest_length_before_scrypt(monkeypatch):
    def unexpected_derive(password: str, salt: bytes) -> bytes:
        pytest.fail("scrypt não deve rodar para digest com tamanho inválido")

    monkeypatch.setattr(auth_module, "_derive", unexpected_derive)
    encoded = "scrypt$n=32768,r=8,p=1$MDEyMzQ1Njc4OWFiY2RlZg$AA"
    assert verify_password("uma-senha-bem-longa", encoded) is False


@pytest.mark.parametrize(
    "encoded",
    [
        CANONICAL_PASSWORD_HASH.replace(
            "MDEyMzQ1Njc4OWFiY2RlZg", "MDEyMzQ1Njc4OWFiY2RlZg=="
        ),
        CANONICAL_PASSWORD_HASH + "=",
    ],
)
def test_verify_password_rejects_padded_base64(encoded: str):
    assert verify_password("uma-senha-bem-longa", encoded) is False


@pytest.mark.parametrize(
    "encoded",
    [
        CANONICAL_PASSWORD_HASH.replace(
            "MDEyMzQ1Njc4OWFiY2RlZg", "MDEy!MzQ1Njc4OWFiY2RlZg=="
        ),
        CANONICAL_PASSWORD_HASH.replace(
            "oPucAxz7QQoMkztLxXQVv8kdqpjXLj-_GClXlphseGY",
            "oPuc!Axz7QQoMkztLxXQVv8kdqpjXLj-_GClXlphseGY=",
        ),
    ],
)
def test_verify_password_rejects_non_alphabet_base64(encoded: str):
    assert verify_password("uma-senha-bem-longa", encoded) is False


def test_username_is_case_insensitive_and_session_can_be_revoked(tmp_path: Path):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    session = auth.register("Igor.B", "senha-pessoal-123")
    assert normalize_username("  IGOR.B ") == "igor.b"
    assert auth.resolve_session(session.token).username == "Igor.B"

    with pytest.raises(AuthError, match="usuário já existe"):
        auth.register("igor.b", "outra-senha-123")

    auth.logout(session.token)
    assert auth.resolve_session(session.token) is None


def test_expired_session_is_rejected(tmp_path: Path):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    session = auth.register("igor", "senha-pessoal-123")
    expired = AuthService(auth.db, now=lambda: now + timedelta(hours=13))
    assert expired.resolve_session(session.token) is None


def test_registration_creates_personal_state_and_persists_only_token_hashes(
    tmp_path: Path,
):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    session = auth.register(" Maria ", "senha-pessoal-123")

    with auth.db.connection() as conn:
        user = conn.execute(
            "SELECT username, username_key FROM users WHERE id = ?",
            (session.user.user_id,),
        ).fetchone()
        state = conn.execute(
            "SELECT cash_cents FROM portfolio_state WHERE user_id = ?",
            (session.user.user_id,),
        ).fetchone()
        stored_session = conn.execute(
            "SELECT token_hash, csrf_hash FROM user_sessions WHERE user_id = ?",
            (session.user.user_id,),
        ).fetchone()

    assert tuple(user) == ("Maria", "maria")
    assert state["cash_cents"] is None
    assert stored_session["token_hash"] != session.token
    assert stored_session["csrf_hash"] != session.csrf_token
    assert len(stored_session["token_hash"]) == 64
    assert len(stored_session["csrf_hash"]) == 64
    assert session.expires_at == now + timedelta(hours=12)


def test_login_uses_same_error_and_one_scrypt_for_unknown_or_wrong_password(
    tmp_path: Path,
    monkeypatch,
):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    auth.register("Igor", "senha-pessoal-123")

    real_derive = auth_module._derive
    calls = []

    def counting_derive(password: str, salt: bytes) -> bytes:
        calls.append((password, salt))
        return real_derive(password, salt)

    monkeypatch.setattr(auth_module, "_derive", counting_derive)

    with pytest.raises(AuthError, match="^usuário ou senha inválidos$"):
        auth.login("desconhecido", "senha-pessoal-123")
    assert len(calls) == 1

    calls.clear()
    with pytest.raises(AuthError, match="^usuário ou senha inválidos$"):
        auth.login("IGOR", "senha-pessoal-errada")
    assert len(calls) == 1


def test_login_returns_new_session_and_csrf_is_bound_to_it(tmp_path: Path):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    registered = auth.register("Igor", "senha-pessoal-123")
    logged_in = auth.login(" igor ", "senha-pessoal-123")

    assert logged_in.user == registered.user
    assert logged_in.token != registered.token
    assert auth.verify_csrf(logged_in.token, logged_in.csrf_token) is True
    assert auth.verify_csrf(logged_in.token, registered.csrf_token) is False
    assert auth.verify_csrf("token-inválido", logged_in.csrf_token) is False


def test_expired_csrf_is_rejected_and_login_removes_expired_sessions(
    tmp_path: Path,
):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    session = auth.register("Igor", "senha-pessoal-123")
    later = AuthService(auth.db, now=lambda: now + timedelta(hours=13))

    assert later.verify_csrf(session.token, session.csrf_token) is False
    later.login("igor", "senha-pessoal-123")

    with auth.db.connection() as conn:
        stored_sessions = conn.execute(
            "SELECT COUNT(*) FROM user_sessions WHERE user_id = ?",
            (session.user.user_id,),
        ).fetchone()[0]
    assert stored_sessions == 1


@pytest.mark.parametrize("username", ["ab", "-igor", "ig or", "ígor"])
def test_registration_rejects_invalid_username(tmp_path: Path, username: str):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    with pytest.raises(AuthError, match="usuário deve ter 3 a 32 caracteres"):
        auth.register(username, "senha-pessoal-123")


@pytest.mark.parametrize("password", ["curta", "x" * 129])
def test_registration_rejects_password_outside_length_limit(
    tmp_path: Path,
    password: str,
):
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    auth = _service(tmp_path, now)
    with pytest.raises(AuthError, match="^senha deve ter 12 a 128 caracteres$"):
        auth.register("igor", password)
