"""Automated trading service / 자동 거래 서비스."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.db_models import User
from app.models.opportunity import Opportunity
from app.services.opportunity_engine import OpportunityEngine
from app.services.order_executor import OrderExecutor

logger = logging.getLogger(__name__)


class AutoTradingStrategy:
    """Base class for automated trading strategies / 자동 거래 전략 기본 클래스."""

    def should_execute(self, opportunity: Opportunity) -> bool:
        """
        Determine if an opportunity should be executed.
        기회를 실행해야 하는지 결정.

        Args:
            opportunity: Opportunity to evaluate

        Returns:
            True if should execute, False otherwise
        """
        raise NotImplementedError


class ConservativeStrategy(AutoTradingStrategy):
    """
    Conservative strategy: Only execute high-quality opportunities.
    보수적 전략: 고품질 기회만 실행.
    """

    def __init__(
        self,
        min_spread_bps: float = 50.0,
        min_expected_pnl_pct: float = 0.5,
        min_notional: float = 100.0,
    ):
        """
        Initialize conservative strategy.

        Args:
            min_spread_bps: Minimum spread in basis points
            min_expected_pnl_pct: Minimum expected PnL percentage
            min_notional: Minimum notional (too small trades filtered out)
        """
        self.min_spread_bps = min_spread_bps
        self.min_expected_pnl_pct = min_expected_pnl_pct
        self.min_notional = min_notional

    def should_execute(self, opportunity: Opportunity) -> bool:
        """Check if opportunity meets conservative criteria / 보수적 기준 충족 여부 확인."""
        return (
            opportunity.spread_bps >= self.min_spread_bps
            and opportunity.expected_pnl_pct >= self.min_expected_pnl_pct
            and opportunity.notional >= self.min_notional
        )


class AggressiveStrategy(AutoTradingStrategy):
    """
    Aggressive strategy: Execute more opportunities with lower thresholds.
    공격적 전략: 낮은 기준으로 더 많은 기회 실행.
    """

    def __init__(
        self,
        min_spread_bps: float = 20.0,
        min_expected_pnl_pct: float = 0.2,
        min_notional: float = 50.0,
    ):
        """
        Initialize aggressive strategy.

        Args:
            min_spread_bps: Minimum spread in basis points
            min_expected_pnl_pct: Minimum expected PnL percentage
            min_notional: Minimum notional (too small trades filtered out)
        """
        self.min_spread_bps = min_spread_bps
        self.min_expected_pnl_pct = min_expected_pnl_pct
        self.min_notional = min_notional

    def should_execute(self, opportunity: Opportunity) -> bool:
        """Check if opportunity meets aggressive criteria / 공격적 기준 충족 여부 확인."""
        return (
            opportunity.spread_bps >= self.min_spread_bps
            and opportunity.expected_pnl_pct >= self.min_expected_pnl_pct
            and opportunity.notional >= self.min_notional
        )


class FundingRateStrategy(AutoTradingStrategy):
    """
    Strategy focused on funding rate arbitrage.
    펀딩 비율 차익거래 전략.
    """

    def __init__(
        self,
        min_funding_rate_apr: float = 10.0,  # 10% APR
        min_notional: float = 100.0,
    ):
        """
        Initialize funding rate strategy.

        Args:
            min_funding_rate_apr: Minimum funding rate APR %
            min_notional: Minimum notional (too small trades filtered out)
        """
        self.min_funding_rate_apr = min_funding_rate_apr
        self.min_notional = min_notional

    def should_execute(self, opportunity: Opportunity) -> bool:
        """Check if opportunity is funding arbitrage with good rate / 좋은 펀딩 비율 확인."""
        if opportunity.type.value != "funding_arb":
            return False

        # Check metadata for funding rate
        funding_rate_apr = opportunity.metadata.get("funding_rate_apr", 0)
        return (
            funding_rate_apr >= self.min_funding_rate_apr
            and opportunity.notional >= self.min_notional
        )


class AutoTrader:
    """
    Automated trading service that executes opportunities based on strategy.
    전략에 따라 기회를 자동으로 실행하는 서비스.
    """

    def __init__(
        self,
        opportunity_engine: OpportunityEngine,
        user_id: int,
        strategy: AutoTradingStrategy,
        check_interval: int = 10,
        dry_run: bool = True,
    ):
        """
        Initialize auto trader.

        Args:
            opportunity_engine: Source of opportunities
            user_id: User to execute trades for
            strategy: Trading strategy to use
            check_interval: Seconds between opportunity checks
            dry_run: If True, only simulate trades
        """
        self.opportunity_engine = opportunity_engine
        self.user_id = user_id
        self.strategy = strategy
        self.check_interval = check_interval
        self.dry_run = dry_run
        self._running = False
        self._task: asyncio.Task | None = None
        self._executed_opportunity_ids: set[str] = set()

    def start(self) -> None:
        """Start automated trading / 자동 거래 시작."""
        if self._running:
            logger.warning(
                "Auto trader already running for user %d / 사용자 %d의 자동 거래 이미 실행 중",
                self.user_id,
                self.user_id,
            )
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Auto trader started for user %d (dry_run=%s) / 사용자 %d 자동 거래 시작 (시뮬레이션=%s)",
            self.user_id,
            self.dry_run,
            self.user_id,
            self.dry_run,
        )

    async def stop(self) -> None:
        """Stop automated trading / 자동 거래 중지."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(
            "Auto trader stopped for user %d / 사용자 %d 자동 거래 중지됨",
            self.user_id,
            self.user_id,
        )

    async def _run_loop(self) -> None:
        """Main auto trading loop / 메인 자동 거래 루프."""
        while self._running:
            try:
                # Get latest opportunities
                opportunities = self.opportunity_engine.latest()

                # Filter and execute
                for opp in opportunities:
                    # Skip if already executed
                    if opp.id in self._executed_opportunity_ids:
                        continue

                    # Check strategy
                    if self.strategy.should_execute(opp):
                        await self._execute_opportunity(opp)

            except Exception as exc:
                logger.exception(
                    "Error in auto trader loop for user %d: %s / "
                    "사용자 %d 자동 거래 루프 오류: %s",
                    self.user_id,
                    exc,
                    self.user_id,
                    exc,
                )

            # Wait before next check
            await asyncio.sleep(self.check_interval)

    async def _execute_opportunity(self, opportunity: Opportunity) -> None:
        """
        Execute an opportunity.
        기회 실행.
        """
        try:
            async for db in get_db():
                executor = OrderExecutor(db)

                logger.info(
                    "Auto executing opportunity %s for user %d (dry_run=%s): %s / "
                    "사용자 %d의 기회 %s 자동 실행 (시뮬레이션=%s): %s",
                    opportunity.id,
                    self.user_id,
                    self.dry_run,
                    opportunity.description,
                    self.user_id,
                    opportunity.id,
                    self.dry_run,
                    opportunity.description,
                )

                result = await executor.execute_opportunity(
                    user_id=self.user_id,
                    opportunity=opportunity,
                    dry_run=self.dry_run,
                )

                # Mark as executed
                self._executed_opportunity_ids.add(opportunity.id)

                logger.info(
                    "Auto execution result for %s: %s / %s 자동 실행 결과: %s",
                    opportunity.id,
                    result.get("status"),
                    opportunity.id,
                    result.get("status"),
                )

                break  # Exit after one iteration

        except Exception as exc:
            logger.exception(
                "Error executing opportunity %s: %s / 기회 %s 실행 오류: %s",
                opportunity.id,
                exc,
                opportunity.id,
                exc,
            )


class AutoTraderManager:
    """Manages multiple auto traders for different users / 여러 사용자의 자동 거래 관리."""

    def __init__(self, opportunity_engine: OpportunityEngine):
        """
        Initialize auto trader manager.

        Args:
            opportunity_engine: Source of opportunities
        """
        self.opportunity_engine = opportunity_engine
        self._traders: dict[int, AutoTrader] = {}

    def start_trader(
        self,
        user_id: int,
        strategy: AutoTradingStrategy,
        check_interval: int = 10,
        dry_run: bool = True,
    ) -> None:
        """
        Start auto trader for a user.
        사용자의 자동 거래 시작.

        Args:
            user_id: User ID
            strategy: Trading strategy
            check_interval: Check interval in seconds
            dry_run: Simulation mode
        """
        if user_id in self._traders:
            logger.warning(
                "Auto trader already exists for user %d / 사용자 %d의 자동 거래 이미 존재",
                user_id,
                user_id,
            )
            return

        trader = AutoTrader(
            opportunity_engine=self.opportunity_engine,
            user_id=user_id,
            strategy=strategy,
            check_interval=check_interval,
            dry_run=dry_run,
        )
        trader.start()
        self._traders[user_id] = trader

        logger.info(
            "Started auto trader for user %d / 사용자 %d 자동 거래 시작됨",
            user_id,
            user_id,
        )

    async def stop_trader(self, user_id: int) -> None:
        """
        Stop auto trader for a user.
        사용자의 자동 거래 중지.

        Args:
            user_id: User ID
        """
        trader = self._traders.get(user_id)
        if not trader:
            logger.warning(
                "No auto trader found for user %d / 사용자 %d의 자동 거래 없음",
                user_id,
                user_id,
            )
            return

        await trader.stop()
        del self._traders[user_id]

        logger.info(
            "Stopped auto trader for user %d / 사용자 %d 자동 거래 중지됨",
            user_id,
            user_id,
        )

    async def stop_all(self) -> None:
        """Stop all auto traders / 모든 자동 거래 중지."""
        user_ids = list(self._traders.keys())
        for user_id in user_ids:
            await self.stop_trader(user_id)

        logger.info("All auto traders stopped / 모든 자동 거래 중지됨")

    def get_trader(self, user_id: int) -> AutoTrader | None:
        """Get auto trader for a user / 사용자의 자동 거래 가져오기."""
        return self._traders.get(user_id)

    def list_active_traders(self) -> list[int]:
        """List all active trader user IDs / 활성 거래자 사용자 ID 목록."""
        return list(self._traders.keys())


# Global manager instance
_auto_trader_manager: AutoTraderManager | None = None


def get_auto_trader_manager(opportunity_engine: OpportunityEngine) -> AutoTraderManager:
    """Get or create global auto trader manager / 전역 자동 거래 관리자 가져오기."""
    global _auto_trader_manager
    if _auto_trader_manager is None:
        _auto_trader_manager = AutoTraderManager(opportunity_engine)
    return _auto_trader_manager
