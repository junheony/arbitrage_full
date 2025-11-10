from __future__ import annotations

import asyncio
import itertools
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Awaitable, Sequence

from app.connectors.base import MarketConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote, Opportunity, OpportunityLeg, OpportunityType

logger = logging.getLogger(__name__)


class OpportunityEngine:
    """Continuously ingests market data and generates arbitrage opportunities. / 마켓 데이터를 연속으로 수집해 아비트리지 기회를 생성합니다."""

    def __init__(self, connectors: Sequence[MarketConnector]):
        self._connectors = connectors
        self._settings = get_settings()
        self._tether_curve: list[tuple[float, float]] = sorted(
            [tuple(point) for point in self._settings.tether_bot_curve],
            key=lambda item: item[0],
        )
        self._tether_equity = self._settings.tether_total_equity_usd
        self._latest: list[Opportunity] = []
        self._listeners: list[asyncio.Queue[list[Opportunity]]] = []
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def latest(self) -> list[Opportunity]:
        return self._latest

    def subscribe(self) -> "asyncio.Queue[list[Opportunity]]":
        queue: asyncio.Queue[list[Opportunity]] = asyncio.Queue(maxsize=5)
        self._listeners.append(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[list[Opportunity]]") -> None:
        try:
            self._listeners.remove(queue)
        except ValueError:
            pass

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="opportunity-engine")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        self._listeners.clear()
        closers = []
        for connector in self._connectors:
            close_method = getattr(connector, "close", None)
            if close_method:
                closers.append(close_method())
        if closers:
            await asyncio.gather(*closers, return_exceptions=True)

    async def _run_loop(self) -> None:
        logger.info(
            "Starting opportunity engine with %d connectors. / %d개의 커넥터로 기회 엔진을 시작합니다.",
            len(self._connectors),
            len(self._connectors),
        )
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception(
                    "Opportunity engine tick failed; retrying in 1s. / 기회 엔진 틱이 실패하여 1초 후 재시도합니다."
                )
                await asyncio.sleep(1.0)
                continue
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._settings.market_poll_interval,
                )
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        quotes = await self._gather_quotes()
        opportunities = self._generate_spot_cross(quotes)
        opportunities.extend(self._generate_kimchi_premium(quotes))
        if not opportunities:
            opportunities = self._generate_placeholder_opportunities()
        self._latest = opportunities
        for queue in list(self._listeners):
            if queue.full():
                # Drop oldest update to keep queue fresh.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(opportunities)

    async def _gather_quotes(self) -> list[MarketQuote]:
        tasks: list[Awaitable[Sequence[MarketQuote]]] = [
            connector.fetch_quotes() for connector in self._connectors
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for connector, result in zip(self._connectors, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Connector %s failed: %s / 커넥터 %s 오류: %s",
                    connector.name,
                    result,
                    connector.name,
                    result,
                )
                continue
            quotes.extend(result)
        return quotes

    def _generate_spot_cross(self, quotes: Sequence[MarketQuote]) -> list[Opportunity]:
        grouped: dict[tuple[str, str], list[MarketQuote]] = defaultdict(list)
        for quote in quotes:
            grouped[(quote.base_asset, quote.quote_currency)].append(quote)

        opportunities: list[Opportunity] = []
        for (base_asset, quote_currency), symbol_quotes in grouped.items():
            for left, right in itertools.permutations(symbol_quotes, 2):
                spread_bps = self._calculate_spread_bps(left.ask, right.bid)
                if spread_bps <= 0:
                    continue
                if spread_bps > self._settings.max_spread_bps:
                    continue
                expected_pnl_pct = spread_bps / 10000 - self._estimate_fees_pct(left, right)
                if expected_pnl_pct <= 0:
                    continue
                notional = self._settings.simulated_base_notional
                quantity = notional / ((left.ask + right.bid) / 2)
                opportunity = Opportunity(
                    id=str(uuid.uuid4()),
                    type=OpportunityType.SPOT_CROSS,
                    symbol=f"{base_asset}/{quote_currency}",
                    spread_bps=round(spread_bps, 3),
                    expected_pnl_pct=round(expected_pnl_pct * 100, 3),
                    notional=round(notional, 2),
                    timestamp=datetime.utcnow(),
                    description=(
                        f"Buy {base_asset}/{quote_currency} on {left.exchange} @{left.ask} / "
                        f"sell on {right.exchange} @{right.bid}"
                        f" / {left.exchange}에서 {base_asset}/{quote_currency} {left.ask}에 매수, "
                        f"{right.exchange}에서 {right.bid}에 매도"
                    ),
                    legs=[
                        OpportunityLeg(
                            exchange=left.exchange,
                            venue_type=left.venue_type,
                            side="buy",
                            symbol=f"{base_asset}/{quote_currency}",
                            price=left.ask,
                            quantity=round(quantity, 6),
                        ),
                        OpportunityLeg(
                            exchange=right.exchange,
                            venue_type=right.venue_type,
                            side="sell",
                            symbol=f"{base_asset}/{quote_currency}",
                            price=right.bid,
                            quantity=round(quantity, 6),
                        ),
                    ],
                )
                opportunities.append(opportunity)
        return sorted(opportunities, key=lambda opp: opp.expected_pnl_pct, reverse=True)

    def _generate_kimchi_premium(self, quotes: Sequence[MarketQuote]) -> list[Opportunity]:
        fx_quotes = [q for q in quotes if q.base_asset == "USD" and q.quote_currency == "KRW"]
        if not fx_quotes:
            return []
        fx_mid = sum(q.mid_price for q in fx_quotes) / len(fx_quotes)
        if fx_mid <= 0:
            return []
        global_quotes: dict[str, list[MarketQuote]] = defaultdict(list)
        krw_quotes: dict[str, list[MarketQuote]] = defaultdict(list)
        for quote in quotes:
            if quote.quote_currency in {"USDT", "USD"}:
                global_quotes[quote.base_asset].append(quote)
            elif quote.quote_currency == "KRW":
                krw_quotes[quote.base_asset].append(quote)

        opportunities: list[Opportunity] = []
        for asset, krw_list in krw_quotes.items():
            if asset not in global_quotes:
                continue
            krw_quote = min(krw_list, key=lambda q: q.ask)
            for global_quote in global_quotes[asset]:
                global_mid = global_quote.mid_price
                krw_mid_usd = krw_quote.mid_price / fx_mid
                premium_pct = (krw_mid_usd - global_mid) / global_mid
                spread_bps = premium_pct * 10000
                notional = self._settings.simulated_base_notional
                quantity = notional / global_mid if global_mid else 0
                if quantity <= 0:
                    continue
                allocation_fraction = self._evaluate_allocation(premium_pct * 100)
                recommended_notional = allocation_fraction * self._tether_equity
                recommended_action = "sell_krw" if premium_pct >= 0 else "buy_krw"
                legs = self._build_kimchi_legs(
                    asset=asset,
                    global_quote=global_quote,
                    krw_quote=krw_quote,
                    quantity=quantity,
                    premium_pct=premium_pct,
                )
                description = (
                    f"Kimchi premium {premium_pct*100:.2f}% via {krw_quote.exchange}/{global_quote.exchange} "
                    f"/ {krw_quote.exchange}와 {global_quote.exchange} 간 김프 {premium_pct*100:.2f}%"
                )
                opportunity = Opportunity(
                    id=str(uuid.uuid4()),
                    type=OpportunityType.KIMCHI_PREMIUM,
                    symbol=f"{asset}/KRW vs {asset}/{global_quote.quote_currency}",
                    spread_bps=round(spread_bps, 3),
                    expected_pnl_pct=round(premium_pct * 100, 3),
                    notional=round(notional, 2),
                    timestamp=datetime.utcnow(),
                    description=description,
                    legs=legs,
                    metadata={
                        "premium_pct": round(premium_pct * 100, 3),
                        "fx_rate": round(fx_mid, 4),
                        "target_allocation_pct": round(allocation_fraction * 100, 2),
                        "recommended_notional": round(recommended_notional, 2),
                        "recommended_action": recommended_action,
                    },
                )
                opportunities.append(opportunity)
        return sorted(opportunities, key=lambda opp: abs(opp.expected_pnl_pct), reverse=True)

    def _build_kimchi_legs(
        self,
        asset: str,
        global_quote: MarketQuote,
        krw_quote: MarketQuote,
        quantity: float,
        premium_pct: float,
    ) -> list[OpportunityLeg]:
        if premium_pct >= 0:
            global_leg = OpportunityLeg(
                exchange=global_quote.exchange,
                venue_type=global_quote.venue_type,
                side="buy",
                symbol=f"{asset}/{global_quote.quote_currency}",
                price=global_quote.ask,
                quantity=round(quantity, 6),
            )
            krw_leg = OpportunityLeg(
                exchange=krw_quote.exchange,
                venue_type=krw_quote.venue_type,
                side="sell",
                symbol=f"{asset}/KRW",
                price=krw_quote.bid,
                quantity=round(quantity, 6),
            )
        else:
            global_leg = OpportunityLeg(
                exchange=global_quote.exchange,
                venue_type=global_quote.venue_type,
                side="sell",
                symbol=f"{asset}/{global_quote.quote_currency}",
                price=global_quote.bid,
                quantity=round(quantity, 6),
            )
            krw_leg = OpportunityLeg(
                exchange=krw_quote.exchange,
                venue_type=krw_quote.venue_type,
                side="buy",
                symbol=f"{asset}/KRW",
                price=krw_quote.ask,
                quantity=round(quantity, 6),
            )
        return [global_leg, krw_leg]

    def _evaluate_allocation(self, premium_pct: float) -> float:
        if not self._tether_curve:
            return 0.0
        curve = self._tether_curve
        if premium_pct <= curve[0][0]:
            return self._clamp_allocation(curve[0][1])
        for idx in range(1, len(curve)):
            left = curve[idx - 1]
            right = curve[idx]
            if premium_pct <= right[0]:
                span = right[0] - left[0]
                if span == 0:
                    return self._clamp_allocation(right[1])
                weight = (premium_pct - left[0]) / span
                value = left[1] + weight * (right[1] - left[1])
                return self._clamp_allocation(value)
        return self._clamp_allocation(curve[-1][1])

    @staticmethod
    def _clamp_allocation(value: float) -> float:
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return value

    def _generate_placeholder_opportunities(self) -> list[Opportunity]:
        now = datetime.utcnow()
        sample = Opportunity(
            id=str(uuid.uuid4()),
            type=OpportunityType.KIMCHI_PREMIUM,
            symbol="BTC/KRW vs BTC/USDT (sample)",
            spread_bps=65.0,
            expected_pnl_pct=0.55,
            notional=10000.0,
            timestamp=now,
            description=(
                "Sample kimchi premium signal (demo mode). / 샘플 김프 시그널 (데모 모드)."
            ),
            legs=[
                OpportunityLeg(
                    exchange="upbit",
                    venue_type="spot",
                    side="sell",
                    symbol="BTC/KRW",
                    price=94000000,
                    quantity=0.1064,
                ),
                OpportunityLeg(
                    exchange="binance",
                    venue_type="spot",
                    side="buy",
                    symbol="BTC/USDT",
                    price=70000,
                    quantity=0.1064,
                ),
            ],
            metadata={
                "premium_pct": 5.5,
                "fx_rate": 1350.0,
                "target_allocation_pct": 35.0,
                "recommended_notional": 35000.0,
                "recommended_action": "sell_krw",
            },
        )
        spread = Opportunity(
            id=str(uuid.uuid4()),
            type=OpportunityType.SPOT_CROSS,
            symbol="ETH/USDT",
            spread_bps=22.4,
            expected_pnl_pct=0.12,
            notional=5000.0,
            timestamp=now,
            description=(
                "Sample cross-exchange spread between OKX and Binance. / OKX와 Binance 간 샘플 스프레드"
            ),
            legs=[
                OpportunityLeg(
                    exchange="okx",
                    venue_type="spot",
                    side="buy",
                    symbol="ETH/USDT",
                    price=3250,
                    quantity=1.5,
                ),
                OpportunityLeg(
                    exchange="binance",
                    venue_type="spot",
                    side="sell",
                    symbol="ETH/USDT",
                    price=3257.3,
                    quantity=1.5,
                ),
            ],
        )
        return [sample, spread]

    def _calculate_spread_bps(self, ask: float, bid: float) -> float:
        if ask <= 0 or bid <= 0:
            return 0.0
        spread = bid - ask
        if spread <= 0:
            return 0.0
        return (spread / ask) * 10000

    def _estimate_fees_pct(self, left: MarketQuote, right: MarketQuote) -> float:
        fee_pct = self._settings.simulated_fee_bps / 10000
        # Increase fee estimate for perp venues to reflect funding + taker cost.
        if left.venue_type == "perp":
            fee_pct += 0.0005
        if right.venue_type == "perp":
            fee_pct += 0.0005
        return fee_pct
