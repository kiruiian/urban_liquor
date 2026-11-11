from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.modules.auth.models import Staff

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_staff(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Staff:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise unauthorized
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise unauthorized

    staff = await session.get(Staff, int(subject))
    if staff is None or not staff.is_active:
        raise unauthorized
    return staff


async def require_owner(
    staff: Annotated[Staff, Depends(get_current_staff)],
) -> Staff:
    if staff.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner privileges required",
        )
    return staff
