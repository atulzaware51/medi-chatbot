"""Use disposable SQLite checkpoint storage for the entire test session."""

import os
import shutil
import sys
import tempfile
from pathlib import Path


_original_memory_path = os.environ.get("MEDIBOT_MEMORY_DB_PATH")
_original_auth_path = os.environ.get("MEDIBOT_AUTH_DB_PATH")
_test_memory_directory = Path(
    tempfile.mkdtemp(prefix="medibot-pytest-memory-")
)
os.environ["MEDIBOT_MEMORY_DB_PATH"] = str(
    _test_memory_directory / "checkpoints.sqlite3"
)
os.environ["MEDIBOT_AUTH_DB_PATH"] = str(
    _test_memory_directory / "auth.sqlite3"
)


def pytest_sessionfinish(session, exitstatus):
    """Close the isolated SQLite handle before removing its temporary files."""
    checkpointer = sys.modules.get("app.memory.checkpointer")
    if checkpointer is not None:
        checkpointer._connection.close()

    shutil.rmtree(_test_memory_directory)

    if _original_memory_path is None:
        os.environ.pop("MEDIBOT_MEMORY_DB_PATH", None)
    else:
        os.environ["MEDIBOT_MEMORY_DB_PATH"] = _original_memory_path

    if _original_auth_path is None:
        os.environ.pop("MEDIBOT_AUTH_DB_PATH", None)
    else:
        os.environ["MEDIBOT_AUTH_DB_PATH"] = _original_auth_path
