from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Sequence

import httpx

from app.connectors.perp_base import PerpConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote
from app.models.market_data import FundingRate, PerpMarketData

logger = logging.getLogger(__name__)


class BasePerpConnector(PerpConnector):
    """Fetches Base network perpetual futures data (Synthetix Perps) / Base 네트워크 무기한 선물 데이터 수집 (Synthetix Perps).

    This connector interfaces with Synthetix Perps v3 on Base network.
    Base 네트워크의 Synthetix Perps v3와 인터페이스합니다.
    """

    venue_type = "perp"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "base-synthetix"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        # Using Synthetix v3 API endpoint for Base
        self._client = httpx.AsyncClient(
            base_url="https://perps.synthetix.io/api/base",
            timeout=timeout * 2,  # API can be slower
            headers={"Content-Type": "application/json"},
        )
        self._symbol_map = self._build_symbol_map()

    def _build_symbol_map(self) -> dict[str, str]:
        """Map standard symbols to Synthetix format / 심볼 형식 매핑."""
        symbol_map = {}
        for symbol in self._symbols:
            base, _ = symbol.split("/")
            # Synthetix uses ETH, BTC format
            symbol_map[symbol] = base
        return symbol_map

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Fetch order book quotes for perpetual futures / 무기한 선물 호가 조회."""
        # Note: Synthetix doesn't have traditional order books, uses oracles
        # We'll fetch current prices and simulate spreads
        tasks = [self._fetch_quote(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning("Base perp quote failed for %s: %s", symbol, result)
                continue
            if result:
                quotes.append(result)
        return quotes

    async def fetch_funding_rates(self) -> Sequence[FundingRate]:
        """Fetch current funding rates for all symbols / 모든 심볼의 펀딩비 조회."""
        tasks = [self._fetch_funding_rate(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        funding_rates: list[FundingRate] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning("Base funding rate failed for %s: %s", symbol, result)
                continue
            if result:
                funding_rates.append(result)
        return funding_rates

    async def fetch_perp_market_data(self) -> Sequence[PerpMarketData]:
        """Fetch combined market data (quotes + funding + OI) / 통합 시장 데이터 조회."""
        tasks = [self._fetch_perp_data(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        data: list[PerpMarketData] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning("Base perp data failed for %s: %s", symbol, result)
                continue
            if result:
                data.append(result)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        base_symbol = self._symbol_map.get(symbol, symbol.split("/")[0])
        try:
            # Fetch from Synthetix markets API
            response = await self._client.get(f"/markets/{base_symbol}")
            response.raise_for_status()
            data = response.json()

            oi = float(data.get("openInterest", 0))
            mark_price = float(data.get("markPrice", 0))

            return abs(oi) * mark_price  # OI can be negative in Synthetix
        except Exception as exc:
            logger.warning("Base OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch price quote for a single symbol / 단일 심볼 호가 조회."""
        base, quote = symbol.split("/")
        base_symbol = self._symbol_map.get(symbol, base)

        try:
            response = await self._client.get(f"/markets/{base_symbol}")
            response.raise_for_status()
            data = response.json()

            mark_price = float(data.get("markPrice", 0))
            if mark_price == 0:
                return None

            # Synthetix doesn't have traditional order books
            # Simulate a tight spread (5 bps) around mark price
            spread_bps = 5
            spread_fraction = spread_bps / 10000
            half_spread = mark_price * spread_fraction / 2

            best_bid = mark_price - half_spread
            best_ask = mark_price + half_spread

            return MarketQuote(
                exchange=self.name,
                venue_type="perp",
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                bid=best_bid,
                ask=best_ask,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Base quote error for %s: %s", symbol, exc)
            return None

    async def _fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate for a single symbol / 단일 심볼 펀딩비 조회."""
        base, quote = symbol.split("/")
        base_symbol = self._symbol_map.get(symbol, base)

        try:
            response = await self._client.get(f"/markets/{base_symbol}")
            response.raise_for_status()
            data = response.json()

            # Synthetix funding rate (typically per day)
            funding_rate = float(data.get("fundingRate", 0))
            mark_price = float(data.get("markPrice", 0))
            oi = float(data.get("openInterest", 0))
            oi_usd = abs(oi) * mark_price

            # Convert daily funding rate to 8H
            # Synthetix uses continuous funding, approximate to 8H periods
            funding_rate_8h = funding_rate / 3  # Daily / 3 = 8H

            return FundingRate(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                funding_rate=funding_rate,
                funding_rate_8h=funding_rate_8h,
                next_funding_time=None,  # Continuous funding
                open_interest_usd=oi_usd,
                open_interest_contracts=abs(oi),
                mark_price=mark_price,
                index_price=None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Base funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        base, quote = symbol.split("/")
        base_symbol = self._symbol_map.get(symbol, base)

        try:
            response = await self._client.get(f"/markets/{base_symbol}")
            response.raise_for_status()
            data = response.json()

            mark_price = float(data.get("markPrice", 0))
            if mark_price == 0:
                return None

            funding_rate = float(data.get("fundingRate", 0))
            oi = float(data.get("openInterest", 0))
            oi_usd = abs(oi) * mark_price

            # Simulate spread
            spread_bps = 5
            spread_fraction = spread_bps / 10000
            half_spread = mark_price * spread_fraction / 2

            best_bid = mark_price - half_spread
            best_ask = mark_price + half_spread

            # Convert daily funding to 8H
            funding_rate_8h = funding_rate / 3

            return PerpMarketData(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                bid=best_bid,
                ask=best_ask,
                mark_price=mark_price,
                funding_rate=funding_rate,
                funding_rate_8h=funding_rate_8h,
                next_funding_time=None,
                open_interest_usd=oi_usd,
                open_interest_contracts=abs(oi),
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Base perp data error for %s: %s", symbol, exc)
            return None
