"""Account registration, login, and session endpoints."""

import re
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    clear_session_cookies,
    client_identity,
    create_session,
    enforce_rate_limit,
    get_auth_context,
    hash_password,
    purge_expired_data,
    require_csrf,
    verify_password,
)
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class AccountDeletionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


def _limit_auth_attempts(db: Session, request: Request, scope: str) -> None:
    enforce_rate_limit(
        db,
        scope=f"auth:{scope}",
        identity=client_identity(request),
        limit=10,
        window_seconds=15 * 60,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    credentials: Credentials,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Create an account and sign in the new user."""
    _limit_auth_attempts(db, request, "register")
    if db.scalar(select(User.id).where(User.email == credentials.email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        id=str(uuid4()),
        email=credentials.email,
        password_hash=hash_password(credentials.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    csrf_token = create_session(db, user, response)
    return {"email": user.email, "csrf_token": csrf_token}


@router.post("/login")
def login(
    credentials: Credentials,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Verify credentials and issue an opaque, revocable session."""
    _limit_auth_attempts(db, request, "login")
    user = db.scalar(select(User).where(User.email == credentials.email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(password_hash, credentials.password)

    if user is None or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    csrf_token = create_session(db, user, response)
    return {"email": user.email, "csrf_token": csrf_token}


@router.get("/me")
def current_account(
    auth=Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Return the signed-in account and CSRF token for this browser session."""
    purge_expired_data(db)
    if not auth.csrf_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is incomplete. Sign in again.",
        )
    return {"email": auth.user.email, "csrf_token": auth.csrf_token}


@router.post("/logout")
def logout(
    response: Response,
    auth=Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Revoke the current session and expire its cookies."""
    db.delete(auth.session)
    db.commit()
    clear_session_cookies(response)
    return {"authenticated": False}


@router.delete("/me")
def delete_account(
    credentials: AccountDeletionRequest,
    response: Response,
    auth=Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Delete an account, its sessions, and all owned conversations."""
    if not verify_password(auth.user.password_hash, credentials.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )

    db.delete(auth.user)
    db.commit()
    clear_session_cookies(response)
    return {"deleted": True}
