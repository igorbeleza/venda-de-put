from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from venda_de_put.carteira.db import Database


SCRYPT_N = 32768
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SESSION_SECONDS = 12 * 3600
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
BASE64_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class UserPrincipal:
    user_id: int
    username: str


@dataclass(frozen=True)
class SessionBundle:
    user: UserPrincipal
    token: str
    csrf_token: str
    expires_at: datetime


def normalize_username(value: str) -> str:
    key = value.strip().casefold()
    if not USERNAME_RE.fullmatch(key):
        raise AuthError(
            "usuário deve ter 3 a 32 caracteres: letras minúsculas, números, "
            "ponto, hífen ou sublinhado"
        )
    return key


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not BASE64_RE.fullmatch(value):
        raise ValueError("base64 inválido")
    padding = "=" * (-len(value) % 4)
    decoded = base64.b64decode(
        value + padding,
        altchars=b"-_",
        validate=True,
    )
    if _b64encode(decoded) != value:
        raise ValueError("base64 não canônico")
    return decoded


def hash_password(password: str, salt: bytes | None = None) -> str:
    if not 12 <= len(password) <= 128:
        raise AuthError("senha deve ter 12 a 128 caracteres")
    actual_salt = secrets.token_bytes(16) if salt is None else salt
    if len(actual_salt) != 16:
        raise AuthError("salt deve ter 16 bytes")
    digest = _derive(password, actual_salt)
    return (
        f"scrypt$n=32768,r=8,p=1${_b64encode(actual_salt)}$"
        f"{_b64encode(digest)}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, params, salt_text, digest_text = encoded.split("$")
        if (
            algorithm != "scrypt"
            or params != "n=32768,r=8,p=1"
            or len(password) > 128
        ):
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        if len(salt) != 16 or len(expected) != SCRYPT_DKLEN:
            return False
        actual = _derive(password, salt)
    except (TypeError, ValueError, binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_PASSWORD_HASH = hash_password(
    "senha-ficticia-segura",
    salt=b"0123456789abcdef",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        db: Database,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = db
        self._now = now

    @property
    def db(self) -> Database:
        return self._db

    def register(self, username: str, password: str) -> SessionBundle:
        username_key = normalize_username(username)
        display_username = username.strip()
        password_hash = hash_password(password)
        now = self._now()
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=SESSION_SECONDS)

        with self._db.connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._delete_expired(conn, now)
                user_id = conn.execute(
                    """INSERT INTO users
                       (username, username_key, password_hash, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        display_username,
                        username_key,
                        password_hash,
                        now.isoformat(),
                    ),
                ).lastrowid
                if user_id is None:
                    raise RuntimeError("falha ao criar usuário")
                conn.execute(
                    """INSERT INTO portfolio_state
                       (user_id, cash_cents, updated_at)
                       VALUES (?, NULL, ?)""",
                    (user_id, now.isoformat()),
                )
                bundle = SessionBundle(
                    user=UserPrincipal(
                        user_id=int(user_id),
                        username=display_username,
                    ),
                    token=token,
                    csrf_token=csrf_token,
                    expires_at=expires_at,
                )
                self._insert_session(conn, bundle, now)
                conn.commit()
            except sqlite3.IntegrityError as error:
                conn.rollback()
                if "users.username_key" in str(error):
                    raise AuthError("usuário já existe") from error
                raise
            except Exception:
                conn.rollback()
                raise

        return bundle

    def login(self, username: str, password: str) -> SessionBundle:
        try:
            username_key: str | None = normalize_username(username)
        except AuthError:
            username_key = None

        now = self._now()
        bundle: SessionBundle | None = None
        with self._db.connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._delete_expired(conn, now)
                row = None
                if username_key is not None:
                    row = conn.execute(
                        """SELECT id, username, password_hash
                           FROM users WHERE username_key = ?""",
                        (username_key,),
                    ).fetchone()

                encoded = (
                    _DUMMY_PASSWORD_HASH if row is None else row["password_hash"]
                )
                candidate = "\0" if len(password) > 128 else password
                valid_password = verify_password(candidate, encoded)
                if len(password) > 128:
                    valid_password = False

                if row is not None and valid_password:
                    principal = UserPrincipal(
                        user_id=int(row["id"]),
                        username=row["username"],
                    )
                    bundle = self._make_bundle(principal, now)
                    self._insert_session(conn, bundle, now)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        if bundle is None:
            raise AuthError("usuário ou senha inválidos")
        return bundle

    def resolve_session(self, token: str) -> UserPrincipal | None:
        now = self._now().isoformat()
        with self._db.connection() as conn:
            row = conn.execute(
                """SELECT users.id, users.username
                   FROM user_sessions
                   JOIN users ON users.id = user_sessions.user_id
                   WHERE user_sessions.token_hash = ?
                     AND user_sessions.expires_at > ?""",
                (_sha256(token), now),
            ).fetchone()
        if row is None:
            return None
        return UserPrincipal(user_id=int(row["id"]), username=row["username"])

    def verify_csrf(self, token: str, csrf_token: str) -> bool:
        now = self._now().isoformat()
        with self._db.connection() as conn:
            row = conn.execute(
                """SELECT csrf_hash
                   FROM user_sessions
                   WHERE token_hash = ? AND expires_at > ?""",
                (_sha256(token), now),
            ).fetchone()
        if row is None:
            return False
        return hmac.compare_digest(row["csrf_hash"], _sha256(csrf_token))

    def logout(self, token: str) -> None:
        with self._db.connection() as conn:
            conn.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?",
                (_sha256(token),),
            )
            conn.commit()

    @staticmethod
    def _delete_expired(conn: sqlite3.Connection, now: datetime) -> None:
        conn.execute(
            "DELETE FROM user_sessions WHERE expires_at <= ?",
            (now.isoformat(),),
        )

    @staticmethod
    def _make_bundle(principal: UserPrincipal, now: datetime) -> SessionBundle:
        return SessionBundle(
            user=principal,
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=now + timedelta(seconds=SESSION_SECONDS),
        )

    @staticmethod
    def _insert_session(
        conn: sqlite3.Connection,
        bundle: SessionBundle,
        now: datetime,
    ) -> None:
        conn.execute(
            """INSERT INTO user_sessions
               (token_hash, user_id, csrf_hash, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                _sha256(bundle.token),
                bundle.user.user_id,
                _sha256(bundle.csrf_token),
                now.isoformat(),
                bundle.expires_at.isoformat(),
            ),
        )
