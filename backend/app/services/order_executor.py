"""Order execution service / 주문 실행 서비스."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import ccxt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    ExchangeCredential,
    ExecutionLog,
    Fill,
    Order,
    OrderStatus,
    OpportunityHistory,
    Position,
    PositionStatus,
    RiskLimit,
    User,
)
from app.models.opportunity import Opportunity
from app.services.exchange_client import ExchangeClientFactory
from app.core.config import get_settings

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
            scale = await self._perform_risk_checks(user_id, opportunity)

            # Step 2: Verify exchange credentials / 거래소 인증 정보 확인
            credentials = await self._get_credentials(user_id, opportunity)

            # Step 3: Save opportunity to history / 기회 히스토리 저장
            await self._save_opportunity_history(opportunity, was_executed=not dry_run)

            if dry_run:
                await self._log_execution(
                    user_id, opportunity.id, "execute_dry_run", "success", {
                        "dry_run": True,
                        "scale": scale,
                        "scaled_notional": opportunity.notional * scale,
                    }
                )
                return {
                    "status": "dry_run",
                    "opportunity_id": opportunity.id,
                    "message": f"Dry run successful (scale={scale:.3f}) / 시뮬레이션 성공 (비율={scale:.3f})",
                    "scale": scale,
                    "scaled_notional": opportunity.notional * scale,
                    "orders": [],
                }

            # Step 4: Submit orders to exchanges / 거래소에 주문 제출
            orders = await self._submit_orders(user_id, opportunity, credentials, scale)

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

    async def _perform_risk_checks(self, user_id: int, opportunity: Opportunity) -> float:
        """
        Perform risk limit checks before execution.
        실행 전 리스크 한도 체크.

        Returns:
            scale: Scale factor to apply to notional (1.0 = no scaling, 0.5 = half size, etc.)
        """
        # Get user's risk limits
        result = await self.db.execute(select(RiskLimit).where(RiskLimit.user_id == user_id))
        limits = result.scalar_one_or_none()

        if not limits:
            raise RiskCheckFailed("No risk limits configured / 리스크 한도 미설정")

        # Calculate scale factor based on max position size
        # If opportunity is larger than limit, scale it down
        scale = 1.0
        if opportunity.notional > limits.max_position_size_usd:
            scale = limits.max_position_size_usd / opportunity.notional
            logger.info(
                "Scaling down opportunity from $%.2f to $%.2f (scale=%.3f) / "
                "기회 크기 축소: $%.2f → $%.2f (비율=%.3f)",
                opportunity.notional,
                opportunity.notional * scale,
                scale,
                opportunity.notional,
                opportunity.notional * scale,
                scale,
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

        # Check daily loss limit
        await self._check_daily_loss_limit(user_id, limits)

        # Check leverage for perpetual futures
        if any(leg.venue_type == "perp" for leg in opportunity.legs):
            effective_notional = opportunity.notional * scale * limits.max_leverage
            if effective_notional > limits.max_position_size_usd:
                # Further scale down for leveraged positions
                scale = limits.max_position_size_usd / (opportunity.notional * limits.max_leverage)
                logger.info(
                    "Further scaling down for leverage (new scale=%.3f) / "
                    "레버리지 고려 추가 축소 (새 비율=%.3f)",
                    scale,
                    scale,
                )

        logger.info(
            "Risk checks passed for user %d (final scale=%.3f) / 사용자 %d 리스크 체크 통과 (최종 비율=%.3f)",
            user_id,
            scale,
            user_id,
            scale,
        )
        return scale

    async def _check_daily_loss_limit(self, user_id: int, limits: RiskLimit) -> None:
        """
        Check if daily loss limit has been exceeded.
        일일 손실 한도 초과 여부 확인.
        """
        # Calculate start of current day (UTC)
        from datetime import date, timedelta

        today_start = datetime.combine(date.today(), datetime.min.time())

        # Get all filled orders from today
        result = await self.db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.status == OrderStatus.FILLED,
                Order.filled_at >= today_start,
            )
        )
        todays_orders = list(result.scalars().all())

        if not todays_orders:
            return  # No orders today, no loss

        # Calculate total PnL from today's orders
        # For arbitrage: compare expected vs actual execution prices
        total_loss = 0.0

        for order in todays_orders:
            # Get fills for this order
            fills_result = await self.db.execute(
                select(Fill).where(Fill.order_id == order.id)
            )
            fills = list(fills_result.scalars().all())

            if not fills:
                continue

            # Calculate average fill price
            total_qty = sum(f.quantity for f in fills)
            total_value = sum(f.quantity * f.price for f in fills)
            avg_fill_price = total_value / total_qty if total_qty > 0 else 0

            # Calculate slippage loss (difference from expected price)
            if order.price:  # Expected price
                expected_value = order.quantity * order.price
                actual_value = total_value
                slippage = expected_value - actual_value if order.side == "buy" else actual_value - expected_value

                if slippage < 0:  # Loss
                    total_loss += abs(slippage)

            # Add fees
            total_fees = sum(f.fee for f in fills)
            total_loss += total_fees

        # Check against limit
        if total_loss > limits.max_daily_loss_usd:
            raise RiskCheckFailed(
                f"Daily loss ${total_loss:.2f} exceeds limit ${limits.max_daily_loss_usd} / "
                f"일일 손실 ${total_loss:.2f}이 한도 ${limits.max_daily_loss_usd}를 초과"
            )

        logger.info(
            "Daily loss check passed: $%s / $%s / 일일 손실 체크 통과: $%s / $%s",
            total_loss,
            limits.max_daily_loss_usd,
            total_loss,
            limits.max_daily_loss_usd,
        )

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
        scale: float = 1.0,
    ) -> list[Order]:
        """
        Submit orders to exchanges.
        거래소에 주문 제출.

        This implementation:
        1. Decrypts API keys
        2. Creates exchange clients (CCXT)
        3. Submits actual orders
        4. Handles exchange-specific errors
        5. Returns exchange order IDs

        구현 내용:
        1. API 키 복호화
        2. 거래소 클라이언트 생성 (CCXT)
        3. 실제 주문 제출
        4. 거래소별 오류 처리
        5. 거래소 주문 ID 반환
        """
        orders = []
        exchange_clients = {}

        try:
            # Create exchange clients for each required exchange
            for exchange_name, credential in credentials.items():
                try:
                    client = ExchangeClientFactory.create_client(credential)
                    exchange_clients[exchange_name] = client
                except Exception as exc:
                    logger.error(
                        "Failed to create client for %s: %s / %s 클라이언트 생성 실패: %s",
                        exchange_name,
                        exc,
                        exchange_name,
                        exc,
                    )
                    raise

            # Submit orders for each leg
            for leg in opportunity.legs:
                # Apply scale to quantity
                scaled_quantity = leg.quantity * scale

                # Create order record
                order = Order(
                    user_id=user_id,
                    opportunity_id=opportunity.id,
                    exchange=leg.exchange,
                    symbol=leg.symbol,
                    side=leg.side,
                    order_type="market",  # Default to market orders for arbitrage
                    quantity=scaled_quantity,
                    price=leg.price,  # Reference price
                    status=OrderStatus.PENDING,
                    order_metadata={
                        "venue_type": leg.venue_type,
                        "opportunity_type": opportunity.type.value,
                        "scale": scale,
                        "original_quantity": leg.quantity,
                    },
                )

                self.db.add(order)
                await self.db.flush()  # Get order ID

                # Get exchange client
                exchange_client = exchange_clients.get(leg.exchange)
                if not exchange_client:
                    logger.error(
                        "No client found for exchange %s / 거래소 %s 클라이언트 없음",
                        leg.exchange,
                        leg.exchange,
                    )
                    order.status = OrderStatus.FAILED
                    order.error_message = f"No client for exchange {leg.exchange}"
                    continue

                # Submit order to exchange
                try:
                    # Check if this is a perpetual futures order
                    if leg.venue_type == "perp":
                        # Get user's risk limits for leverage
                        limits_result = await self.db.execute(
                            select(RiskLimit).where(RiskLimit.user_id == user_id)
                        )
                        limits = limits_result.scalar_one_or_none()
                        leverage = int(limits.max_leverage) if limits else 1

                        exchange_order = await ExchangeClientFactory.submit_perp_order(
                            exchange=exchange_client,
                            symbol=leg.symbol,
                            side=leg.side,
                            quantity=scaled_quantity,
                            leverage=leverage,
                            order_type="market",
                        )
                    else:
                        # Spot order
                        exchange_order = await ExchangeClientFactory.submit_order(
                            exchange=exchange_client,
                            symbol=leg.symbol,
                            side=leg.side,
                            quantity=scaled_quantity,
                            order_type="market",
                        )

                    # Update order with exchange response
                    order.status = OrderStatus.SUBMITTED
                    order.submitted_at = datetime.utcnow()
                    order.exchange_order_id = str(exchange_order.get("id"))
                    if order.order_metadata is None:
                        order.order_metadata = {}
                    order.order_metadata.update(
                        {
                            "exchange_response": {
                                "status": exchange_order.get("status"),
                                "timestamp": exchange_order.get("timestamp"),
                                "info": exchange_order.get("info", {}),
                            }
                        }
                    )

                    logger.info(
                        "Order %d submitted to %s: %s %s %s @ %s (scaled qty=%.6f, exchange_order_id=%s) / "
                        "주문 %d이 %s에 제출됨: %s %s %s @ %s (조정수량=%.6f, 거래소주문ID=%s)",
                        order.id,
                        leg.exchange,
                        leg.side,
                        scaled_quantity,
                        leg.symbol,
                        leg.price,
                        scaled_quantity,
                        order.exchange_order_id,
                        order.id,
                        leg.exchange,
                        leg.side,
                        scaled_quantity,
                        leg.symbol,
                        leg.price,
                        scaled_quantity,
                        order.exchange_order_id,
                    )

                except ccxt.InsufficientFunds as exc:
                    logger.error(
                        "Insufficient funds for order %d on %s: %s / "
                        "주문 %d에 대한 %s 잔액 부족: %s",
                        order.id,
                        leg.exchange,
                        exc,
                        order.id,
                        leg.exchange,
                        exc,
                    )
                    order.status = OrderStatus.REJECTED
                    order.error_message = f"Insufficient funds: {exc}"

                except ccxt.InvalidOrder as exc:
                    logger.error(
                        "Invalid order %d for %s: %s / 주문 %d (%s) 유효하지 않음: %s",
                        order.id,
                        leg.exchange,
                        exc,
                        order.id,
                        leg.exchange,
                        exc,
                    )
                    order.status = OrderStatus.REJECTED
                    order.error_message = f"Invalid order: {exc}"

                except ccxt.ExchangeError as exc:
                    logger.error(
                        "Exchange error for order %d on %s: %s / "
                        "주문 %d (%s) 거래소 오류: %s",
                        order.id,
                        leg.exchange,
                        exc,
                        order.id,
                        leg.exchange,
                        exc,
                    )
                    order.status = OrderStatus.FAILED
                    order.error_message = f"Exchange error: {exc}"

                except Exception as exc:
                    logger.exception(
                        "Unexpected error submitting order %d to %s: %s / "
                        "주문 %d (%s) 제출 중 예상치 못한 오류: %s",
                        order.id,
                        leg.exchange,
                        exc,
                        order.id,
                        leg.exchange,
                        exc,
                    )
                    order.status = OrderStatus.FAILED
                    order.error_message = f"Unexpected error: {exc}"

                orders.append(order)

            # Create position record for perpetual strategies that need tracking
            # 포지션 추적이 필요한 무기한 선물 전략에 대해 포지션 레코드 생성
            await self._create_position_if_needed(user_id, opportunity, orders, scale)

            await self.db.commit()
            return orders

        finally:
            # Close all exchange clients
            for exchange_name, client in exchange_clients.items():
                try:
                    ExchangeClientFactory.close_client(client)
                except Exception as exc:
                    logger.warning(
                        "Error closing client for %s: %s / %s 클라이언트 종료 오류: %s",
                        exchange_name,
                        exc,
                        exchange_name,
                        exc,
                    )

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
            opportunity_metadata=opportunity.metadata,
            was_executed=was_executed,
            timestamp=opportunity.timestamp,
        )
        self.db.add(history)
        await self.db.commit()

    async def _create_position_if_needed(
        self, user_id: int, opportunity: Opportunity, orders: list[Order], scale: float = 1.0
    ) -> None:
        """
        Create position record for strategies requiring position tracking.
        포지션 추적이 필요한 전략에 대해 포지션 레코드 생성.

        Only creates positions for:
        - funding_arb (funding rate arbitrage)
        - perp_perp_spread (perpetual-perpetual spread)
        - spot_perp_basis (spot-perpetual basis trade)
        """
        # Only create positions for perpetual-based strategies
        if opportunity.type.value not in ["funding_arb", "perp_perp_spread", "spot_perp_basis"]:
            return

        # Check if at least one order was successfully submitted
        successful_orders = [o for o in orders if o.status == OrderStatus.SUBMITTED]
        if not successful_orders:
            logger.warning(
                "No successful orders for opportunity %s, not creating position / "
                "기회 %s에 성공한 주문 없음, 포지션 미생성",
                opportunity.id,
                opportunity.id,
            )
            return

        # Get config settings
        settings = get_settings()

        # Build entry legs from orders
        entry_legs = [
            {
                "exchange": order.exchange,
                "venue_type": (order.order_metadata or {}).get("venue_type", "unknown"),
                "side": order.side,
                "price": order.price or 0.0,
                "quantity": order.quantity,
                "order_id": order.id,
                "exchange_order_id": order.exchange_order_id,
            }
            for order in successful_orders
        ]

        # Create position record
        scaled_notional = opportunity.notional * scale
        position = Position(
            user_id=user_id,
            opportunity_id=opportunity.id,
            position_type=opportunity.type.value,
            symbol=opportunity.symbol,
            status=PositionStatus.OPEN,
            entry_time=datetime.utcnow(),
            entry_legs=entry_legs,
            entry_notional=scaled_notional,
            target_profit_pct=settings.default_target_profit_pct,
            stop_loss_pct=settings.default_stop_loss_pct,
            current_pnl_pct=0.0,
            current_pnl_usd=0.0,
            position_metadata={
                "spread_bps": opportunity.spread_bps,
                "expected_pnl_pct": opportunity.expected_pnl_pct,
                "description": opportunity.description,
                "scale": scale,
                "original_notional": opportunity.notional,
            },
        )

        self.db.add(position)
        logger.info(
            "Created position %s for opportunity %s (type=%s, symbol=%s, scaled_notional=$%.2f, scale=%.3f) / "
            "기회 %s에 대한 포지션 생성 (유형=%s, 심볼=%s, 조정명목금액=$%.2f, 비율=%.3f)",
            opportunity.id,
            opportunity.id,
            opportunity.type.value,
            opportunity.symbol,
            scaled_notional,
            scale,
            opportunity.id,
            opportunity.type.value,
            opportunity.symbol,
            scaled_notional,
            scale,
        )

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
