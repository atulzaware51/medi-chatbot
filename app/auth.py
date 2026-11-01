"""SQLite-backed users and opaque bearer sessions for Medibot."""

import hashlib
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_configured_db_path = os.getenv("MEDIBOT_AUTH_DB_PATH")
AUTH_DB_PATH = (
    Path(_configured_db_path).resolve()
    if _configured_db_path
    else PROJECT_ROOT / "data" / "medibot_auth.sqlite3"
)
AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

ACCESS_TOKEN_TTL_SECONDS = 12 * 60 * 60
AUTH_RATE_LIMIT_ATTEMPTS = 10
AUTH_RATE_LIMIT_WINDOW_SECONDS = 60
PASSWORD_HASHER = PasswordHasher()
_DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(
    "medibot-invalid-login-timing-placeholder"
)
bearer_scheme = HTTPBearer(auto_error=False)


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    """Open and always close an application database connection."""
    connection = sqlite3.connect(str(AUTH_DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_auth_db() -> None:
    """Create auth tables if needed."""
    with connect_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_rate_limits (
                bucket_hash TEXT PRIMARY KEY,
                window_started_at REAL NOT NULL,
                attempts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS conversations_user_updated
                ON conversations(user_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_conversation_created
                ON messages(conversation_id, created_at);
            """
        )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def create_user(name: str, email: str, password: str) -> dict[str, str]:
    user_id = str(uuid4())
    normalized_email = email.strip().lower()
    password_hash = PASSWORD_HASHER.hash(password)

    try:
        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO users (id, name, email, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, name.strip(), normalized_email, password_hash, _now_iso()),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists.") from exc

    return {"id": user_id, "name": name.strip(), "email": normalized_email}


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                _token_digest(token),
                user_id,
                time.time() + ACCESS_TOKEN_TTL_SECONDS,
                _now_iso(),
            ),
        )
    return token


def enforce_auth_rate_limit(request: Request, action: str) -> None:
    """Limit repeated registration/login attempts without storing raw IPs."""
    address = request.client.host if request.client else ""
    if not address:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Authentication is temporarily unavailable.",
        )

    bucket_hash = hashlib.sha256(
        f"{action}:{address}".encode("utf-8")
    ).hexdigest()
    now = time.time()

    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT window_started_at, attempts
            FROM auth_rate_limits
            WHERE bucket_hash = ?
            """,
            (bucket_hash,),
        ).fetchone()

        if (
            row is None
            or now - row["window_started_at"] >= AUTH_RATE_LIMIT_WINDOW_SECONDS
        ):
            connection.execute(
                """
                INSERT OR REPLACE INTO auth_rate_limits
                    (bucket_hash, window_started_at, attempts)
                VALUES (?, ?, 1)
                """,
                (bucket_hash, now),
            )
            return

        if row["attempts"] >= AUTH_RATE_LIMIT_ATTEMPTS:
            retry_after = max(
                1,
                int(
                    AUTH_RATE_LIMIT_WINDOW_SECONDS
                    - (now - row["window_started_at"])
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )

        connection.execute(
            """
            UPDATE auth_rate_limits SET attempts = attempts + 1
            WHERE bucket_hash = ?
            """,
            (bucket_hash,),
        )


def authenticate(email: str, password: str) -> tuple[dict[str, str], str] | None:
    normalized_email = email.strip().lower()
    with connect_db() as connection:
        row = connection.execute(
            "SELECT id, name, email, password_hash FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()

    password_hash = row["password_hash"] if row else _DUMMY_PASSWORD_HASH
    valid_password = _verify_password(password, password_hash)
    if row is None or not valid_password:
        return None

    user = {"id": row["id"], "name": row["name"], "email": row["email"]}
    return user, create_session(user["id"])


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.name, users.email
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (_token_digest(credentials.credentials), time.time()),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def revoke_session(token: str) -> None:
    with connect_db() as connection:
        connection.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?",
            (_token_digest(token),),
        )


def is_valid_email(email: str) -> bool:
    return bool(
        re.fullmatch(r"[^@\s]{1,64}@[^@\s.]{1,63}(?:\.[^@\s.]{1,63})+", email)
    )


initialize_auth_db()
