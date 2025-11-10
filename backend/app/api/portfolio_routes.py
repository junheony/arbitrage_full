"""Portfolio API routes / 포트폴리오 API 라우트."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.db_models import User
from app.services.portfolio import PortfolioService

router = APIRouter(tags=["portfolio"])


@router.get("/summary")
async def get_portfolio_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get comprehensive portfolio summary.
    종합 포트폴리오 요약 조회.

    Includes:
    - Total exposure by asset and exchange
    - Open orders count
    - Realized PnL

    포함 내용:
    - 자산 및 거래소별 총 익스포저
    - 미체결 주문 수
    - 실현 손익
    """
    service = PortfolioService(db)
    return await service.get_portfolio_summary(current_user.id)


@router.get("/balances")
async def get_balances(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get current balances across all exchanges.
    모든 거래소의 현재 잔고 조회.
    """
    service = PortfolioService(db)
    balances = await service.get_balances(current_user.id)
    return {
        "balances": [
            {
                "exchange": b.exchange,
                "asset": b.asset,
                "free": b.free,
                "locked": b.locked,
                "total": b.total,
                "usd_value": b.usd_value,
                "timestamp": b.timestamp.isoformat(),
            }
            for b in balances
        ]
    }


@router.get("/exposure")
async def get_exposure(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get total portfolio exposure.
    총 포트폴리오 익스포저 조회.
    """
    service = PortfolioService(db)
    return await service.calculate_total_exposure(current_user.id)


@router.get("/pnl")
async def get_pnl(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get profit/loss summary.
    손익 요약 조회.
    """
    service = PortfolioService(db)
    return await service.calculate_pnl(current_user.id)


@router.get("/orders/open")
async def get_open_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get all open orders.
    모든 미체결 주문 조회.
    """
    service = PortfolioService(db)
    orders = await service.get_open_orders(current_user.id)
    return {
        "orders": [
            {
                "id": o.id,
                "exchange": o.exchange,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "quantity": o.quantity,
                "price": o.price,
                "filled_quantity": o.filled_quantity,
                "status": o.status.value,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ]
    }
