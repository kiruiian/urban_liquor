from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.modules.auth.dependencies import get_current_staff, require_admin
from app.modules.auth.models import Staff
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    StaffCreate,
    StaffPasswordUpdate,
    StaffRead,
    StaffUpdate,
)

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    normalized_username = payload.username.strip().lower()
    staff = await session.scalar(
        select(Staff).where(Staff.username == normalized_username)
    )
    if (
        staff is None
        or not staff.is_active
        or not verify_password(payload.password, staff.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(staff.id)
    return LoginResponse(access_token=token, staff=StaffRead.model_validate(staff))


@router.get("/me", response_model=StaffRead)
async def get_me(
    staff: Annotated[Staff, Depends(get_current_staff)],
) -> Staff:
    return staff


@router.post("/staff", response_model=StaffRead, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Staff, Depends(require_admin)],
) -> Staff:
    full_name = payload.full_name.strip()
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name cannot be blank",
        )
    staff = Staff(
        username=payload.username.strip().lower(),
        full_name=full_name,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        is_active=True,
    )
    session.add(staff)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username is already in use"
        ) from exc
    return staff


@router.get("/staff", response_model=list[StaffRead])
async def list_staff(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Staff, Depends(require_admin)],
) -> list[Staff]:
    result = await session.scalars(
        select(Staff).order_by(Staff.role, Staff.username, Staff.id)
    )
    return list(result.all())


@router.patch("/staff/{staff_id}", response_model=StaffRead)
async def update_staff(
    staff_id: int,
    payload: StaffUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[Staff, Depends(require_admin)],
) -> Staff:
    changes = payload.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one non-null field to update",
        )

    staff = await session.get(Staff, staff_id)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    if "username" in changes:
        changes["username"] = changes["username"].strip().lower()
    if "full_name" in changes:
        changes["full_name"] = changes["full_name"].strip()
        if not changes["full_name"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Full name cannot be blank",
            )

    if staff_id == admin.id and changes.get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account",
        )

    removes_active_admin = (
        staff.role == "admin"
        and staff.is_active
        and (
            changes.get("role", staff.role) != "admin"
            or changes.get("is_active", staff.is_active) is False
        )
    )
    if removes_active_admin:
        active_admins = await session.scalars(
            select(Staff.id)
            .where(Staff.role == "admin", Staff.is_active.is_(True))
            .order_by(Staff.id)
            .with_for_update()
        )
        if len(active_admins.all()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last active admin cannot be demoted or deactivated",
            )

    for field, value in changes.items():
        setattr(staff, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username is already in use"
        ) from exc
    return staff


@router.post(
    "/staff/{staff_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def update_staff_password(
    staff_id: int,
    payload: StaffPasswordUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Staff, Depends(require_admin)],
) -> Response:
    staff = await session.get(Staff, staff_id)
    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found"
        )

    staff.password_hash = get_password_hash(payload.password)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
