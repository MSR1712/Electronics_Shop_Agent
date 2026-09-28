"""
Demo "login" endpoints — bare customer_id, no password — same
authentication level as chat_app.py's sidebar picker. Kept for quick demo
testing alongside the real signup/login in api/routers/auth.py; both issue
the same session cookie via api/session.py's issue_session().
"""

from fastapi import APIRouter, HTTPException, Request, Response

from db.models import Customer
from db.session import get_session

from api.schemas import CreateSessionRequest
from api.session import SESSION_COOKIE_NAME, issue_session, require_session

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/customers")
def list_customers():
    """Only the passwordless seeded demo customers — a real signup (which
    does have a password_hash) shouldn't clutter the "quick demo login"
    picker, and couldn't be logged into through this bare-id route anyway."""
    with get_session() as session:
        customers = (
            session.query(Customer)
            .filter(Customer.password_hash.is_(None))
            .order_by(Customer.id)
            .all()
        )
        return [{"id": c.id, "name": c.name} for c in customers]


@router.post("/session")
def create_session(payload: CreateSessionRequest, response: Response):
    with get_session() as session:
        customer = session.get(Customer, payload.customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        name = customer.name

    return issue_session(response, payload.customer_id, name)


@router.get("/session")
def read_session(request: Request):
    """Not in the original spec — added so the frontend can check on load
    whether a session cookie is already present, instead of re-prompting
    the customer picker on every page refresh."""
    session_data = require_session(request)
    with get_session() as session:
        customer = session.get(Customer, session_data.customer_id)
        name = customer.name if customer else session_data.customer_id
    return {
        "customer_id": session_data.customer_id,
        "conversation_id": session_data.conversation_id,
        "name": name,
    }


@router.post("/logout")
def logout(response: Response):
    """Also not in the original spec — clears the cookie so the customer
    picker can be re-shown without waiting for cookie expiry."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"success": True}
