
"""Persistent SQLite checkpoint storage for Medibot."""

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


# Project root: C:\Users\Asus\OneDrive\Desktop\Medibot
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Keep application conversations persistent; tests can select an isolated DB.
_configured_memory_path = os.getenv("MEDIBOT_MEMORY_DB_PATH")
MEMORY_DB_PATH = (
    Path(_configured_memory_path).resolve()
    if _configured_memory_path
    else PROJECT_ROOT / "data" / "medibot_memory.sqlite3"
)
MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Keep one connection open while the application is running.
_connection = sqlite3.connect(
    str(MEMORY_DB_PATH),
    check_same_thread=False,
)

_checkpointer = SqliteSaver(_connection)

# Create the checkpoint tables if they do not exist.
_checkpointer.setup()


def get_checkpointer() -> SqliteSaver:
    """Return the shared LangGraph SQLite checkpointer."""
    return _checkpointer
