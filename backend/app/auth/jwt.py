"""JWT token utilities / JWT 토큰 유틸리티."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token / JWT 액세스 토큰 생성."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT token / JWT 토큰 디코드 및 검증."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
