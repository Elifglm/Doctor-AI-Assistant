"""Admin routes for user management. Only accessible by admin role."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from apps.backend.src.db.database import async_session_maker
from apps.backend.src.db.models import User
from apps.backend.src.dependencies import get_current_user
from apps.backend.src.schemas.admin import (
    OpenEMRDoctor,
    OpenEMRSyncResponse,
    UserCreateRequest,
    UserListResponse,
    UserPasswordChangeRequest,
    UserResponse,
    UserUpdateRequest,
)
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.services.auth_service import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _require_admin(user: UserInfo) -> None:
    """Raise 403 if the user is not an admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için admin yetkisi gereklidir",
        )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    user: UserInfo = Depends(get_current_user),
) -> UserListResponse:
    """List all users. Admin only."""
    _require_admin(user)

    async with async_session_maker() as session:
        result = await session.execute(select(User).order_by(User.id))
        users = result.scalars().all()
        count = len(users)

    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=count,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    user: UserInfo = Depends(get_current_user),
) -> UserResponse:
    """Create a new user. Admin only."""
    _require_admin(user)

    async with async_session_maker() as session:
        # Check username uniqueness
        existing = await session.execute(
            select(User).where(User.username == body.username)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"'{body.username}' kullanıcı adı zaten mevcut",
            )

        new_user = User(
            username=body.username,
            hashed_password=hash_password(body.password),
            display_name=body.display_name,
            role=body.role,
            brans=body.brans,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        logger.info("Yeni kullanici olusturuldu: %s (%s)", body.username, body.brans)
        return UserResponse.model_validate(new_user)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    user: UserInfo = Depends(get_current_user),
) -> UserResponse:
    """Get a single user by ID. Admin only."""
    _require_admin(user)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        db_user = result.scalar_one_or_none()

    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı",
        )

    return UserResponse.model_validate(db_user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    user: UserInfo = Depends(get_current_user),
) -> UserResponse:
    """Update user details (display_name, role, brans, is_active). Admin only."""
    _require_admin(user)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kullanıcı bulunamadı",
            )

        if body.display_name is not None:
            db_user.display_name = body.display_name
        if body.role is not None:
            db_user.role = body.role
        if body.brans is not None:
            db_user.brans = body.brans
        if body.is_active is not None:
            db_user.is_active = body.is_active

        await session.commit()
        await session.refresh(db_user)

        logger.info("Kullanici guncellendi: %s", db_user.username)
        return UserResponse.model_validate(db_user)


@router.patch("/users/{user_id}/password")
async def change_password(
    user_id: int,
    body: UserPasswordChangeRequest,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Change a user's password. Admin only."""
    _require_admin(user)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kullanıcı bulunamadı",
            )

        db_user.hashed_password = hash_password(body.new_password)
        await session.commit()

        logger.info("Kullanici sifresi degistirildi: %s", db_user.username)
        return {"message": "Şifre başarıyla değiştirildi"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    user: UserInfo = Depends(get_current_user),
) -> dict:
    """Permanently delete a user from the database. Admin only."""
    _require_admin(user)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kullanıcı bulunamadı",
            )

        if db_user.username == user.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kendi hesabınızı silemezsiniz",
            )

        deleted_name = db_user.username
        await session.delete(db_user)
        await session.commit()

        logger.info("Kullanici kalici olarak silindi: %s", deleted_name)
        return {"message": f"'{deleted_name}' kullanıcısı silindi"}


@router.get("/openemr-doctors", response_model=OpenEMRSyncResponse)
async def sync_openemr_doctors(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> OpenEMRSyncResponse:
    """Fetch doctors from OpenEMR and compare with local users.

    Returns all OpenEMR doctors with a flag indicating whether they
    already exist in KlinikAsistan.
    """
    _require_admin(user)

    openemr_service = getattr(request.app.state, "openemr_service", None)
    if openemr_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenEMR servisi kullanılamaz",
        )

    # Get practitioners from OpenEMR
    practitioners = await openemr_service.list_practitioners()

    # Get existing usernames from KlinikAsistan DB
    async with async_session_maker() as session:
        result = await session.execute(select(User.username))
        existing_usernames = {row[0] for row in result}

    doctors: list[OpenEMRDoctor] = []
    new_count = 0
    for p in practitioners:
        already = p["username"] in existing_usernames
        if not already:
            new_count += 1
        doctors.append(OpenEMRDoctor(
            openemr_id=str(p.get("id", "")),
            username=p["username"],
            fname=p.get("fname", ""),
            lname=p.get("lname", ""),
            specialty=p.get("specialty", ""),
            already_in_system=already,
        ))

    return OpenEMRSyncResponse(
        doctors=doctors,
        new_count=new_count,
        total_count=len(doctors),
    )
