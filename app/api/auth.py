"""Registration, login, and logout endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import (
    authenticate,
    bearer_scheme,
    create_session,
    create_user,
    enforce_auth_rate_limit,
    get_current_user,
    is_valid_email,
    revoke_session,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not is_valid_email(value):
            raise ValueError("Enter a valid email address.")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    name: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, request: Request) -> AuthResponse:
    enforce_auth_rate_limit(request, "register")
    try:
        user = create_user(payload.name, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return AuthResponse(
        access_token=create_session(user["id"]),
        user=UserResponse(**user),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request) -> AuthResponse:
    enforce_auth_rate_limit(request, "login")
    result = authenticate(payload.email, payload.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, token = result
    return AuthResponse(access_token=token, user=UserResponse(**user))


@router.get("/me", response_model=UserResponse)
def current_user(
    user: Annotated[dict[str, str], Depends(get_current_user)],
) -> UserResponse:
    return UserResponse(**user)


@router.post("/logout", status_code=204)
def logout(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> Response:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    get_current_user(credentials)
    revoke_session(credentials.credentials)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
