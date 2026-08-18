from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

SESSION_MAX_AGE_SECONDS: int = 12 * 3600  # 12 horas

# Se VENDA_DE_PUT_SECRET_KEY não for informada no ambiente, usa chave aleatória
# gerada no import do módulo (sessões não sobrevivem ao restart do processo neste caso).
_MODULE_FALLBACK_KEY: bytes = secrets.token_bytes(32)


def _get_secret_key() -> bytes:
    key = os.environ.get("VENDA_DE_PUT_SECRET_KEY")
    if key:
        return key.encode("utf-8")
    return _MODULE_FALLBACK_KEY


def check_password(password: str) -> bool:
    """Verifica a senha informada contra a variável de ambiente.

    Se VENDA_DE_PUT_ADMIN_PASSWORD não estiver definida, retorna False (nunca crasha).
    """
    if not isinstance(password, str):
        return False
    admin_password = os.environ.get("VENDA_DE_PUT_ADMIN_PASSWORD")
    if not admin_password:
        return False
    return hmac.compare_digest(password, admin_password)


def create_session_token() -> str:
    """Gera um token de sessão assinado contendo timestamp e nonce aleatório.

    Formato: {timestamp}.{nonce}.{hmac_sha256}
    """
    ts = int(time.time())
    nonce = secrets.token_hex(16)
    payload = f"{ts}.{nonce}"
    sig = hmac.new(_get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_token(token: str, max_age: int = SESSION_MAX_AGE_SECONDS) -> bool:
    """Verifica a integridade da assinatura e expiração do token de sessão."""
    if not token or not isinstance(token, str):
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    ts_str, nonce, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False

    payload = f"{ts}.{nonce}"
    expected_sig = hmac.new(_get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False

    now = int(time.time())
    if now - ts > max_age or ts > now + 60:
        return False

    return True
