"""Fill monitoring service for tracking order execution / 주문 체결 모니터링 서비스."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import ccxt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.db_models import (
    BalanceSnapshot,
    ExchangeCredential,
    Fill,
    Order,
    OrderStatus,
)
from app.services.exchange_client import ExchangeClientFactory

logger = logging.getLogger(__name__)


class FillMonitor:
    """
    Background service to monitor order fills and update statuses.
    주문 체결을 모니터링하고 상태를 업데이트하는 백그라운드 서비스.
    """

    def __init__(self, poll_interval: int = 5):
        """
        Initialize fill monitor.

        Args:
            poll_interval: Seconds between polling cycles
        """
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the fill monitoring background task / 체결 모니터링 시작."""
        if self._running:
            logger.warning("Fill monitor already running / 체결 모니터 이미 실행 중")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Fill monitor started / 체결 모니터 시작됨")

    async def stop(self) -> None:
        """Stop the fill monitoring background task / 체결 모니터링 중지."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Fill monitor stopped / 체결 모니터 중지됨")

    async def _run_loop(self) -> None:
        """Main monitoring loop / 메인 모니터링 루프."""
        while self._running:
            try:
                async for db in get_db():
                    await self._check_pending_orders(db)
                    break  # Exit after one iteration
            except Exception as exc:
                logger.exception("Error in fill monitor loop: %s / 체결 모니터 루프 오류: %s", exc, exc)

            # Wait before next cycle
            await asyncio.sleep(self.poll_interval)

    async def _check_pending_orders(self, db: AsyncSession) -> None:
        """
        Check all pending/submitted orders for fills.
        모든 대기/제출된 주문의 체결 확인.
        """
        # Find orders that need monitoring (submitted but not filled/cancelled)
        result = await db.execute(
            select(Order)
            .where(
                Order.status.in_([OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]),
                Order.exchange_order_id.isnot(None),
            )
            .order_by(Order.submitted_at.desc())
            .limit(100)  # Process up to 100 orders per cycle
        )
        orders = list(result.scalars().all())

        if not orders:
            logger.debug("No pending orders to monitor / 모니터링할 대기 주문 없음")
            return

        logger.info(
            "Checking %d pending orders / %d개 대기 주문 확인 중",
            len(orders),
            len(orders),
        )

        # Group orders by user and exchange for batch processing
        orders_by_user_exchange: dict[tuple[int, str], list[Order]] = {}
        for order in orders:
            key = (order.user_id, order.exchange)
            if key not in orders_by_user_exchange:
                orders_by_user_exchange[key] = []
            orders_by_user_exchange[key].append(order)

        # Process each user-exchange group
        for (user_id, exchange_name), user_orders in orders_by_user_exchange.items():
            try:
                await self._check_user_exchange_orders(db, user_id, exchange_name, user_orders)
            except Exception as exc:
                logger.exception(
                    "Error checking orders for user %d on %s: %s / "
                    "사용자 %d의 %s 주문 확인 오류: %s",
                    user_id,
                    exchange_name,
                    exc,
                    user_id,
                    exchange_name,
                    exc,
                )

    async def _check_user_exchange_orders(
        self, db: AsyncSession, user_id: int, exchange_name: str, orders: list[Order]
    ) -> None:
        """
        Check orders for a specific user and exchange.
        특정 사용자 및 거래소의 주문 확인.
        """
        # Get user's exchange credential
        result = await db.execute(
            select(ExchangeCredential).where(
                ExchangeCredential.user_id == user_id,
                ExchangeCredential.exchange == exchange_name,
                ExchangeCredential.is_active == True,  # noqa: E712
            )
        )
        credential = result.scalar_one_or_none()

        if not credential:
            logger.warning(
                "No credentials for user %d on %s, skipping / "
                "사용자 %d의 %s 인증 정보 없음, 건너뜀",
                user_id,
                exchange_name,
                user_id,
                exchange_name,
            )
            return

        # Create exchange client
        try:
            exchange_client = ExchangeClientFactory.create_client(credential)
        except Exception as exc:
            logger.error(
                "Failed to create client for %s: %s / %s 클라이언트 생성 실패: %s",
                exchange_name,
                exc,
                exchange_name,
                exc,
            )
            return

        try:
            # Check each order
            for order in orders:
                try:
                    await self._update_order_status(db, order, exchange_client)
                except Exception as exc:
                    logger.error(
                        "Error updating order %d: %s / 주문 %d 업데이트 오류: %s",
                        order.id,
                        exc,
                        order.id,
                        exc,
                    )

            await db.commit()

        finally:
            # Close exchange client
            ExchangeClientFactory.close_client(exchange_client)

    async def _update_order_status(
        self, db: AsyncSession, order: Order, exchange_client: Any
    ) -> None:
        """
        Update order status from exchange.
        거래소에서 주문 상태 업데이트.
        """
        if not order.exchange_order_id:
            logger.warning(
                "Order %d has no exchange_order_id, skipping / "
                "주문 %d에 거래소 주문ID 없음, 건너뜀",
                order.id,
                order.id,
            )
            return

        try:
            # Fetch order status from exchange
            exchange_order = await ExchangeClientFactory.fetch_order_status(
                exchange=exchange_client,
                order_id=order.exchange_order_id,
                symbol=order.symbol,
            )

            # Parse exchange order status
            status = exchange_order.get("status", "").lower()
            filled = float(exchange_order.get("filled", 0))
            remaining = float(exchange_order.get("remaining", 0))
            average_price = exchange_order.get("average")
            fee = exchange_order.get("fee", {})

            # Update order status
            old_status = order.status
            if status == "closed" or (filled > 0 and remaining == 0):
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.utcnow()
            elif filled > 0 and remaining > 0:
                order.status = OrderStatus.PARTIALLY_FILLED
            elif status == "canceled":
                order.status = OrderStatus.CANCELLED
            elif status == "rejected" or status == "expired":
                order.status = OrderStatus.REJECTED

            # Record fill if any quantity was filled
            if filled > 0 and old_status != OrderStatus.FILLED:
                # Check if we already recorded this fill
                existing_fill = await db.execute(
                    select(Fill).where(
                        Fill.order_id == order.id,
                        Fill.exchange_fill_id == exchange_order.get("id"),
                    )
                )
                if not existing_fill.scalar_one_or_none():
                    fill = Fill(
                        order_id=order.id,
                        exchange_fill_id=str(exchange_order.get("id")),
                        quantity=filled,
                        price=average_price or order.price,
                        fee=fee.get("cost", 0.0) if fee else 0.0,
                        fee_currency=fee.get("currency", "USDT") if fee else "USDT",
                        timestamp=datetime.fromtimestamp(
                            exchange_order.get("timestamp", datetime.utcnow().timestamp()) / 1000
                        ),
                    )
                    db.add(fill)

                    logger.info(
                        "Recorded fill for order %d: %s @ %s / "
                        "주문 %d 체결 기록: %s @ %s",
                        order.id,
                        filled,
                        average_price,
                        order.id,
                        filled,
                        average_price,
                    )

            # Log status changes
            if old_status != order.status:
                logger.info(
                    "Order %d status changed: %s -> %s / "
                    "주문 %d 상태 변경: %s -> %s",
                    order.id,
                    old_status.value,
                    order.status.value,
                    order.id,
                    old_status.value,
                    order.status.value,
                )

            # Update order metadata with latest exchange info
            order.metadata.update(
                {
                    "last_checked": datetime.utcnow().isoformat(),
                    "exchange_status": status,
                    "filled": filled,
                    "remaining": remaining,
                }
            )

        except ccxt.OrderNotFound as exc:
            logger.warning(
                "Order %d not found on exchange, marking as failed: %s / "
                "주문 %d를 거래소에서 찾을 수 없음, 실패로 표시: %s",
                order.id,
                exc,
                order.id,
                exc,
            )
            order.status = OrderStatus.FAILED
            order.error_message = "Order not found on exchange"

        except Exception as exc:
            logger.error(
                "Error fetching order %d status: %s / 주문 %d 상태 조회 오류: %s",
                order.id,
                exc,
                order.id,
                exc,
            )


# Global instance
_fill_monitor: FillMonitor | None = None


def get_fill_monitor() -> FillMonitor:
    """Get or create global fill monitor instance / 전역 체결 모니터 인스턴스 가져오기."""
    global _fill_monitor
    if _fill_monitor is None:
        _fill_monitor = FillMonitor(poll_interval=5)
    return _fill_monitor


async def start_fill_monitor() -> None:
    """Start the global fill monitor / 전역 체결 모니터 시작."""
    monitor = get_fill_monitor()
    monitor.start()


async def stop_fill_monitor() -> None:
    """Stop the global fill monitor / 전역 체결 모니터 중지."""
    monitor = get_fill_monitor()
    await monitor.stop()
