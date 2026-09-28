"""
Admin session handling for api/routers/admin.py — deliberately separate
from api/session.py's customer cookie. A customer session can never act as
an admin (different cookie name, different signing salt), and an admin
session carries no customer_id, so it can't place orders or chat as anyone.

Login is a single shared ADMIN_PASSWORD from .env (demo-grade, like the
rest of api/'s auth). If ADMIN_PASSWORD is unset the admin panel is
disabled entirely rather than falling back to a default password.

The signing salt includes a fingerprint of ADMIN_PASSWORD, so changing the
password in .env immediately invalidates every existing admin cookie.
"""

import hashlib
import hmac

import itsdangerous
from fastapi import HTTPException, Request, Response

from config import settings

ADMIN_COOKIE_NAME = "cw_admin"
ADMIN_SESSION_MAX_AGE_SECONDS = 60 * 60 * 12  # 12 hours


def _serializer() -> itsdangerous.URLSafeTimedSerializer:
    fingerprint = hashlib.sha256(settings.admin_password.encode("utf-8")).hexdigest()[:16]
    return itsdangerous.URLSafeTimedSerializer(settings.session_secret_key, salt=f"cw-admin:{fingerprint}")


def _require_enabled() -> None:
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin panel is disabled. Set ADMIN_PASSWORD in .env.")


def check_admin_password(password: str) -> bool:
    _require_enabled()
    return hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))


def issue_admin_session(response: Response) -> None:
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        _serializer().dumps({"admin": True}),
        httponly=True,
        samesite="lax",
        max_age=ADMIN_SESSION_MAX_AGE_SECONDS,
        path="/",
    )


def require_admin(request: Request) -> None:
    """FastAPI dependency: 401 unless the request carries a valid admin cookie."""
    _require_enabled()
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Admin login required.")
    try:
        data = _serializer().loads(token, max_age=ADMIN_SESSION_MAX_AGE_SECONDS)
    except itsdangerous.BadData:
        raise HTTPException(status_code=401, detail="Admin session expired or invalid.")
    if data.get("admin") is not True:
        raise HTTPException(status_code=401, detail="Admin login required.")
