"""Regression tests for isolated SQLite checkpoint storage during pytest."""

import os
from pathlib import Path

from app import auth
from app.memory import checkpointer


def test_test_suite_uses_temporary_checkpoint_storage():
    configured_path = Path(os.environ["MEDIBOT_MEMORY_DB_PATH"]).resolve()

    assert checkpointer.MEMORY_DB_PATH == configured_path
    assert checkpointer.MEMORY_DB_PATH != (
        checkpointer.PROJECT_ROOT / "data" / "medibot_memory.sqlite3"
    )
    assert checkpointer.MEMORY_DB_PATH.is_file()

    configured_auth_path = Path(os.environ["MEDIBOT_AUTH_DB_PATH"]).resolve()
    assert auth.AUTH_DB_PATH == configured_auth_path
    assert auth.AUTH_DB_PATH != auth.PROJECT_ROOT / "data" / "medibot_auth.sqlite3"
