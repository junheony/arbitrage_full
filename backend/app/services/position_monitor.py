"""Position monitoring service / 포지션 모니터링 서비스."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.connector_factory import ConnectorFactory
from app.core.config import get_settings
from app.models.db_models import Position, PositionStatus
from app.models.market_data import PerpMarketData

logger = logging.getLogger(__name__)


class PositionMonitor:
    """
    Monitors open positions and calculates real-time PnL.
    오픈 포지션을 모니터링하고 실시간 PnL을 계산합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._settings = get_settings()
        self._connector_factory: ConnectorFactory | None = None

    async def update_all_positions(self) -> dict[str, Any]:
        """
        Update PnL for all open positions.
        모든 오픈 포지션의 PnL 업데이트.

        Returns:
            Summary of position updates
        """
        # Get all open positions
        result = await self.db.execute(
            select(Position).where(Position.status == PositionStatus.OPEN)
        )
        positions = list(result.scalars().all())

        if not positions:
            return {"updated": 0, "closed": 0, "errors": 0}

        logger.info("Updating %d open positions / %d개 오픈 포지션 업데이트 중", len(positions), len(positions))

        # Initialize connector factory
        if not self._connector_factory:
            self._connector_factory = await self._get_connector_factory()

        updated_count = 0
        closed_count = 0
        error_count = 0

        for position in positions:
            try:
                should_close = await self._update_position_pnl(position)

                if should_close:
                    # Mark for closing (actual close order submission happens elsewhere)
                    position.status = PositionStatus.CLOSING
                    logger.info(
                        "Position %s marked for closing (reason: %s) / "
                        "포지션 %s 종료 대기 (사유: %s)",
                        position.id,
                        should_close,
                        position.id,
                        should_close,
                    )
                    closed_count += 1
                else:
                    updated_count += 1

            except Exception as exc:
                logger.error(
                    "Error updating position %s: %s / 포지션 %s 업데이트 오류: %s",
                    position.id,
                    exc,
                    position.id,
                    exc,
                )
                error_count += 1

        await self.db.commit()

        return {
            "updated": updated_count,
            "closed": closed_count,
            "errors": error_count,
        }

    async def _update_position_pnl(self, position: Position) -> str | None:
        """
        Update PnL for a single position.
        단일 포지션의 PnL 업데이트.

        Args:
            position: Position to update

        Returns:
            Close reason if position should be closed, None otherwise
        """
        if position.position_type == "funding_arb":
            return await self._update_funding_arb_pnl(position)
        elif position.position_type == "perp_perp_spread":
            return await self._update_perp_spread_pnl(position)
        elif position.position_type == "spot_perp_basis":
            return await self._update_spot_perp_pnl(position)
        else:
            logger.warning("Unknown position type: %s", position.position_type)
            return None

    async def _update_funding_arb_pnl(self, position: Position) -> str | None:
        """
        Update PnL for funding rate arbitrage position.
        펀딩비 차익거래 포지션의 PnL 업데이트.

        PnL calculation:
        - Accumulated funding payments
        - Current spread cost to exit
        """
        # Get entry legs
        entry_legs = position.entry_legs or []
        if len(entry_legs) < 2:
            logger.warning("Funding arb position %s has insufficient legs", position.id)
            return None

        # For funding arb: long on one exchange, short on another
        # PnL = accumulated funding + exit spread cost

        # Get current market data for both exchanges
        try:
            market_data = await self._fetch_market_data(position.symbol, entry_legs)
            if not market_data:
                return None

            # Calculate current spread
            # Find long and short legs
            long_leg = next((leg for leg in entry_legs if leg["side"] == "buy"), None)
            short_leg = next((leg for leg in entry_legs if leg["side"] == "sell"), None)

            if not long_leg or not short_leg:
                logger.warning("Could not find long/short legs for position %s", position.id)
                return None

            # Get current prices for exit (reverse of entry)
            long_exchange = long_leg["exchange"]
            short_exchange = short_leg["exchange"]

            long_market = next((m for m in market_data if m.exchange == long_exchange), None)
            short_market = next((m for m in market_data if m.exchange == short_exchange), None)

            if not long_market or not short_market:
                logger.warning("Missing market data for position %s", position.id)
                return None

            # Exit prices: sell where we bought, buy where we sold
            exit_sell_price = long_market.bid  # Sell on long exchange
            exit_buy_price = short_market.ask  # Buy on short exchange

            # Entry prices
            entry_buy_price = long_leg["price"]
            entry_sell_price = short_leg["price"]

            # Calculate PnL components
            # 1. Spread cost at entry
            entry_spread = entry_sell_price - entry_buy_price  # Positive is good

            # 2. Spread cost at exit
            exit_spread = exit_sell_price - exit_buy_price  # Positive is good

            # 3. Net spread improvement
            spread_pnl = exit_spread - entry_spread

            # 4. Accumulated funding (simplified - would need actual funding history)
            # For now, use expected funding from metadata
            expected_pnl_pct = position.position_metadata.get("expected_pnl_pct", 0.0)

            # Calculate total PnL percentage
            # PnL = spread improvement as % of entry price
            avg_entry_price = (entry_buy_price + entry_sell_price) / 2
            spread_pnl_pct = (spread_pnl / avg_entry_price) * 100

            # Total PnL (spread + expected funding that accumulates over time)
            # For simplicity, assume linear accumulation
            hours_open = (datetime.utcnow() - position.entry_time).total_seconds() / 3600
            accumulated_funding = expected_pnl_pct * (hours_open / 8)  # Funding every 8H

            current_pnl_pct = spread_pnl_pct + accumulated_funding
            current_pnl_usd = (current_pnl_pct / 100) * position.entry_notional

            # Update position
            position.current_pnl_pct = current_pnl_pct
            position.current_pnl_usd = current_pnl_usd
            position.last_update = datetime.utcnow()

            # Check exit conditions
            if current_pnl_pct >= position.target_profit_pct:
                return "target_profit"
            elif current_pnl_pct <= -position.stop_loss_pct:
                return "stop_loss"
            # Check if spread has converged (close to zero)
            elif abs(exit_spread / avg_entry_price * 100) < 0.05:  # Less than 0.05%
                return "spread_converged"

            return None

        except Exception as exc:
            logger.error("Error calculating funding arb PnL: %s", exc)
            return None

    async def _update_perp_spread_pnl(self, position: Position) -> str | None:
        """
        Update PnL for perpetual-perpetual spread position.
        무기한-무기한 스프레드 포지션의 PnL 업데이트.

        PnL calculation:
        - Entry spread vs current spread
        - Funding rate differentials
        """
        entry_legs = position.entry_legs or []
        if len(entry_legs) < 2:
            logger.warning("Perp spread position %s has insufficient legs", position.id)
            return None

        try:
            market_data = await self._fetch_market_data(position.symbol, entry_legs)
            if not market_data or len(market_data) < 2:
                return None

            # Get the two perpetual exchanges
            exchange1 = entry_legs[0]["exchange"]
            exchange2 = entry_legs[1]["exchange"]

            market1 = next((m for m in market_data if m.exchange == exchange1), None)
            market2 = next((m for m in market_data if m.exchange == exchange2), None)

            if not market1 or not market2:
                return None

            # Entry spread
            entry_price1 = entry_legs[0]["price"]
            entry_price2 = entry_legs[1]["price"]
            entry_spread = abs(entry_price1 - entry_price2)

            # Current spread
            current_price1 = (market1.bid + market1.ask) / 2
            current_price2 = (market2.bid + market2.ask) / 2
            current_spread = abs(current_price1 - current_price2)

            # Spread convergence (good for us)
            spread_change = entry_spread - current_spread
            avg_entry_price = (entry_price1 + entry_price2) / 2
            spread_pnl_pct = (spread_change / avg_entry_price) * 100

            # Update position
            position.current_pnl_pct = spread_pnl_pct
            position.current_pnl_usd = (spread_pnl_pct / 100) * position.entry_notional
            position.last_update = datetime.utcnow()

            # Check exit conditions
            if spread_pnl_pct >= position.target_profit_pct:
                return "target_profit"
            elif spread_pnl_pct <= -position.stop_loss_pct:
                return "stop_loss"
            elif current_spread / avg_entry_price * 100 < 0.05:  # Spread converged
                return "spread_converged"

            return None

        except Exception as exc:
            logger.error("Error calculating perp spread PnL: %s", exc)
            return None

    async def _update_spot_perp_pnl(self, position: Position) -> str | None:
        """
        Update PnL for spot-perpetual basis trade.
        현물-무기한 베이시스 트레이드의 PnL 업데이트.
        """
        # Similar logic to perp spread but with spot + perp
        # For now, return None (not implemented)
        logger.info("Spot-perp PnL calculation not yet implemented for position %s", position.id)
        return None

    async def _fetch_market_data(
        self, symbol: str, entry_legs: list[dict]
    ) -> list[PerpMarketData]:
        """Fetch current market data for position's exchanges."""
        if not self._connector_factory:
            return []

        exchanges = [leg["exchange"] for leg in entry_legs]
        market_data = []

        for exchange in exchanges:
            connector = self._connector_factory.perp_connectors.get(exchange)
            if not connector:
                logger.warning("No connector for exchange %s", exchange)
                continue

            try:
                data = await connector.fetch_perp_market_data()
                # Find data for this symbol
                symbol_data = next((d for d in data if d.symbol == symbol), None)
                if symbol_data:
                    market_data.append(symbol_data)
            except Exception as exc:
                logger.warning("Error fetching data from %s: %s", exchange, exc)

        return market_data

    async def _get_connector_factory(self) -> ConnectorFactory:
        """Initialize connector factory for market data."""
        factory = ConnectorFactory(symbols=self._settings.trading_symbols)
        await factory.initialize()
        return factory

    async def close(self) -> None:
        """Clean up resources."""
        if self._connector_factory:
            await self._connector_factory.close_all()
