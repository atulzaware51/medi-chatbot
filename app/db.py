"""Database engine and session management."""

import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Base(DeclarativeBase):
    """Base class for application database models."""


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        if os.getenv("RENDER"):
            raise RuntimeError("DATABASE_URL must be configured in production.")
        value = f"sqlite:///{PROJECT_ROOT / 'data' / 'medibot.sqlite3'}"

    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


DATABASE_URL = _database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)

# Test schemas are isolated in pytest's temporary SQLite database.
if os.getenv("MEDIBOT_ENV") == "test":
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a short-lived database session for a request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
