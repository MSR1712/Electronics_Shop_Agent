"""Pydantic request bodies for the api/ package. Response shapes are mostly
passed through verbatim from the tool JSON (tools/order_tools.py,
tools/product_tools.py) rather than re-modeled here, so the API can't drift
from what those tools actually return."""

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    customer_id: str


class OrderItemIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


class PrepareCheckoutRequest(BaseModel):
    items: list[OrderItemIn]


class ConfirmCheckoutRequest(BaseModel):
    confirmation_id: int


class ChatRequest(BaseModel):
    message: str
