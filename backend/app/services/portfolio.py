"""Portfolio management service / 포트폴리오 관리 서비스."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import BalanceSnapshot, ExchangeCredential, Order, OrderStatus, User

logger = logging.getLogger(__name__)


class PortfolioService:
    """Manages user portfolio and balances across exchanges / 거래소별 사용자 포트폴리오 및 잔고 관리."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_balances(self, user_id: int) -> list[BalanceSnapshot]:
        """
        Get latest balances for all exchanges.
        모든 거래소의 최신 잔고 조회.
        """
        result = await self.db.execute(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.user_id == user_id)
            .order_by(BalanceSnapshot.timestamp.desc())
        )
        return list(result.scalars().all())

    async def update_balance(
        self,
        user_id: int,
        exchange: str,
        asset: str,
        free: float,
        locked: float,
        usd_value: float | None = None,
    ) -> BalanceSnapshot:
        """
        Record a new balance snapshot.
        새로운 잔고 스냅샷 기록.
        """
        total = free + locked
        snapshot = BalanceSnapshot(
            user_id=user_id,
            exchange=exchange,
            asset=asset,
            free=free,
            locked=locked,
            total=total,
            usd_value=usd_value,
            timestamp=datetime.utcnow(),
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def calculate_total_exposure(self, user_id: int) -> dict[str, Any]:
        """
        Calculate total portfolio exposure and value.
        총 포트폴리오 익스포저 및 가치 계산.
        """
        balances = await self.get_balances(user_id)

        # Group by asset
        asset_totals: dict[str, float] = {}
        exchange_totals: dict[str, float] = {}
        total_usd_value = 0.0

        for balance in balances:
            # Asset totals
            if balance.asset not in asset_totals:
                asset_totals[balance.asset] = 0.0
            asset_totals[balance.asset] += balance.total

            # Exchange totals (USD)
            if balance.usd_value:
                if balance.exchange not in exchange_totals:
                    exchange_totals[balance.exchange] = 0.0
                exchange_totals[balance.exchange] += balance.usd_value
                total_usd_value += balance.usd_value

        return {
            "total_usd_value": round(total_usd_value, 2),
            "by_asset": {asset: round(total, 8) for asset, total in asset_totals.items()},
            "by_exchange": {exch: round(value, 2) for exch, value in exchange_totals.items()},
            "snapshot_count": len(balances),
        }

    async def get_open_orders(self, user_id: int) -> list[Order]:
        """
        Get all open orders for user.
        사용자의 모든 미체결 주문 조회.
        """
        result = await self.db.execute(
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]),
            )
            .order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())

    async def calculate_pnl(self, user_id: int, start_date: datetime | None = None) -> dict[str, Any]:
        """
        Calculate profit/loss from filled orders.
        체결된 주문으로부터 손익 계산.

        Simple calculation: sum of (sell orders - buy orders) weighted by price.
        간단 계산: (매도 주문 - 매수 주문)의 가격 가중 합계.
        """
        query = select(Order).where(
            Order.user_id == user_id,
            Order.status == OrderStatus.FILLED,
        )
        if start_date:
            query = query.where(Order.filled_at >= start_date)

        result = await self.db.execute(query.order_by(Order.filled_at))
        orders = list(result.scalars().all())

        total_buy_value = 0.0
        total_sell_value = 0.0
        total_fees = 0.0
        trade_count = len(orders)

        for order in orders:
            value = (order.average_fill_price or 0) * order.filled_quantity
            total_fees += order.fee or 0

            if order.side == "buy":
                total_buy_value += value
            elif order.side == "sell":
                total_sell_value += value

        realized_pnl = total_sell_value - total_buy_value - total_fees

        return {
            "realized_pnl_usd": round(realized_pnl, 2),
            "total_buy_value": round(total_buy_value, 2),
            "total_sell_value": round(total_sell_value, 2),
            "total_fees": round(total_fees, 2),
            "trade_count": trade_count,
        }

    async def get_portfolio_summary(self, user_id: int) -> dict[str, Any]:
        """
        Get comprehensive portfolio summary.
        종합 포트폴리오 요약 조회.
        """
        exposure = await self.calculate_total_exposure(user_id)
        open_orders = await self.get_open_orders(user_id)
        pnl = await self.calculate_pnl(user_id)

        return {
            "exposure": exposure,
            "open_orders_count": len(open_orders),
            "pnl": pnl,
            "timestamp": datetime.utcnow().isoformat(),
        }
