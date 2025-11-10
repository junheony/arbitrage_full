"""Order execution service / 주문 실행 서비스."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    ExchangeCredential,
    ExecutionLog,
    Order,
    OrderStatus,
    OpportunityHistory,
    RiskLimit,
    User,
)
from app.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


class RiskCheckFailed(Exception):
    """Raised when risk checks fail / 리스크 체크 실패 시 발생."""

    pass


class OrderExecutor:
    """
    Executes arbitrage opportunities with risk management.
    리스크 관리와 함께 차익거래 기회를 실행합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_opportunity(
        self, user_id: int, opportunity: Opportunity, dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Execute an arbitrage opportunity.
        차익거래 기회 실행.

        Args:
            user_id: User ID
            opportunity: Opportunity to execute
            dry_run: If True, only simulate execution

        Returns:
            Execution result with order IDs
        """
        # Log execution attempt
        await self._log_execution(user_id, opportunity.id, "execute_start", "pending", {})

        try:
            # Step 1: Risk checks / 리스크 체크
            await self._perform_risk_checks(user_id, opportunity)

            # Step 2: Verify exchange credentials / 거래소 인증 정보 확인
            credentials = await self._get_credentials(user_id, opportunity)

            # Step 3: Save opportunity to history / 기회 히스토리 저장
            await self._save_opportunity_history(opportunity, was_executed=not dry_run)

            if dry_run:
                await self._log_execution(
                    user_id, opportunity.id, "execute_dry_run", "success", {"dry_run": True}
                )
                return {
                    "status": "dry_run",
                    "opportunity_id": opportunity.id,
                    "message": "Dry run successful - no actual orders placed / 시뮬레이션 성공 - 실제 주문 미실행",
                    "orders": [],
                }

            # Step 4: Submit orders to exchanges / 거래소에 주문 제출
            orders = await self._submit_orders(user_id, opportunity, credentials)

            # Step 5: Monitor fills (async task in production) / 체결 모니터링
            # TODO: Launch background task for fill monitoring

            await self._log_execution(
                user_id,
                opportunity.id,
                "execute_complete",
                "success",
                {"order_count": len(orders)},
            )

            return {
                "status": "success",
                "opportunity_id": opportunity.id,
                "message": f"{len(orders)} orders submitted / {len(orders)}개 주문 제출됨",
                "orders": [
                    {
                        "id": o.id,
                        "exchange": o.exchange,
                        "symbol": o.symbol,
                        "side": o.side,
                        "quantity": o.quantity,
                        "status": o.status.value,
                    }
                    for o in orders
                ],
            }

        except RiskCheckFailed as exc:
            await self._log_execution(
                user_id, opportunity.id, "risk_check", "failure", {"error": str(exc)}
            )
            return {
                "status": "risk_check_failed",
                "opportunity_id": opportunity.id,
                "message": f"Risk check failed: {exc} / 리스크 체크 실패: {exc}",
                "orders": [],
            }

        except Exception as exc:
            logger.exception("Order execution failed: %s", exc)
            await self._log_execution(
                user_id, opportunity.id, "execute_error", "failure", {"error": str(exc)}
            )
            return {
                "status": "error",
                "opportunity_id": opportunity.id,
                "message": f"Execution error: {exc} / 실행 오류: {exc}",
                "orders": [],
            }

    async def _perform_risk_checks(self, user_id: int, opportunity: Opportunity) -> None:
        """
        Perform risk limit checks before execution.
        실행 전 리스크 한도 체크.
        """
        # Get user's risk limits
        result = await self.db.execute(select(RiskLimit).where(RiskLimit.user_id == user_id))
        limits = result.scalar_one_or_none()

        if not limits:
            raise RiskCheckFailed("No risk limits configured / 리스크 한도 미설정")

        # Check max position size
        if opportunity.notional > limits.max_position_size_usd:
            raise RiskCheckFailed(
                f"Position size ${opportunity.notional} exceeds limit ${limits.max_position_size_usd} / "
                f"포지션 크기 ${opportunity.notional}이 한도 ${limits.max_position_size_usd}을 초과"
            )

        # Check max open orders
        open_orders_result = await self.db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED]),
            )
        )
        open_orders = list(open_orders_result.scalars().all())

        if len(open_orders) >= limits.max_open_orders:
            raise RiskCheckFailed(
                f"Too many open orders ({len(open_orders)}) / 미체결 주문이 너무 많음 ({len(open_orders)})"
            )

        # TODO: Check daily loss limit
        # TODO: Check margin requirements

        logger.info("Risk checks passed for user %d / 사용자 %d 리스크 체크 통과", user_id, user_id)

    async def _get_credentials(
        self, user_id: int, opportunity: Opportunity
    ) -> dict[str, ExchangeCredential]:
        """
        Get exchange credentials for opportunity legs.
        기회 레그에 필요한 거래소 인증 정보 가져오기.
        """
        required_exchanges = set(leg.exchange for leg in opportunity.legs)

        credentials = {}
        for exchange in required_exchanges:
            result = await self.db.execute(
                select(ExchangeCredential).where(
                    ExchangeCredential.user_id == user_id,
                    ExchangeCredential.exchange == exchange,
                    ExchangeCredential.is_active == True,  # noqa: E712
                )
            )
            cred = result.scalar_one_or_none()

            if not cred:
                raise RiskCheckFailed(
                    f"No credentials for exchange {exchange} / 거래소 {exchange} 인증 정보 없음"
                )

            credentials[exchange] = cred

        return credentials

    async def _submit_orders(
        self,
        user_id: int,
        opportunity: Opportunity,
        credentials: dict[str, ExchangeCredential],
    ) -> list[Order]:
        """
        Submit orders to exchanges.
        거래소에 주문 제출.

        NOTE: This is a STUB implementation for demonstration.
        In production, this would:
        1. Decrypt API keys
        2. Create exchange clients (CCXT, native SDKs)
        3. Submit actual orders
        4. Handle exchange-specific errors
        5. Return exchange order IDs

        주의: 이것은 데모용 스텁 구현입니다.
        프로덕션에서는:
        1. API 키 복호화
        2. 거래소 클라이언트 생성 (CCXT, 네이티브 SDK)
        3. 실제 주문 제출
        4. 거래소별 오류 처리
        5. 거래소 주문 ID 반환
        """
        orders = []

        for leg in opportunity.legs:
            # Create order record
            order = Order(
                user_id=user_id,
                opportunity_id=opportunity.id,
                exchange=leg.exchange,
                symbol=leg.symbol,
                side=leg.side,
                order_type="market",  # Default to market orders for arbitrage
                quantity=leg.quantity,
                price=leg.price,  # Reference price
                status=OrderStatus.PENDING,
                metadata={
                    "venue_type": leg.venue_type,
                    "opportunity_type": opportunity.type.value,
                },
            )

            self.db.add(order)
            await self.db.flush()  # Get order ID

            # TODO: IMPLEMENT ACTUAL EXCHANGE SUBMISSION HERE
            # For now, mark as submitted
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.utcnow()
            order.exchange_order_id = f"STUB_{order.id}"  # Placeholder

            logger.info(
                "Order %d submitted to %s: %s %s %s @ %s / 주문 %d이 %s에 제출됨: %s %s %s @ %s",
                order.id,
                leg.exchange,
                leg.side,
                leg.quantity,
                leg.symbol,
                leg.price,
                order.id,
                leg.exchange,
                leg.side,
                leg.quantity,
                leg.symbol,
                leg.price,
            )

            orders.append(order)

        await self.db.commit()
        return orders

    async def _save_opportunity_history(
        self, opportunity: Opportunity, was_executed: bool
    ) -> None:
        """Save opportunity to historical records / 기회 히스토리 저장."""
        history = OpportunityHistory(
            opportunity_id=opportunity.id,
            type=opportunity.type.value,
            symbol=opportunity.symbol,
            spread_bps=opportunity.spread_bps,
            expected_pnl_pct=opportunity.expected_pnl_pct,
            notional=opportunity.notional,
            description=opportunity.description,
            legs=[leg.model_dump() for leg in opportunity.legs],
            metadata=opportunity.metadata,
            was_executed=was_executed,
            timestamp=opportunity.timestamp,
        )
        self.db.add(history)
        await self.db.commit()

    async def _log_execution(
        self, user_id: int, opportunity_id: str, action: str, status: str, details: dict[str, Any]
    ) -> None:
        """Log execution attempt / 실행 시도 로그."""
        log = ExecutionLog(
            user_id=user_id,
            opportunity_id=opportunity_id,
            action=action,
            status=status,
            details=details,
            timestamp=datetime.utcnow(),
        )
        self.db.add(log)
        await self.db.commit()
