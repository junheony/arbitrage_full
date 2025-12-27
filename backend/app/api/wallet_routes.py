"""Wallet status proxy for Upbit API (requires fixed IP)"""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from base64 import urlsafe_b64encode
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _generate_upbit_jwt() -> str | None:
    """Generate Upbit JWT token for API authentication"""
    settings = get_settings()
    access_key = settings.upbit_access_key
    secret_key = settings.upbit_secret_key

    if not access_key or not secret_key:
        return None

    import json

    payload = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
    }

    # Manual JWT construction (HS256)
    header = urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    body = urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    signature = urlsafe_b64encode(
        hmac.new(secret_key.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()

    return f"{header}.{body}.{signature}"


@router.get("/upbit/wallet-status")
async def get_upbit_wallet_status(token: str = Query(None, description="Auth token")) -> dict[str, Any]:
    """
    Proxy for Upbit wallet status API.
    This endpoint runs on a server with fixed IP registered with Upbit.
    """
    # Simple token auth (optional)
    settings = get_settings()
    expected_token = settings.wallet_proxy_token
    if expected_token and token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    jwt_token = _generate_upbit_jwt()
    if not jwt_token:
        raise HTTPException(status_code=500, detail="Upbit API keys not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                "https://api.upbit.com/v1/status/wallet",
                headers={"Authorization": f"Bearer {jwt_token}"},
            )
            response.raise_for_status()
            data = response.json()

            # Transform to simpler format
            result = {}
            for item in data:
                currency = item.get("currency", "")
                wallet_state = item.get("wallet_state", "")

                # wallet_state: working, withdraw_only, deposit_only, paused, unsupported
                deposit_enabled = wallet_state in ("working", "deposit_only")
                withdraw_enabled = wallet_state in ("working", "withdraw_only")

                result[currency] = {
                    "deposit": deposit_enabled,
                    "withdraw": withdraw_enabled,
                    "state": wallet_state,
                }

            return {
                "success": True,
                "count": len(result),
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Upbit API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            logger.error(f"Upbit wallet status fetch failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
