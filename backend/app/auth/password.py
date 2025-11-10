"""Password hashing utilities / 비밀번호 해싱 유틸리티."""
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt / bcrypt로 비밀번호 해싱."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash / 비밀번호 해시 검증."""
    return pwd_context.verify(plain_password, hashed_password)
