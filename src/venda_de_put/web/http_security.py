from fastapi import Request


def forwarded_prefix(request: Request) -> str:
    raw = (request.headers.get("x-forwarded-prefix") or "").strip()
    if not raw.startswith("/") or raw.startswith("//") or "://" in raw:
        return ""
    return raw.rstrip("/")


def cookie_path(request: Request) -> str:
    return forwarded_prefix(request) or "/"


def cookie_secure(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    return proto == "https"
