"""
Real password-based signup/login, additive to the bare-customer_id demo
picker in api/routers/customers.py (kept for quick testing against the
seeded demo customers, which have no password and can't use these routes).

Passwords are hashed with bcrypt (api/passwords.py) — never stored, logged,
or compared as plaintext. Both routes issue the same signed session cookie
api/session.py's other login path does (issue_session), so nothing
downstream (checkout, chat, orders, voice) needs to know or care which
login path a session came from.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from db.models import Customer
from db.session import get_session

from api.passwords import hash_password, verify_password
from api.session import issue_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


@router.post("/signup")
def signup(payload: SignupRequest, response: Response):
    customer_id = f"cust-{uuid.uuid4().hex[:10]}"
    with get_session() as session:
        session.add(
            Customer(
                id=customer_id,
                name=payload.name,
                email=payload.email,
                password_hash=hash_password(payload.password),
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="An account with that email already exists.")

    return issue_session(response, customer_id, payload.name)


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    with get_session() as session:
        customer = session.query(Customer).filter(Customer.email == payload.email).first()
        # Same "invalid email or password" error either way — never reveal
        # whether the email exists, so this can't be used to enumerate
        # accounts (or seeded demo customers, who have no password set).
        if customer is None or not verify_password(payload.password, customer.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        customer_id, name = customer.id, customer.name

    return issue_session(response, customer_id, name)
