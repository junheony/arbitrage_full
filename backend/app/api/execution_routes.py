"""Execution API routes / 실행 API 라우트."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.db_models import User
from app.models.opportunity import Opportunity
from app.services.opportunity_engine import OpportunityEngine
from app.services.order_executor import OrderExecutor

router = APIRouter(tags=["execution"])


class ExecuteOpportunityRequest(BaseModel):
    """Request to execute an opportunity / 기회 실행 요청."""

    opportunity_id: str
    dry_run: bool = False


@router.post("/execute")
async def execute_opportunity(
    request_data: ExecuteOpportunityRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Execute an arbitrage opportunity.
    차익거래 기회 실행.

    Args:
        opportunity_id: ID of opportunity to execute
        dry_run: If true, simulate execution without placing real orders

    Returns:
        Execution result with order details

    프로덕션 주의사항 / Production Warning:
    This endpoint submits REAL ORDERS to exchanges!
    Ensure you:
    - Have sufficient funds on all required exchanges
    - Have tested with dry_run=true first
    - Understand the risks of arbitrage trading
    - Have proper risk limits configured

    이 엔드포인트는 거래소에 실제 주문을 제출합니다!
    다음을 확인하세요:
    - 필요한 모든 거래소에 충분한 자금 보유
    - 먼저 dry_run=true로 테스트
    - 차익거래의 위험성 이해
    - 적절한 리스크 한도 설정
    """
    # Get opportunity from engine
    engine: OpportunityEngine = getattr(request.app.state, "opportunity_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    # Find the opportunity
    opportunities = engine.latest()
    opportunity: Opportunity | None = None
    for opp in opportunities:
        if opp.id == request_data.opportunity_id:
            opportunity = opp
            break

    if not opportunity:
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity {request_data.opportunity_id} not found or expired / "
            f"기회 {request_data.opportunity_id}를 찾을 수 없거나 만료됨",
        )

    # Execute opportunity
    executor = OrderExecutor(db)
    result = await executor.execute_opportunity(
        user_id=current_user.id, opportunity=opportunity, dry_run=request_data.dry_run
    )

    return result


@router.get("/history")
async def get_execution_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get execution history for current user.
    현재 사용자의 실행 히스토리 조회.
    """
    from sqlalchemy import select

    from app.models.db_models import ExecutionLog

    result = await db.execute(
        select(ExecutionLog)
        .where(ExecutionLog.user_id == current_user.id)
        .order_by(ExecutionLog.timestamp.desc())
        .limit(limit)
    )
    logs = list(result.scalars().all())

    return {
        "executions": [
            {
                "opportunity_id": log.opportunity_id,
                "action": log.action,
                "status": log.status,
                "details": log.details,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in logs
        ]
    }
