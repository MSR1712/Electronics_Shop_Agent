"""
FastAPI layer in front of the same graph/tools chat_app.py and voice_app.py
already use — no business logic lives here, only HTTP plumbing (sessions,
request/response shaping) around build_graph() and the tool factories in
tools/order_tools.py and tools/product_tools.py.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.session import init_db
from graph import build_graph

from api.routers import admin, auth, chat, checkout, customers, products, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    # Built once at process startup, like chat_app.py's st.session_state.graph
    # — build_graph() opens a SqliteSaver connection meant to live for the
    # process's lifetime, not be recreated per request.
    app.state.graph = build_graph()
    yield


app = FastAPI(title="CircuitWorks Storefront API", lifespan=lifespan)

# The Next.js dev server's origin, explicitly — never "*", since cookies
# (allow_credentials=True) can't be sent to a wildcard origin anyway, and a
# wildcard would defeat the point of a signed session cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers.router)
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(checkout.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
