"""Use a disposable application database for the entire test session."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest


_test_database_directory = Path(
    tempfile.mkdtemp(prefix="medibot-pytest-db-")
)
os.environ["MEDIBOT_ENV"] = "test"
os.environ["DATABASE_URL"] = (
    f"sqlite:///{_test_database_directory / 'application.sqlite3'}"
)
os.environ["MEDIBOT_RETENTION_DAYS"] = "30"

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AuthSession,
    Conversation,
    ConversationMessage,
    RateLimitBucket,
    User,
)


@pytest.fixture(autouse=True)
def clear_application_database():
    """Keep tests independent while reusing one temporary database file."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def pytest_sessionfinish(session, exitstatus):
    """Close the disposable DB and remove its temporary directory."""
    engine.dispose()
    shutil.rmtree(_test_database_directory)

    os.environ.pop("MEDIBOT_ENV", None)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("MEDIBOT_RETENTION_DAYS", None)
