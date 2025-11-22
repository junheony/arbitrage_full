"""Position closing service / 포지션 종료 서비스."""
from __future__ import annotations

import logging
from datetime import datetime

import ccxt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    ExchangeCredential,
    Order,
    OrderStatus,
    Position,
    PositionStatus,
    RiskLimit,
)
from app.services.exchange_client import ExchangeClientFactory

logger = logging.getLogger(__name__)


class PositionCloser:
    """
    Closes positions by submitting exit orders.
    포지션 종료 주문을 제출합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def close_positions_marked_for_closing(self) -> dict[str, int]:
        """
        Close all positions marked with CLOSING status.
        CLOSING 상태로 표시된 모든 포지션 종료.

        Returns:
            Summary of close attempts
        """
        # Get all positions marked for closing
        result = await self.db.execute(
            select(Position).where(Position.status == PositionStatus.CLOSING)
        )
        positions = list(result.scalars().all())

        if not positions:
            return {"success": 0, "failed": 0}

        logger.info("Closing %d positions / %d개 포지션 종료 중", len(positions), len(positions))

        success_count = 0
        failed_count = 0

        for position in positions:
            try:
                success = await self._close_position(position)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as exc:
                logger.error(
                    "Error closing position %s: %s / 포지션 %s 종료 오류: %s",
                    position.id,
                    exc,
                    position.id,
                    exc,
                )
                failed_count += 1

        await self.db.commit()

        return {"success": success_count, "failed": failed_count}

    async def _close_position(self, position: Position) -> bool:
        """
        Close a single position by submitting exit orders.
        단일 포지션 종료 주문 제출.

        Args:
            position: Position to close

        Returns:
            True if successful, False otherwise
        """
        entry_legs = position.entry_legs or []
        if not entry_legs:
            logger.warning("Position %s has no entry legs", position.id)
            position.status = PositionStatus.FAILED
            return False

        # Get user credentials for exchanges
        user_id = position.user_id
        exchanges = set(leg["exchange"] for leg in entry_legs)

        credentials = {}
        for exchange in exchanges:
            result = await self.db.execute(
                select(ExchangeCredential).where(
                    ExchangeCredential.user_id == user_id,
                    ExchangeCredential.exchange == exchange,
                    ExchangeCredential.is_active == True,  # noqa: E712
                )
            )
            cred = result.scalar_one_or_none()

            if not cred:
                logger.error(
                    "No credentials for exchange %s (position %s) / "
                    "거래소 %s 인증 정보 없음 (포지션 %s)",
                    exchange,
                    position.id,
                    exchange,
                    position.id,
                )
                position.status = PositionStatus.FAILED
                return False

            credentials[exchange] = cred

        # Submit exit orders (reverse of entry)
        exit_orders = []
        exchange_clients = {}

        try:
            # Create exchange clients
            for exchange_name, credential in credentials.items():
                try:
                    client = ExchangeClientFactory.create_client(credential)
                    exchange_clients[exchange_name] = client
                except Exception as exc:
                    logger.error("Failed to create client for %s: %s", exchange_name, exc)
                    raise

            # Submit exit orders (reverse each leg)
            for leg in entry_legs:
                # Reverse the side
                exit_side = "sell" if leg["side"] == "buy" else "buy"

                # Create exit order record
                exit_order = Order(
                    user_id=user_id,
                    opportunity_id=position.opportunity_id,
                    exchange=leg["exchange"],
                    symbol=position.symbol,
                    side=exit_side,
                    order_type="market",
                    quantity=leg["quantity"],
                    price=None,  # Market order
                    status=OrderStatus.PENDING,
                    order_metadata={
                        "position_id": position.id,
                        "exit_order": True,
                        "venue_type": leg.get("venue_type", "unknown"),
                    },
                )

                self.db.add(exit_order)
                await self.db.flush()  # Get order ID

                # Get exchange client
                exchange_client = exchange_clients.get(leg["exchange"])
                if not exchange_client:
                    exit_order.status = OrderStatus.FAILED
                    exit_order.error_message = f"No client for exchange {leg['exchange']}"
                    exit_orders.append(exit_order)
                    continue

                # Submit order to exchange
                try:
                    if leg.get("venue_type") == "perp":
                        # Perpetual futures exit
                        limits_result = await self.db.execute(
                            select(RiskLimit).where(RiskLimit.user_id == user_id)
                        )
                        limits = limits_result.scalar_one_or_none()
                        leverage = int(limits.max_leverage) if limits else 1

                        exchange_order = await ExchangeClientFactory.submit_perp_order(
                            exchange=exchange_client,
                            symbol=position.symbol,
                            side=exit_side,
                            quantity=leg["quantity"],
                            leverage=leverage,
                            order_type="market",
                        )
                    else:
                        # Spot exit
                        exchange_order = await ExchangeClientFactory.submit_order(
                            exchange=exchange_client,
                            symbol=position.symbol,
                            side=exit_side,
                            quantity=leg["quantity"],
                            order_type="market",
                        )

                    # Update order with exchange response
                    exit_order.status = OrderStatus.SUBMITTED
                    exit_order.submitted_at = datetime.utcnow()
                    exit_order.exchange_order_id = str(exchange_order.get("id"))
                    exit_order.order_metadata.update(
                        {
                            "exchange_response": {
                                "status": exchange_order.get("status"),
                                "timestamp": exchange_order.get("timestamp"),
                            }
                        }
                    )

                    logger.info(
                        "Exit order %d submitted for position %s: %s %s %s / "
                        "포지션 %s에 대한 청산 주문 %d 제출: %s %s %s",
                        exit_order.id,
                        position.id,
                        exit_side,
                        leg["quantity"],
                        position.symbol,
                        position.id,
                        exit_order.id,
                        exit_side,
                        leg["quantity"],
                        position.symbol,
                    )

                except ccxt.InsufficientFunds as exc:
                    logger.error("Insufficient funds for exit order: %s", exc)
                    exit_order.status = OrderStatus.REJECTED
                    exit_order.error_message = f"Insufficient funds: {exc}"

                except ccxt.ExchangeError as exc:
                    logger.error("Exchange error for exit order: %s", exc)
                    exit_order.status = OrderStatus.FAILED
                    exit_order.error_message = f"Exchange error: {exc}"

                except Exception as exc:
                    logger.exception("Unexpected error submitting exit order: %s", exc)
                    exit_order.status = OrderStatus.FAILED
                    exit_order.error_message = f"Unexpected error: {exc}"

                exit_orders.append(exit_order)

            # Check if all exit orders were submitted successfully
            successful_exits = [o for o in exit_orders if o.status == OrderStatus.SUBMITTED]

            if len(successful_exits) == len(entry_legs):
                # All exit orders submitted successfully
                position.status = PositionStatus.CLOSED
                position.exit_time = datetime.utcnow()
                position.exit_legs = [
                    {
                        "exchange": order.exchange,
                        "side": order.side,
                        "quantity": order.quantity,
                        "order_id": order.id,
                        "exchange_order_id": order.exchange_order_id,
                    }
                    for order in successful_exits
                ]
                # PnL will be updated once fills come in
                position.realized_pnl_pct = position.current_pnl_pct
                position.realized_pnl_usd = position.current_pnl_usd

                logger.info(
                    "Position %s closed successfully (PnL: %.2f%% / $%.2f) / "
                    "포지션 %s 종료 성공 (수익: %.2f%% / $%.2f)",
                    position.id,
                    position.realized_pnl_pct or 0,
                    position.realized_pnl_usd or 0,
                    position.id,
                    position.realized_pnl_pct or 0,
                    position.realized_pnl_usd or 0,
                )
                return True
            else:
                # Some exit orders failed
                position.status = PositionStatus.FAILED
                logger.error(
                    "Position %s failed to close: %d/%d exit orders successful / "
                    "포지션 %s 종료 실패: %d/%d 청산 주문 성공",
                    position.id,
                    len(successful_exits),
                    len(entry_legs),
                    position.id,
                    len(successful_exits),
                    len(entry_legs),
                )
                return False

        finally:
            # Close all exchange clients
            for exchange_name, client in exchange_clients.items():
                try:
                    ExchangeClientFactory.close_client(client)
                except Exception as exc:
                    logger.warning("Error closing client for %s: %s", exchange_name, exc)

    async def manual_close_position(self, position_id: int, user_id: int) -> bool:
        """
        Manually close a position.
        수동으로 포지션 종료.

        Args:
            position_id: Position ID to close
            user_id: User ID (for verification)

        Returns:
            True if successful, False otherwise
        """
        # Get position
        result = await self.db.execute(
            select(Position).where(
                Position.id == position_id,
                Position.user_id == user_id,
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            logger.error("Position %d not found for user %d", position_id, user_id)
            return False

        if position.status == PositionStatus.CLOSED:
            logger.warning("Position %d already closed", position_id)
            return True

        # Mark for closing and close immediately
        position.status = PositionStatus.CLOSING
        position.exit_reason = "manual"
        await self.db.flush()

        success = await self._close_position(position)
        await self.db.commit()

        return success
