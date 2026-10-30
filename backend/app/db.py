"""
app/db.py — database engine + session.

SQLAlchemy 2.0 style. The same code runs against Neon PostgreSQL
(DATABASE_URL in .env) and against SQLite in tests, because we only use
portable column types.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

if not settings.DATABASE_URL:
    # Fail early with a clear message instead of a confusing crash later.
    raise RuntimeError(
        "DATABASE_URL bo'sh! backend/.env fayliga Neon PostgreSQL "
        "manzilini yozing (postgresql+psycopg://...)"
    )

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False  # tests only

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
