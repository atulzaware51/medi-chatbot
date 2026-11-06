"""Authentication helpers and database-backed request throttling."""

import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AuthSession,
    Conversation,
    RateLimitBucket,
    User,
    utc_now,
)


SESSION_COOKIE = "medibot_session"
CSRF_COOKIE = "medibot_csrf"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
RETENTION_DAYS = int(os.getenv("MEDIBOT_RETENTION_DAYS", "30"))
if not 1 <= RETENTION_DAYS <= 365:
    raise RuntimeError("MEDIBOT_RETENTION_DAYS must be between 1 and 365.")
_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_local_rate_limit_lock = threading.Lock()


class AuthContext(NamedTuple):
    user: User
    session: AuthSession
    csrf_token: str


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password without revealing malformed hashes to clients."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def set_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    """Issue a short-lived HttpOnly session cookie and a CSRF cookie."""
    secure_setting = os.getenv("MEDIBOT_COOKIE_SECURE", "").strip().lower()
    secure = (
        secure_setting in {"1", "true", "yes"}
        if secure_setting
        else bool(os.getenv("RENDER"))
    )
    common = {
        "max_age": SESSION_MAX_AGE_SECONDS,
        "secure": secure,
        "samesite": "strict",
        "path": "/",
    }
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        **common,
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        **common,
    )


def clear_session_cookies(response: Response) -> None:
    """Expire both authentication cookies."""
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", samesite="strict")


def create_session(db: Session, user: User, response: Response) -> str:
    """Persist only hashes of newly generated session and CSRF secrets."""
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            id=str(uuid4()),
            user_id=user.id,
            token_hash=_digest(token),
            csrf_hash=_digest(csrf_token),
            expires_at=utc_now() + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
        )
    )
    db.commit()
    set_session_cookies(response, token, csrf_token)
    return csrf_token


def get_auth_context(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthContext:
    """Resolve the current session from its opaque HttpOnly cookie."""
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in is required.",
        )

    record = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == _digest(token))
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in is required.",
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= utc_now():
        db.delete(record)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Sign in again.",
        )

    csrf_token = request.cookies.get(CSRF_COOKIE, "")
    return AuthContext(record.user, record, csrf_token)


def require_csrf(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require a session-bound double-submit token for state-changing requests."""
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("X-CSRF-Token", "")
    valid = (
        bool(csrf_cookie)
        and hmac.compare_digest(csrf_cookie, csrf_header)
        and hmac.compare_digest(_digest(csrf_cookie), auth.session.csrf_hash)
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )
    return auth


def enforce_rate_limit(
    db: Session,
    *,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Apply a shared database-backed fixed-window limit without storing raw IPs."""
    now = utc_now()
    key = _digest(f"{scope}:{identity}")
    lock = _local_rate_limit_lock
    with lock:
        try:
            if db.bind and db.bind.dialect.name == "postgresql":
                db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": key},
                )
            bucket = db.get(RateLimitBucket, key)
            if bucket is None:
                bucket = RateLimitBucket(
                    key=key,
                    window_started_at=now,
                    hits=0,
                )
                db.add(bucket)
                db.flush()

            started_at = bucket.window_started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if now - started_at >= timedelta(seconds=window_seconds):
                bucket.window_started_at = now
                bucket.hits = 0

            bucket.hits += 1
            blocked = bucket.hits > limit
            db.commit()
        except Exception:
            db.rollback()
            raise

    if blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before trying again.",
            headers={"Retry-After": str(window_seconds)},
        )


def client_identity(request: Request) -> str:
    """Return the direct peer address for rate-limit bucketing."""
    if request.client is None:
        return "unknown"
    return request.client.host


def purge_expired_data(db: Session) -> None:
    """Delete old conversations and expired sessions under the configured policy."""
    cutoff = utc_now() - timedelta(days=RETENTION_DAYS)
    db.execute(
        delete(Conversation)
        .where(Conversation.updated_at < cutoff)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(AuthSession)
        .where(AuthSession.expires_at < utc_now())
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(RateLimitBucket)
        .where(RateLimitBucket.window_started_at < cutoff)
        .execution_options(synchronize_session=False)
    )
    db.commit()
