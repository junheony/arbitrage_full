"""API key encryption utilities / API 키 암호화 유틸리티."""
from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

settings = get_settings()


def _get_fernet() -> Fernet:
    """Get Fernet cipher using app secret key / 앱 시크릿 키로 Fernet 암호화 객체 생성."""
    # Derive a key from the secret_key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"arbitrage_salt_change_in_prod",  # Should be unique per deployment
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.secret_key.encode()))
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key / API 키 암호화."""
    f = _get_fernet()
    encrypted = f.encrypt(api_key.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key / API 키 복호화."""
    f = _get_fernet()
    encrypted_bytes = base64.b64decode(encrypted_key.encode())
    decrypted = f.decrypt(encrypted_bytes)
    return decrypted.decode()
