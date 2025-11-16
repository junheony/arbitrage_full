"""Auto trading API routes / 자동 거래 API 라우트."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.db_models import User
from app.services.auto_trader import (
    AggressiveStrategy,
    AutoTraderManager,
    ConservativeStrategy,
    FundingRateStrategy,
    get_auto_trader_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["autotrading"])


class StartAutoTradingRequest(BaseModel):
    """Request to start auto trading / 자동 거래 시작 요청."""

    strategy: str  # "conservative", "aggressive", "funding_rate"
    dry_run: bool = True
    check_interval: int = 10

    # Strategy-specific parameters
    min_spread_bps: Optional[float] = None
    min_expected_pnl_pct: Optional[float] = None
    max_notional: Optional[float] = None
    min_funding_rate_apr: Optional[float] = None


class AutoTradingStatus(BaseModel):
    """Auto trading status / 자동 거래 상태."""

    user_id: int
    is_active: bool
    strategy: Optional[str] = None
    dry_run: Optional[bool] = None


@router.post("/start")
async def start_auto_trading(
    request: Request,
    req: StartAutoTradingRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Start automated trading for current user.
    현재 사용자의 자동 거래 시작.
    """
    # Get opportunity engine from app state
    engine = getattr(request.app.state, "opportunity_engine", None)
    if not engine:
        raise HTTPException(status_code=500, detail="Opportunity engine not available")

    # Get or create auto trader manager
    manager = get_auto_trader_manager(engine)

    # Check if already running
    if manager.get_trader(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="Auto trading already active for this user / 이미 자동 거래가 활성화되어 있습니다",
        )

    # Create strategy based on request
    if req.strategy == "conservative":
        strategy = ConservativeStrategy(
            min_spread_bps=req.min_spread_bps or 50.0,
            min_expected_pnl_pct=req.min_expected_pnl_pct or 0.5,
            max_notional=req.max_notional or 1000.0,
        )
    elif req.strategy == "aggressive":
        strategy = AggressiveStrategy(
            min_spread_bps=req.min_spread_bps or 20.0,
            min_expected_pnl_pct=req.min_expected_pnl_pct or 0.2,
            max_notional=req.max_notional or 5000.0,
        )
    elif req.strategy == "funding_rate":
        strategy = FundingRateStrategy(
            min_funding_rate_apr=req.min_funding_rate_apr or 10.0,
            max_notional=req.max_notional or 10000.0,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy: {req.strategy}. Must be 'conservative', 'aggressive', or 'funding_rate'",
        )

    # Start auto trader
    manager.start_trader(
        user_id=current_user.id,
        strategy=strategy,
        check_interval=req.check_interval,
        dry_run=req.dry_run,
    )

    logger.info(
        "Started auto trading for user %d with strategy %s (dry_run=%s) / "
        "사용자 %d의 자동 거래 시작 (전략: %s, 시뮬레이션: %s)",
        current_user.id,
        req.strategy,
        req.dry_run,
        current_user.id,
        req.strategy,
        req.dry_run,
    )

    return {
        "status": "started",
        "user_id": current_user.id,
        "strategy": req.strategy,
        "dry_run": req.dry_run,
        "message": f"Auto trading started with {req.strategy} strategy / "
        f"{req.strategy} 전략으로 자동 거래 시작됨",
    }


@router.post("/stop")
async def stop_auto_trading(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Stop automated trading for current user.
    현재 사용자의 자동 거래 중지.
    """
    # Get opportunity engine from app state
    engine = getattr(request.app.state, "opportunity_engine", None)
    if not engine:
        raise HTTPException(status_code=500, detail="Opportunity engine not available")

    # Get auto trader manager
    manager = get_auto_trader_manager(engine)

    # Check if running
    if not manager.get_trader(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="Auto trading not active for this user / 자동 거래가 활성화되어 있지 않습니다",
        )

    # Stop auto trader
    await manager.stop_trader(current_user.id)

    logger.info(
        "Stopped auto trading for user %d / 사용자 %d의 자동 거래 중지됨",
        current_user.id,
        current_user.id,
    )

    return {
        "status": "stopped",
        "user_id": current_user.id,
        "message": "Auto trading stopped / 자동 거래 중지됨",
    }


@router.get("/status")
async def get_auto_trading_status(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AutoTradingStatus:
    """
    Get auto trading status for current user.
    현재 사용자의 자동 거래 상태 조회.
    """
    # Get opportunity engine from app state
    engine = getattr(request.app.state, "opportunity_engine", None)
    if not engine:
        raise HTTPException(status_code=500, detail="Opportunity engine not available")

    # Get auto trader manager
    manager = get_auto_trader_manager(engine)

    # Check if running
    trader = manager.get_trader(current_user.id)

    if not trader:
        return AutoTradingStatus(
            user_id=current_user.id,
            is_active=False,
        )

    # Determine strategy type
    strategy_name = "unknown"
    if isinstance(trader.strategy, ConservativeStrategy):
        strategy_name = "conservative"
    elif isinstance(trader.strategy, AggressiveStrategy):
        strategy_name = "aggressive"
    elif isinstance(trader.strategy, FundingRateStrategy):
        strategy_name = "funding_rate"

    return AutoTradingStatus(
        user_id=current_user.id,
        is_active=True,
        strategy=strategy_name,
        dry_run=trader.dry_run,
    )


@router.get("/active-traders")
async def list_active_traders(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    List all active auto traders (admin only).
    모든 활성 자동 거래 목록 (관리자 전용).
    """
    # Check if user is admin
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required / 관리자 권한 필요")

    # Get opportunity engine from app state
    engine = getattr(request.app.state, "opportunity_engine", None)
    if not engine:
        raise HTTPException(status_code=500, detail="Opportunity engine not available")

    # Get auto trader manager
    manager = get_auto_trader_manager(engine)

    active_user_ids = manager.list_active_traders()

    return {
        "active_traders": active_user_ids,
        "count": len(active_user_ids),
    }
