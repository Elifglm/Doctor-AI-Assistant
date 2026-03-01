"""Authentication routes: login, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from apps.backend.src.dependencies import get_current_user
from apps.backend.src.schemas.auth import LoginRequest, TokenResponse, UserInfo
from apps.backend.src.schemas.common import BaseResponse
from apps.backend.src.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    authenticate_user,
    create_access_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """Authenticate with username/password and receive a JWT."""
    user = authenticate_user(body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya şifre",
        )
    token = create_access_token(
        {
            "sub": user.username,
            "display_name": user.display_name,
            "role": user.role,
        }
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        user=user,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: UserInfo = Depends(get_current_user),
) -> TokenResponse:
    """Issue a fresh JWT for an already-authenticated user."""
    token = create_access_token(
        {
            "sub": current_user.username,
            "display_name": current_user.display_name,
            "role": current_user.role,
        }
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        user=current_user,
    )


@router.post("/logout", response_model=BaseResponse)
async def logout(
    current_user: UserInfo = Depends(get_current_user),
) -> BaseResponse:
    """Logout (stateless -- just acknowledges the request)."""
    return BaseResponse(message="Logged out successfully")
