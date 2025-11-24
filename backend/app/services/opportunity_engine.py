from __future__ import annotations

import asyncio
import itertools
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Awaitable, Sequence

from app.connectors.base import MarketConnector
from app.connectors.perp_base import PerpConnector
from app.connectors.deposit_status import get_deposit_checker
from app.core.config import get_settings
from app.models.opportunity import MarketQuote, Opportunity, OpportunityLeg, OpportunityType
from app.models.market_data import FundingRate, PerpMarketData

logger = logging.getLogger(__name__)


class OpportunityEngine:
    """Continuously ingests market data and generates arbitrage opportunities. / 마켓 데이터를 연속으로 수집해 아비트리지 기회를 생성합니다."""

    def __init__(self, connectors: Sequence[MarketConnector]):
        self._connectors = connectors
        # Separate perp connectors for funding rate collection
        self._perp_connectors = [c for c in connectors if isinstance(c, PerpConnector)]
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
        self._deposit_checker = get_deposit_checker()

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
        perp_data = await self._gather_perp_data()

        # Kimchi premium strategy - enabled for hot coin opportunities
        # 김치프리미엄 전략 - 급등 코인 기회 포착용 활성화
        opportunities = self._generate_kimchi_premium(quotes, perp_data)

        # Disabled other spot strategies - require asset ownership or margin/loan capability
        # 기타 현물 전략 비활성화 - 자산 보유 또는 대출/마진 기능 필요
        # opportunities.extend(self._generate_spot_cross(quotes))
        # opportunities.extend(self._generate_spot_perp_basis(quotes, perp_data))

        # Focus on perpetual futures strategies - executable with cash/margin only
        # 무기한 선물 전략에 집중 - 현금/마진만으로 실행 가능
        opportunities.extend(self._generate_funding_arb(perp_data))
        opportunities.extend(self._generate_perp_perp_spread(perp_data))

        # Filter out opportunities with blocked deposits/withdrawals
        # 입출금이 막힌 기회는 필터링
        filtered_opportunities = await self._filter_by_deposit_status(opportunities)

        # No placeholder opportunities - only show real trading signals
        self._latest = filtered_opportunities
        for queue in list(self._listeners):
            if queue.full():
                # Drop oldest update to keep queue fresh.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(filtered_opportunities)

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

    async def _gather_perp_data(self) -> list[PerpMarketData]:
        """Gather perpetual market data from perp connectors / 무기한 선물 커넥터에서 시장 데이터 수집."""
        if not self._perp_connectors:
            return []

        tasks: list[Awaitable[Sequence[PerpMarketData]]] = [
            connector.fetch_perp_market_data() for connector in self._perp_connectors
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        perp_data: list[PerpMarketData] = []
        for connector, result in zip(self._perp_connectors, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Perp connector %s failed: %s / 무기한 선물 커넥터 %s 오류: %s",
                    connector.name,
                    result,
                    connector.name,
                    result,
                )
                continue
            perp_data.extend(result)
        return perp_data

    def _generate_spot_cross(self, quotes: Sequence[MarketQuote]) -> list[Opportunity]:
        # Filter out only spot quotes, exclude perp and fx
        spot_quotes = [q for q in quotes if q.venue_type == "spot"]

        grouped: dict[tuple[str, str], list[MarketQuote]] = defaultdict(list)
        for quote in spot_quotes:
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

    def _generate_kimchi_premium(self, quotes: Sequence[MarketQuote], perp_data: Sequence[PerpMarketData]) -> list[Opportunity]:
        fx_quotes = [q for q in quotes if q.base_asset == "USD" and q.quote_currency == "KRW"]
        if not fx_quotes:
            return []
        fx_mid = sum(q.mid_price for q in fx_quotes) / len(fx_quotes)
        if fx_mid <= 0:
            return []

        # Build funding rate lookup for perp quotes
        # 무기한 선물 펀딩비 조회 테이블 구축
        funding_lookup: dict[tuple[str, str], PerpMarketData] = {}
        for perp in perp_data:
            key = (perp.exchange.lower(), perp.base_asset.upper())
            funding_lookup[key] = perp

        # Accept both spot and perp quotes for international side (to handle new listings)
        # Korean side must be spot only
        # 국제 거래소는 현물/선물 모두 허용 (신규 상장 대응), 한국 거래소는 현물만
        tradeable_quotes = [q for q in quotes if q.venue_type in {"spot", "perp"}]

        global_quotes: dict[str, list[MarketQuote]] = defaultdict(list)
        krw_quotes: dict[str, list[MarketQuote]] = defaultdict(list)
        for quote in tradeable_quotes:
            if quote.quote_currency in {"USDT", "USD"}:
                global_quotes[quote.base_asset].append(quote)
            elif quote.quote_currency == "KRW":
                # Korean exchanges must be spot only
                if quote.venue_type == "spot":
                    krw_quotes[quote.base_asset].append(quote)

        # First pass: calculate all premiums to get average
        all_premiums: list[float] = []
        for asset, krw_list in krw_quotes.items():
            if asset not in global_quotes:
                continue
            krw_quote = min(krw_list, key=lambda q: q.ask)
            for global_quote in global_quotes[asset]:
                global_mid = global_quote.mid_price
                krw_mid_usd = krw_quote.mid_price / fx_mid
                premium_pct = (krw_mid_usd - global_mid) / global_mid * 100
                all_premiums.append(premium_pct)

        # Calculate average premium
        avg_premium = sum(all_premiums) / len(all_premiums) if all_premiums else 0.0

        # Second pass: filter by deviation from average
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

                # Check deviation from average
                deviation = abs((premium_pct * 100) - avg_premium)
                if deviation < self._settings.kimchi_deviation_threshold_pct:
                    continue

                allocation_fraction = self._evaluate_allocation(premium_pct * 100)
                allocation_pct = allocation_fraction * 100

                # Filter out low-allocation opportunities (noise)
                if allocation_pct < self._settings.min_kimchi_allocation_pct:
                    continue

                recommended_notional = allocation_fraction * self._tether_equity
                recommended_action = "sell_krw" if premium_pct >= 0 else "buy_krw"
                legs = self._build_kimchi_legs(
                    asset=asset,
                    global_quote=global_quote,
                    krw_quote=krw_quote,
                    quantity=quantity,
                    premium_pct=premium_pct,
                )
                # Add venue type labels to clarify spot vs perp
                krw_venue_label = f"({krw_quote.venue_type})"
                global_venue_label = f"({global_quote.venue_type})"

                # Use different description based on whether it's pure spot or mixed
                if krw_quote.venue_type == "spot" and global_quote.venue_type == "spot":
                    strategy_name = "Kimchi premium"
                    strategy_name_kr = "김치프리미엄"
                else:
                    strategy_name = "Price diff"
                    strategy_name_kr = "가격차"

                # Look up funding rate if global side is perp
                # 국제 거래소 측이 선물이면 펀딩비 조회
                funding_rate_8h = None
                funding_rate_24h = None
                if global_quote.venue_type == "perp":
                    perp_key = (global_quote.exchange.lower(), asset.upper())
                    if perp_key in funding_lookup:
                        perp_info = funding_lookup[perp_key]
                        funding_rate_8h = perp_info.funding_rate_8h
                        # Calculate 24H funding (3 fundings per day)
                        funding_rate_24h = funding_rate_8h * 3

                description = (
                    f"{strategy_name} {premium_pct*100:.2f}% (avg {avg_premium:.2f}%) - "
                    f"{krw_quote.exchange}{krw_venue_label} vs {global_quote.exchange}{global_venue_label} / "
                    f"{krw_quote.exchange}{krw_venue_label}와 {global_quote.exchange}{global_venue_label} 간 {strategy_name_kr} {premium_pct*100:.2f}% (평균 {avg_premium:.2f}%)"
                )

                metadata = {
                    "premium_pct": round(premium_pct * 100, 3),
                    "avg_premium_pct": round(avg_premium, 3),
                    "deviation_from_avg": round(deviation, 3),
                    "fx_rate": round(fx_mid, 4),
                    "target_allocation_pct": round(allocation_fraction * 100, 2),
                    "recommended_notional": round(recommended_notional, 2),
                    "recommended_action": recommended_action,
                }
                # Add funding rate info if available
                if funding_rate_8h is not None:
                    metadata["funding_rate_8h_pct"] = round(funding_rate_8h * 100, 4)
                if funding_rate_24h is not None:
                    metadata["funding_rate_24h_pct"] = round(funding_rate_24h * 100, 4)

                opportunity = Opportunity(
                    id=str(uuid.uuid4()),
                    type=OpportunityType.KIMCHI_PREMIUM,
                    symbol=f"{asset}/KRW{krw_venue_label} vs {asset}/{global_quote.quote_currency}{global_venue_label}",
                    spread_bps=round(spread_bps, 3),
                    expected_pnl_pct=round(premium_pct * 100, 3),
                    notional=round(notional, 2),
                    timestamp=datetime.utcnow(),
                    description=description,
                    legs=legs,
                    metadata=metadata,
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

    def _generate_funding_arb(self, perp_data: Sequence[PerpMarketData]) -> list[Opportunity]:
        """Generate funding rate arbitrage opportunities / 펀딩비 차익거래 기회 생성.

        Delta-neutral strategy: long on exchange with negative funding, short on exchange with positive funding.
        델타 중립 전략: 음수 펀딩비 거래소에서 롱, 양수 펀딩비 거래소에서 숏.
        """
        # Group by base asset
        grouped: dict[str, list[PerpMarketData]] = defaultdict(list)
        for data in perp_data:
            grouped[data.base_asset].append(data)

        opportunities: list[Opportunity] = []
        min_oi_usd = 100_000  # Minimum OI to avoid low liquidity / 낮은 유동성 회피를 위한 최소 OI

        for asset, asset_perps in grouped.items():
            # Filter by minimum OI / 최소 OI로 필터링
            valid_perps = [p for p in asset_perps if p.open_interest_usd >= min_oi_usd]
            if len(valid_perps) < 2:
                continue

            # Find pairs with opposite funding rates
            for i, perp1 in enumerate(valid_perps):
                for perp2 in valid_perps[i + 1 :]:
                    # Calculate funding rate differential (8H normalized)
                    funding_diff_8h = perp1.funding_rate_8h - perp2.funding_rate_8h

                    # We want significant funding differential (at least 0.01% = 1 bps per 8H)
                    if abs(funding_diff_8h) < 0.0001:
                        continue

                    # Check spread is reasonable (total spread should be < 20 bps)
                    total_spread_bps = perp1.spread_bps + perp2.spread_bps
                    if total_spread_bps > 20:
                        continue

                    # Long on lower funding, short on higher funding
                    if funding_diff_8h > 0:
                        long_perp = perp2
                        short_perp = perp1
                    else:
                        long_perp = perp1
                        short_perp = perp2
                        funding_diff_8h = -funding_diff_8h

                    # Expected PnL: funding differential - spread costs
                    # 예상 수익: 펀딩비 차이 - 스프레드 비용
                    funding_pnl_pct = funding_diff_8h * 100  # Convert to percentage
                    spread_cost_pct = total_spread_bps / 100  # Convert bps to percentage
                    expected_pnl_pct = funding_pnl_pct - spread_cost_pct

                    # Only consider if expected PnL exceeds minimum threshold after fees
                    # 수수료 차감 후 최소 수익률 기준 충족하는 경우만
                    if expected_pnl_pct <= (self._settings.min_profit_pct / 100):
                        continue

                    notional = self._settings.simulated_base_notional
                    quantity = notional / long_perp.mark_price

                    opportunity = Opportunity(
                        id=str(uuid.uuid4()),
                        type=OpportunityType.FUNDING_ARB,
                        symbol=f"{asset}/USDT:USDT",
                        spread_bps=round(funding_diff_8h * 10000, 3),
                        expected_pnl_pct=round(expected_pnl_pct, 3),
                        notional=round(notional, 2),
                        timestamp=datetime.utcnow(),
                        description=(
                            f"Funding arb: Long {long_perp.exchange} @{long_perp.funding_rate_8h*100:.4f}%/8H, "
                            f"Short {short_perp.exchange} @{short_perp.funding_rate_8h*100:.4f}%/8H / "
                            f"펀딩 차익: {long_perp.exchange} 롱 {long_perp.funding_rate_8h*100:.4f}%/8H, "
                            f"{short_perp.exchange} 숏 {short_perp.funding_rate_8h*100:.4f}%/8H"
                        ),
                        legs=[
                            OpportunityLeg(
                                exchange=long_perp.exchange,
                                venue_type="perp",
                                side="buy",
                                symbol=f"{asset}/USDT:USDT",
                                price=long_perp.ask,
                                quantity=round(quantity, 6),
                            ),
                            OpportunityLeg(
                                exchange=short_perp.exchange,
                                venue_type="perp",
                                side="sell",
                                symbol=f"{asset}/USDT:USDT",
                                price=short_perp.bid,
                                quantity=round(quantity, 6),
                            ),
                        ],
                        metadata={
                            "funding_diff_8h_pct": round(funding_diff_8h * 100, 4),
                            "long_exchange": long_perp.exchange,
                            "long_funding_8h_pct": round(long_perp.funding_rate_8h * 100, 4),
                            "long_oi_usd": round(long_perp.open_interest_usd, 2),
                            "short_exchange": short_perp.exchange,
                            "short_funding_8h_pct": round(short_perp.funding_rate_8h * 100, 4),
                            "short_oi_usd": round(short_perp.open_interest_usd, 2),
                            "total_spread_bps": round(total_spread_bps, 2),
                        },
                    )
                    opportunities.append(opportunity)

        return sorted(opportunities, key=lambda opp: opp.expected_pnl_pct, reverse=True)

    def _generate_spot_perp_basis(
        self, quotes: Sequence[MarketQuote], perp_data: Sequence[PerpMarketData]
    ) -> list[Opportunity]:
        """Generate spot vs perpetual basis arbitrage opportunities / 현물 vs 무기한 선물 베이시스 차익거래 기회 생성."""
        opportunities: list[Opportunity] = []
        min_oi_usd = 100_000

        # Group spot quotes by asset
        spot_quotes: dict[str, list[MarketQuote]] = defaultdict(list)
        for quote in quotes:
            if quote.venue_type == "spot" and quote.quote_currency in {"USDT", "USD"}:
                spot_quotes[quote.base_asset].append(quote)

        # Group perp data by asset
        perp_by_asset: dict[str, list[PerpMarketData]] = defaultdict(list)
        for perp in perp_data:
            if perp.open_interest_usd >= min_oi_usd:
                perp_by_asset[perp.base_asset].append(perp)

        for asset in spot_quotes.keys():
            if asset not in perp_by_asset:
                continue

            for spot in spot_quotes[asset]:
                for perp in perp_by_asset[asset]:
                    # Calculate basis (perp - spot)
                    basis = perp.mark_price - spot.mid_price
                    basis_bps = (basis / spot.mid_price) * 10000 if spot.mid_price > 0 else 0

                    # Check if basis is significant (at least 10 bps)
                    if abs(basis_bps) < 10:
                        continue

                    # Positive basis: perp > spot, buy spot, sell perp
                    # Negative basis: spot > perp, sell spot, buy perp
                    if basis_bps > 0:
                        buy_venue = spot
                        sell_venue = perp
                        spread = perp.bid - spot.ask
                    else:
                        buy_venue = perp
                        sell_venue = spot
                        spread = spot.bid - perp.ask
                        basis_bps = -basis_bps

                    spread_bps = (spread / spot.mid_price) * 10000 if spot.mid_price > 0 else 0
                    if spread_bps <= 0:
                        continue

                    expected_pnl_pct = (spread_bps / 100) - self._estimate_fees_pct(spot, perp)  # type: ignore
                    if expected_pnl_pct <= 0:
                        continue

                    notional = self._settings.simulated_base_notional
                    quantity = notional / spot.mid_price

                    opportunity = Opportunity(
                        id=str(uuid.uuid4()),
                        type=OpportunityType.SPOT_VS_PERP,
                        symbol=f"{asset}/USDT",
                        spread_bps=round(spread_bps, 3),
                        expected_pnl_pct=round(expected_pnl_pct * 100, 3),
                        notional=round(notional, 2),
                        timestamp=datetime.utcnow(),
                        description=(
                            f"Basis arb: {asset} spot@{spot.mid_price:.2f} vs perp@{perp.mark_price:.2f} "
                            f"({basis_bps:.1f} bps) / 베이시스 차익: {asset} 현물@{spot.mid_price:.2f} vs "
                            f"선물@{perp.mark_price:.2f} ({basis_bps:.1f} bps)"
                        ),
                        legs=[
                            OpportunityLeg(
                                exchange=buy_venue.exchange,
                                venue_type=buy_venue.venue_type,
                                side="buy",
                                symbol=f"{asset}/USDT",
                                price=buy_venue.ask if hasattr(buy_venue, "ask") else buy_venue.mark_price,  # type: ignore
                                quantity=round(quantity, 6),
                            ),
                            OpportunityLeg(
                                exchange=sell_venue.exchange,
                                venue_type=sell_venue.venue_type,
                                side="sell",
                                symbol=f"{asset}/USDT",
                                price=sell_venue.bid if hasattr(sell_venue, "bid") else sell_venue.mark_price,  # type: ignore
                                quantity=round(quantity, 6),
                            ),
                        ],
                        metadata={
                            "basis_bps": round(basis_bps, 2),
                            "spot_exchange": spot.exchange,
                            "perp_exchange": perp.exchange,
                            "perp_funding_8h_pct": round(perp.funding_rate_8h * 100, 4),
                            "perp_oi_usd": round(perp.open_interest_usd, 2),
                        },
                    )
                    opportunities.append(opportunity)

        return sorted(opportunities, key=lambda opp: opp.expected_pnl_pct, reverse=True)

    def _generate_perp_perp_spread(self, perp_data: Sequence[PerpMarketData]) -> list[Opportunity]:
        """Generate perpetual vs perpetual spread arbitrage opportunities / 선물 vs 선물 스프레드 차익거래 기회 생성."""
        opportunities: list[Opportunity] = []
        min_oi_usd = 100_000

        # Group by base asset
        grouped: dict[str, list[PerpMarketData]] = defaultdict(list)
        for perp in perp_data:
            if perp.open_interest_usd >= min_oi_usd:
                grouped[perp.base_asset].append(perp)

        for asset, asset_perps in grouped.items():
            if len(asset_perps) < 2:
                continue

            for i, perp1 in enumerate(asset_perps):
                for perp2 in asset_perps[i + 1 :]:
                    # Calculate price spread
                    spread = perp2.bid - perp1.ask
                    spread_bps = (spread / perp1.mark_price) * 10000 if perp1.mark_price > 0 else 0

                    if spread_bps <= 0:
                        continue
                    if spread_bps > self._settings.max_spread_bps:
                        continue

                    # Consider funding rate differential
                    funding_diff = abs(perp1.funding_rate_8h - perp2.funding_rate_8h)

                    expected_pnl_pct = (spread_bps / 100) - 0.001  # Approximate fees for perp trading
                    # Only consider if expected PnL exceeds minimum threshold after fees
                    # 수수료 차감 후 최소 수익률 기준 충족하는 경우만
                    if expected_pnl_pct <= (self._settings.min_profit_pct / 100):
                        continue

                    notional = self._settings.simulated_base_notional
                    quantity = notional / perp1.mark_price

                    opportunity = Opportunity(
                        id=str(uuid.uuid4()),
                        type=OpportunityType.PERP_PERP_SPREAD,
                        symbol=f"{asset}/USDT:USDT",
                        spread_bps=round(spread_bps, 3),
                        expected_pnl_pct=round(expected_pnl_pct * 100, 3),
                        notional=round(notional, 2),
                        timestamp=datetime.utcnow(),
                        description=(
                            f"Perp spread: Buy {perp1.exchange} @{self._format_price(perp1.ask)}, "
                            f"Sell {perp2.exchange} @{self._format_price(perp2.bid)} / "
                            f"선물 스프레드: {perp1.exchange} 매수 @{self._format_price(perp1.ask)}, "
                            f"{perp2.exchange} 매도 @{self._format_price(perp2.bid)}"
                        ),
                        legs=[
                            OpportunityLeg(
                                exchange=perp1.exchange,
                                venue_type="perp",
                                side="buy",
                                symbol=f"{asset}/USDT:USDT",
                                price=perp1.ask,
                                quantity=round(quantity, 6),
                            ),
                            OpportunityLeg(
                                exchange=perp2.exchange,
                                venue_type="perp",
                                side="sell",
                                symbol=f"{asset}/USDT:USDT",
                                price=perp2.bid,
                                quantity=round(quantity, 6),
                            ),
                        ],
                        metadata={
                            "funding_diff_8h_pct": round(funding_diff * 100, 4),
                            "perp1_funding_8h_pct": round(perp1.funding_rate_8h * 100, 4),
                            "perp1_oi_usd": round(perp1.open_interest_usd, 2),
                            "perp2_funding_8h_pct": round(perp2.funding_rate_8h * 100, 4),
                            "perp2_oi_usd": round(perp2.open_interest_usd, 2),
                        },
                    )
                    opportunities.append(opportunity)

        return sorted(opportunities, key=lambda opp: opp.expected_pnl_pct, reverse=True)

    async def _filter_by_deposit_status(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        """Filter out opportunities where deposits/withdrawals are blocked / 입출금이 막힌 기회 필터링."""
        filtered = []
        for opp in opportunities:
            # Check all legs to see if deposits/withdrawals are enabled
            is_tradeable = True
            for leg in opp.legs:
                exchange = leg.exchange
                base_asset = leg.symbol.split("/")[0] if "/" in leg.symbol else leg.symbol.split(":")[0]

                # Check deposit/withdrawal status
                tradeable = await self._deposit_checker.is_trading_enabled(exchange, base_asset)
                if not tradeable:
                    logger.debug(
                        f"Filtering {opp.type} opportunity {opp.symbol}: "
                        f"{base_asset} deposits/withdrawals disabled on {exchange}"
                    )
                    is_tradeable = False
                    break

            if is_tradeable:
                filtered.append(opp)

        if len(opportunities) > len(filtered):
            logger.info(
                f"Filtered {len(opportunities) - len(filtered)} opportunities due to deposit/withdrawal restrictions / "
                f"입출금 제한으로 {len(opportunities) - len(filtered)}개 기회 필터링됨"
            )

        return filtered

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

    def _format_price(self, price: float) -> str:
        """Smart price formatting based on magnitude / 가격 크기에 따른 스마트 포맷팅."""
        if price >= 1000:
            return f"{price:.2f}"
        elif price >= 1:
            return f"{price:.5f}".rstrip('0').rstrip('.')
        elif price >= 0.01:
            return f"{price:.6f}".rstrip('0').rstrip('.')
        else:
            return f"{price:.8f}".rstrip('0').rstrip('.')
