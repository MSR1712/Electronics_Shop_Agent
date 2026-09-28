"""
Session handling: a signed (not encrypted) cookie carrying customer_id +
conversation_id, issued by either api/routers/customers.py's bare-id demo
picker or api/routers/auth.py's real password signup/login, and read by
every other endpoint that needs to act as a customer.

The cookie's *shape* is identical either way — a signed value carrying an
opaque customer_id the browser can't forge or edit — which is why nothing
downstream (checkout, chat, orders) needs to know or care which login path
issued it; require_session()/get_ws_session() are the single choke point.

One cookie = one conversation_id = one LangGraph checkpoint thread, so the
manual checkout UI and the chat widget started from the same browser
session always resolve to the same (customer_id, conversation_id) pair
that tools/order_tools.py scopes pending confirmations to.
"""

import uuid

import itsdangerous
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from config import settings

SESSION_COOKIE_NAME = "cw_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days

_serializer = itsdangerous.URLSafeTimedSerializer(settings.session_secret_key, salt="cw-session")


class SessionData(BaseModel):
    customer_id: str
    conversation_id: str


def sign_session(customer_id: str, conversation_id: str) -> str:
    return _serializer.dumps({"customer_id": customer_id, "conversation_id": conversation_id})


def issue_session(response: Response, customer_id: str, name: str) -> dict:
    """Shared by every login path (demo picker, signup, password login):
    mints a fresh conversation_id, signs the session cookie, sets it on
    the response, and returns the same shape POST /api/session has always
    returned. A fresh login always starts a fresh conversation_id, same as
    chat_app.py resetting its thread_id when the acting customer changes."""
    conversation_id = str(uuid.uuid4())
    token = sign_session(customer_id=customer_id, conversation_id=conversation_id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return {"customer_id": customer_id, "name": name, "conversation_id": conversation_id}


def _read_session(token: str) -> SessionData | None:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except itsdangerous.BadData:
        return None
    return SessionData(**data)


def get_ws_session(websocket) -> SessionData | None:
    """Same lookup as require_session, for a WebSocket connection instead
    of an HTTP request — used by api/routers/voice.py, since a browser
    WebSocket handshake still carries the same-site session cookie."""
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return _read_session(token)


def require_session(request: Request) -> SessionData:
    """FastAPI dependency: the authenticated (customer_id, conversation_id)
    for this request, or a 401 if there's no valid session cookie. Every
    checkout/chat/order endpoint depends on this instead of accepting
    customer_id from the request body — mirrors make_order_tools() never
    accepting customer_id as an LLM-settable argument."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in. POST /api/session first.")
    data = _read_session(token)
    if data is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid. POST /api/session again.")
    return data
