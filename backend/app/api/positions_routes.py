"""Position management API routes / 포지션 관리 API 라우트."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.db_models import Position, PositionStatus, User
from app.services.position_closer import PositionCloser

router = APIRouter(tags=["positions"])


class PositionResponse(BaseModel):
    """Position response model / 포지션 응답 모델."""

    id: int
    opportunity_id: str
    position_type: str
    symbol: str
    status: str
    entry_time: str
    entry_notional: float
    current_pnl_pct: float
    current_pnl_usd: float
    target_profit_pct: float
    stop_loss_pct: float
    entry_legs: list[dict]
    exit_legs: list[dict] | None
    exit_time: str | None
    realized_pnl_pct: float | None
    realized_pnl_usd: float | None
    exit_reason: str | None

    class Config:
        from_attributes = True


class ClosePositionRequest(BaseModel):
    """Request to close a position / 포지션 종료 요청."""

    position_id: int


@router.get("/list")
async def list_positions(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List user's positions.
    사용자의 포지션 목록 조회.

    Args:
        status: Filter by status (open, closing, closed, failed). If None, returns all.

    Returns:
        List of positions with PnL details
    """
    # Build query
    query = select(Position).where(Position.user_id == current_user.id)

    if status:
        try:
            status_enum = PositionStatus(status)
            query = query.where(Position.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of: open, closing, closed, failed",
            )

    # Order by entry time descending (newest first)
    query = query.order_by(Position.entry_time.desc())

    result = await db.execute(query)
    positions = list(result.scalars().all())

    # Convert to response format
    positions_data = []
    for pos in positions:
        positions_data.append(
            {
                "id": pos.id,
                "opportunity_id": pos.opportunity_id,
                "position_type": pos.position_type,
                "symbol": pos.symbol,
                "status": pos.status.value,
                "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
                "entry_notional": pos.entry_notional,
                "current_pnl_pct": pos.current_pnl_pct,
                "current_pnl_usd": pos.current_pnl_usd,
                "target_profit_pct": pos.target_profit_pct,
                "stop_loss_pct": pos.stop_loss_pct,
                "entry_legs": pos.entry_legs or [],
                "exit_legs": pos.exit_legs,
                "exit_time": pos.exit_time.isoformat() if pos.exit_time else None,
                "realized_pnl_pct": pos.realized_pnl_pct,
                "realized_pnl_usd": pos.realized_pnl_usd,
                "exit_reason": pos.exit_reason,
                "last_update": pos.last_update.isoformat() if pos.last_update else None,
            }
        )

    return {
        "count": len(positions_data),
        "positions": positions_data,
    }


@router.get("/{position_id}")
async def get_position(
    position_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get detailed information about a specific position.
    특정 포지션의 상세 정보 조회.
    """
    result = await db.execute(
        select(Position).where(
            Position.id == position_id,
            Position.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found / 포지션을 찾을 수 없습니다")

    return {
        "id": position.id,
        "opportunity_id": position.opportunity_id,
        "position_type": position.position_type,
        "symbol": position.symbol,
        "status": position.status.value,
        "entry_time": position.entry_time.isoformat() if position.entry_time else None,
        "entry_notional": position.entry_notional,
        "current_pnl_pct": position.current_pnl_pct,
        "current_pnl_usd": position.current_pnl_usd,
        "target_profit_pct": position.target_profit_pct,
        "stop_loss_pct": position.stop_loss_pct,
        "entry_legs": position.entry_legs or [],
        "exit_legs": position.exit_legs,
        "exit_time": position.exit_time.isoformat() if position.exit_time else None,
        "realized_pnl_pct": position.realized_pnl_pct,
        "realized_pnl_usd": position.realized_pnl_usd,
        "exit_reason": position.exit_reason,
        "position_metadata": position.position_metadata,
        "last_update": position.last_update.isoformat() if position.last_update else None,
    }


@router.post("/close")
async def close_position(
    request: ClosePositionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Manually close a position.
    수동으로 포지션 종료.

    This will submit exit orders for all legs of the position.
    포지션의 모든 레그에 대해 청산 주문을 제출합니다.
    """
    closer = PositionCloser(db)

    try:
        success = await closer.manual_close_position(request.position_id, current_user.id)

        if success:
            return {
                "status": "success",
                "message": f"Position {request.position_id} closed successfully / 포지션 {request.position_id} 종료 성공",
            }
        else:
            return {
                "status": "failed",
                "message": f"Failed to close position {request.position_id} / 포지션 {request.position_id} 종료 실패",
            }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error closing position: {exc} / 포지션 종료 오류: {exc}",
        )


@router.get("/summary/stats")
async def get_position_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get position statistics summary.
    포지션 통계 요약 조회.

    Returns:
        - Count of open positions
        - Total PnL (open + closed)
        - Win rate
    """
    # Get all positions
    result = await db.execute(select(Position).where(Position.user_id == current_user.id))
    positions = list(result.scalars().all())

    if not positions:
        return {
            "total_positions": 0,
            "open_positions": 0,
            "closed_positions": 0,
            "total_pnl_usd": 0.0,
            "open_pnl_usd": 0.0,
            "realized_pnl_usd": 0.0,
            "win_rate": 0.0,
            "avg_pnl_pct": 0.0,
        }

    open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
    closed_positions = [p for p in positions if p.status == PositionStatus.CLOSED]

    # Calculate stats
    open_pnl_usd = sum(p.current_pnl_usd for p in open_positions if p.current_pnl_usd)
    realized_pnl_usd = sum(p.realized_pnl_usd for p in closed_positions if p.realized_pnl_usd)
    total_pnl_usd = open_pnl_usd + realized_pnl_usd

    # Win rate (only for closed positions)
    winning_positions = [p for p in closed_positions if (p.realized_pnl_usd or 0) > 0]
    win_rate = (len(winning_positions) / len(closed_positions) * 100) if closed_positions else 0.0

    # Average PnL percentage
    all_pnl_pcts = [
        p.current_pnl_pct for p in open_positions if p.current_pnl_pct is not None
    ] + [p.realized_pnl_pct for p in closed_positions if p.realized_pnl_pct is not None]

    avg_pnl_pct = (sum(all_pnl_pcts) / len(all_pnl_pcts)) if all_pnl_pcts else 0.0

    return {
        "total_positions": len(positions),
        "open_positions": len(open_positions),
        "closed_positions": len(closed_positions),
        "total_pnl_usd": total_pnl_usd,
        "open_pnl_usd": open_pnl_usd,
        "realized_pnl_usd": realized_pnl_usd,
        "win_rate": win_rate,
        "avg_pnl_pct": avg_pnl_pct,
    }
