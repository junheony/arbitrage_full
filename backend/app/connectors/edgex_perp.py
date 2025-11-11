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


class EdgeXPerpConnector(PerpConnector):
    """Fetches EdgeX Exchange perpetual futures data / EdgeX 거래소 무기한 선물 데이터 수집."""

    venue_type = "perp"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "edgex"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://pro.edgex.exchange",  # API base URL
            timeout=timeout * 2,
            headers={"Content-Type": "application/json"},
        )
        self._symbol_map = self._build_symbol_map()

    def _build_symbol_map(self) -> dict[str, str]:
        """Map standard symbols to EdgeX format / 심볼 형식 매핑."""
        symbol_map = {}
        for symbol in self._symbols:
            base, quote = symbol.split("/")
            # EdgeX uses format like BTC_USDT
            symbol_map[symbol] = f"{base}_{quote}"
        return symbol_map

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Fetch order book quotes for perpetual futures / 무기한 선물 호가 조회."""
        tasks = [self._fetch_quote(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning("EdgeX quote failed for %s: %s", symbol, result)
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
                logger.warning("EdgeX funding rate failed for %s: %s", symbol, result)
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
                logger.warning("EdgeX perp data failed for %s: %s", symbol, result)
                continue
            if result:
                data.append(result)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        edgex_symbol = self._symbol_map.get(symbol, symbol)
        try:
            # EdgeX API endpoint for open interest
            response = await self._client.get(f"/api/v1/public/market/{edgex_symbol}/openInterest")
            response.raise_for_status()
            data = response.json()
            oi = float(data.get("openInterest", 0))
            return oi
        except Exception as exc:
            logger.warning("EdgeX OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch order book for a single symbol / 단일 심볼 호가 조회."""
        base, quote = symbol.split("/")
        edgex_symbol = self._symbol_map.get(symbol, f"{base}_{quote}")

        try:
            response = await self._client.get(f"/api/v1/public/orderbook/{edgex_symbol}", params={"limit": 5})
            response.raise_for_status()
            data = response.json()

            bids = data.get("bids", [])
            asks = data.get("asks", [])
            if not bids or not asks:
                return None

            # EdgeX format: [price, size]
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])

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
            logger.warning("EdgeX quote error for %s: %s", symbol, exc)
            return None

    async def _fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate for a single symbol / 단일 심볼 펀딩비 조회."""
        base, quote = symbol.split("/")
        edgex_symbol = self._symbol_map.get(symbol, f"{base}_{quote}")

        try:
            response = await self._client.get(f"/api/v1/public/market/{edgex_symbol}/funding")
            response.raise_for_status()
            data = response.json()

            funding_rate = float(data.get("fundingRate", 0))
            mark_price = float(data.get("markPrice", 0))
            next_funding_ts = int(data.get("nextFundingTime", 0))

            # EdgeX funding happens every 8 hours
            funding_rate_8h = funding_rate

            # Get open interest
            oi_usd = await self.fetch_open_interest(symbol)

            return FundingRate(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                funding_rate=funding_rate,
                funding_rate_8h=funding_rate_8h,
                next_funding_time=datetime.fromtimestamp(next_funding_ts / 1000) if next_funding_ts else None,
                open_interest_usd=oi_usd,
                mark_price=mark_price,
                index_price=None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("EdgeX funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        base, quote = symbol.split("/")
        edgex_symbol = self._symbol_map.get(symbol, f"{base}_{quote}")

        try:
            # Fetch all data in parallel
            book_task = self._client.get(f"/api/v1/public/orderbook/{edgex_symbol}", params={"limit": 5})
            funding_task = self._client.get(f"/api/v1/public/market/{edgex_symbol}/funding")
            oi_task = self._client.get(f"/api/v1/public/market/{edgex_symbol}/openInterest")

            book_resp, funding_resp, oi_resp = await asyncio.gather(
                book_task, funding_task, oi_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(book_resp, Exception):
                raise book_resp
            if isinstance(funding_resp, Exception):
                raise funding_resp
            if isinstance(oi_resp, Exception):
                logger.warning("OI fetch failed for %s, using 0", symbol)
                oi_usd = 0.0
            else:
                oi_resp.raise_for_status()
                oi_data = oi_resp.json()
                oi_usd = float(oi_data.get("openInterest", 0))

            book_resp.raise_for_status()
            funding_resp.raise_for_status()

            book_data = book_resp.json()
            funding_data = funding_resp.json()

            bids = book_data.get("bids", [])
            asks = book_data.get("asks", [])
            if not bids or not asks:
                return None

            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mark_price = float(funding_data.get("markPrice", 0))
            funding_rate = float(funding_data.get("fundingRate", 0))
            next_funding_ts = int(funding_data.get("nextFundingTime", 0))

            # EdgeX uses 8H intervals
            funding_rate_8h = funding_rate

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
                next_funding_time=datetime.fromtimestamp(next_funding_ts / 1000) if next_funding_ts else None,
                open_interest_usd=oi_usd,
                open_interest_contracts=None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("EdgeX perp data error for %s: %s", symbol, exc)
            return None
