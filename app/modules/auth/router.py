from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.modules.auth.dependencies import get_current_staff, require_owner
from app.modules.auth.models import Staff
from app.modules.auth.schemas import LoginRequest, LoginResponse, StaffCreate, StaffRead

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    normalized_email = str(payload.email).strip().lower()
    staff = await session.scalar(select(Staff).where(Staff.email == normalized_email))
    if (
        staff is None
        or not staff.is_active
        or not verify_password(payload.password, staff.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
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
    _owner: Annotated[Staff, Depends(require_owner)],
) -> Staff:
    staff = Staff(
        email=str(payload.email).strip().lower(),
        full_name=payload.full_name.strip(),
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
            status_code=status.HTTP_409_CONFLICT, detail="Email address is already in use"
        ) from exc
    return staff
