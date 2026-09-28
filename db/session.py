"""
Engine + session factory. SQLite by default (see config.py); swap
DATABASE_URL to a Postgres URL later and this file needs no changes —
the only SQLite-specific bit is the `check_same_thread` connect arg below,
which is a no-op / omitted for other backends.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from db.models import Base

_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_customer_auth_columns() -> None:
    """
    Base.metadata.create_all only creates tables that don't exist yet — it
    never alters an existing table's columns. Customer.password_hash was
    added after this project's demo DB files already existed, so an
    existing `customers` table needs a one-off ALTER TABLE to pick it up;
    without this, every existing electronics_shop.db would need a
    destructive `scripts/reset_demo_db.py` just to get signup/login
    working. SQLite-only (this project's default backend) and safe to run
    on every startup — no-ops once the column/index already exist. A
    Postgres deployment would use a real migration tool (Alembic) instead,
    same as db/session.py's docstring already flags for the DATABASE_URL
    swap in general.
    """
    if not settings.is_sqlite:
        return
    with engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(customers)")}
        if "password_hash" not in columns:
            conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN password_hash VARCHAR")
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_email_unique "
            "ON customers(email) WHERE email IS NOT NULL"
        )
        conn.commit()


def _ensure_order_tracking_columns() -> None:
    """Same reasoning as _ensure_customer_auth_columns() above: the
    tracking_number/carrier/shipped_at/delivered_at columns were added to
    Order after existing demo DB files already had an `orders` table, so
    create_all alone won't pick them up. SQLite-only, safe to re-run."""
    if not settings.is_sqlite:
        return
    with engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(orders)")}
        if "tracking_number" not in columns:
            conn.exec_driver_sql("ALTER TABLE orders ADD COLUMN tracking_number VARCHAR")
        if "carrier" not in columns:
            conn.exec_driver_sql("ALTER TABLE orders ADD COLUMN carrier VARCHAR")
        if "shipped_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE orders ADD COLUMN shipped_at DATETIME")
        if "delivered_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE orders ADD COLUMN delivered_at DATETIME")
        conn.commit()


def init_db() -> None:
    """Creates all tables if they don't exist. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)
    _ensure_customer_auth_columns()
    _ensure_order_tracking_columns()


@contextmanager
def get_session():
    """
    Usage:
        with get_session() as session:
            session.add(obj)
            session.commit()
    Rolls back automatically on exception so partial writes (e.g. an order
    created but its items failed) never persist.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
