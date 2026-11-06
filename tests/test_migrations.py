"""Verify that the checked-in Alembic migrations build a fresh database."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine, inspect


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_legacy_database(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE auth_rate_limits (
                bucket_hash TEXT PRIMARY KEY,
                window_started_at REAL NOT NULL,
                attempts INTEGER NOT NULL
            );
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX conversations_user_updated
                ON conversations(user_id, updated_at DESC);
            CREATE INDEX messages_conversation_created
                ON messages(conversation_id, created_at);
            INSERT INTO users VALUES
                ('user-1', 'Legacy User', 'legacy@example.com', '$argon2id$hash', '2025-01-01T00:00:00Z');
            INSERT INTO auth_sessions VALUES
                ('token-hash', 'user-1', 1735776000, '2025-01-01T00:00:00Z');
            INSERT INTO conversations VALUES
                ('conversation-1', 'user-1', 'Legacy chat', '2025-01-02T00:00:00Z', '2025-01-03T00:00:00Z');
            INSERT INTO messages VALUES
                ('message-1', 'conversation-1', 'user', 'Question', '[]', '2025-01-02T00:00:00Z');
            INSERT INTO messages VALUES
                ('message-2', 'conversation-1', 'assistant', 'Answer', '[{"name":"source"}]', '2025-01-02T00:00:01Z');
            """
        )


def _run_migration(database_path: Path, legacy_path: Path | None = None) -> None:
    environment = os.environ.copy()
    environment.pop("MEDIBOT_ENV", None)
    environment.pop("RENDER", None)
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    if legacy_path is not None:
        environment["MEDIBOT_AUTH_DB_PATH"] = str(legacy_path)
    else:
        environment.pop("MEDIBOT_AUTH_DB_PATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_migrated_data(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        user = connection.execute(
            "SELECT id, name, email, password_hash FROM users"
        ).fetchone()
        sessions = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]
        conversation = connection.execute(
            "SELECT id, owner_id, title FROM conversations"
        ).fetchone()
        messages = connection.execute(
            "SELECT role, content, sources FROM conversation_messages "
            "ORDER BY id"
        ).fetchall()

    assert user == (
        "user-1",
        "Legacy User",
        "legacy@example.com",
        "$argon2id$hash",
    )
    assert sessions == 0
    assert conversation == ("conversation-1", "user-1", "Legacy chat")
    assert messages == [
        ("user", "Question", "[]"),
        ("assistant", "Answer", '[{"name": "source"}]'),
    ]
    assert not any(name.startswith("_medibot_legacy_") for name in table_names)


def test_fresh_database_migrates_to_current_schema():
    with tempfile.TemporaryDirectory(prefix="medibot-migration-test-") as directory:
        database_path = Path(directory) / "migration.sqlite3"
        environment = os.environ.copy()
        environment.pop("MEDIBOT_ENV", None)
        environment.pop("RENDER", None)
        environment["DATABASE_URL"] = f"sqlite:///{database_path}"

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        engine = create_engine(f"sqlite:///{database_path}")
        table_names = set(inspect(engine).get_table_names())
        engine.dispose()

    assert {
        "users",
        "auth_sessions",
        "conversations",
        "conversation_messages",
        "rate_limit_buckets",
        "alembic_version",
    }.issubset(table_names)


def test_legacy_sqlite_accounts_and_conversations_are_migrated():
    with tempfile.TemporaryDirectory(prefix="medibot-legacy-migration-test-") as directory:
        directory_path = Path(directory)
        legacy_path = directory_path / "legacy.sqlite3"
        database_path = directory_path / "application.sqlite3"

        _create_legacy_database(legacy_path)
        _run_migration(database_path, legacy_path)
        _assert_migrated_data(database_path)


def test_legacy_database_can_be_migrated_in_place():
    with tempfile.TemporaryDirectory(prefix="medibot-in-place-migration-test-") as directory:
        database_path = Path(directory) / "application.sqlite3"
        _create_legacy_database(database_path)
        _run_migration(database_path, database_path)
        _assert_migrated_data(database_path)
