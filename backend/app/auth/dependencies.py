"""FastAPI authentication dependencies / FastAPI 인증 의존성."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.db.session import get_db
from app.models.db_models import User

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user from JWT token.
    JWT 토큰으로부터 현재 인증된 사용자 가져오기.
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials / 잘못된 인증 정보",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: int | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload / 잘못된 토큰 페이로드",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found / 사용자를 찾을 수 없습니다",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user / 비활성화된 사용자",
        )

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current superuser / 현재 슈퍼유저 가져오기."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges / 권한이 부족합니다",
        )
    return current_user
