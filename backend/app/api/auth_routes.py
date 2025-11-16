"""Authentication API routes / 인증 API 라우트."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.auth.password import hash_password, verify_password
from app.db.session import get_db
from app.models.db_models import RiskLimit, User

router = APIRouter(tags=["auth"])


class UserCreate(BaseModel):
    """User registration schema / 사용자 등록 스키마."""

    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """User login schema / 사용자 로그인 스키마."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """JWT token response / JWT 토큰 응답."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User info response / 사용자 정보 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    """
    Register a new user / 신규 사용자 등록.

    Creates user account with default risk limits.
    기본 리스크 한도와 함께 사용자 계정 생성.
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered / 이미 등록된 이메일입니다",
        )

    # Create new user
    hashed_pwd = hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_pwd,
        full_name=user_data.full_name,
        is_active=True,
        is_superuser=False,
    )
    db.add(new_user)
    await db.flush()  # Get user ID

    # Create default risk limits
    default_limits = RiskLimit(user_id=new_user.id)
    db.add(default_limits)

    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """
    Login and get JWT token / 로그인하여 JWT 토큰 획득.

    Returns access token valid for 7 days.
    7일간 유효한 액세스 토큰 반환.
    """
    # Find user
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password / 이메일 또는 비밀번호가 잘못되었습니다",
        )

    # Verify password
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password / 이메일 또는 비밀번호가 잘못되었습니다",
        )

    # Check if active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account / 비활성화된 사용자 계정",
        )

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> User:
    """
    Get current user information / 현재 사용자 정보 가져오기.

    Requires valid JWT token in Authorization header.
    Authorization 헤더에 유효한 JWT 토큰 필요.
    """
    return current_user
