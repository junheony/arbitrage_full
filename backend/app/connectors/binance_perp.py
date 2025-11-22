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


class BinancePerpConnector(PerpConnector):
    """Fetches Binance USDⓈ-M perpetual futures data / 바이낸스 USDT 무기한 선물 데이터 수집."""

    venue_type = "perp"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "binance"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://fapi.binance.com",  # Futures API
            timeout=timeout,
            headers={"User-Agent": "ArbitrageCommand/0.1"},
        )

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Fetch order book quotes for perpetual futures / 무기한 선물 호가 조회."""
        tasks = [self._fetch_quote(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning("Binance perp quote failed for %s: %s", symbol, result)
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
                logger.warning("Binance funding rate failed for %s: %s", symbol, result)
                continue
            if result:
                funding_rates.append(result)
        return funding_rates

    async def fetch_perp_market_data(self) -> Sequence[PerpMarketData]:
        """Fetch combined market data (quotes + funding + OI) with rate limiting / 레이트 리밋을 고려한 통합 시장 데이터 조회."""
        data: list[PerpMarketData] = []
        # Process in batches of 5 to avoid rate limiting (Binance is strict) / 레이트 리밋 회피를 위해 5개씩 배치 처리 (바이낸스는 엄격함)
        batch_size = 5
        for i in range(0, len(self._symbols), batch_size):
            batch = self._symbols[i:i + batch_size]
            tasks = [self._fetch_perp_data(symbol) for symbol in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for symbol, result in zip(batch, results):
                if isinstance(result, Exception):
                    # Skip logging for known unsupported symbols
                    if "400" not in str(result):
                        logger.warning("Binance perp data failed for %s: %s", symbol, result)
                    continue
                if result:
                    data.append(result)
            # Longer delay between batches to avoid 418/429 errors
            if i + batch_size < len(self._symbols):
                await asyncio.sleep(0.2)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        base, quote = symbol.split("/")
        pair = base + quote  # e.g., BTCUSDT
        try:
            response = await self._client.get("/fapi/v1/openInterest", params={"symbol": pair})
            response.raise_for_status()
            data = response.json()
            oi_contracts = float(data.get("openInterest", 0))

            # Get mark price to convert to USD
            mark_response = await self._client.get("/fapi/v1/premiumIndex", params={"symbol": pair})
            mark_response.raise_for_status()
            mark_data = mark_response.json()
            mark_price = float(mark_data.get("markPrice", 0))

            return oi_contracts * mark_price
        except Exception as exc:
            logger.warning("Binance OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch order book for a single symbol / 단일 심볼 호가 조회."""
        base, quote = symbol.split("/")
        pair = base + quote
        try:
            response = await self._client.get(
                "/fapi/v1/depth",
                params={"symbol": pair, "limit": 5},
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Binance perp depth error for %s: %s", symbol, exc)
            return None

        payload = response.json()
        bids = payload.get("bids") or []
        asks = payload.get("asks") or []
        if not bids or not asks:
            return None

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

    async def _fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate for a single symbol / 단일 심볼 펀딩비 조회."""
        base, quote = symbol.split("/")
        pair = base + quote
        try:
            response = await self._client.get("/fapi/v1/premiumIndex", params={"symbol": pair})
            response.raise_for_status()
            data = response.json()

            funding_rate = float(data.get("lastFundingRate", 0))
            next_funding_ts = int(data.get("nextFundingTime", 0))
            mark_price = float(data.get("markPrice", 0))
            index_price = float(data.get("indexPrice", 0))

            # Binance funding happens every 8 hours, so rate is already 8H
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
                index_price=index_price,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Binance funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        base, quote = symbol.split("/")
        pair = base + quote

        try:
            # Fetch all data in parallel
            depth_task = self._client.get("/fapi/v1/depth", params={"symbol": pair, "limit": 5})
            premium_task = self._client.get("/fapi/v1/premiumIndex", params={"symbol": pair})
            oi_task = self._client.get("/fapi/v1/openInterest", params={"symbol": pair})

            depth_resp, premium_resp, oi_resp = await asyncio.gather(
                depth_task, premium_task, oi_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(depth_resp, Exception):
                raise depth_resp
            if isinstance(premium_resp, Exception):
                raise premium_resp
            if isinstance(oi_resp, Exception):
                logger.warning("OI fetch failed for %s, using 0", symbol)
                oi_data = {"openInterest": "0"}
            else:
                oi_resp.raise_for_status()
                oi_data = oi_resp.json()

            depth_resp.raise_for_status()
            premium_resp.raise_for_status()

            depth = depth_resp.json()
            premium = premium_resp.json()

            bids = depth.get("bids") or []
            asks = depth.get("asks") or []
            if not bids or not asks:
                return None

            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mark_price = float(premium.get("markPrice", 0))
            funding_rate = float(premium.get("lastFundingRate", 0))
            next_funding_ts = int(premium.get("nextFundingTime", 0))

            oi_contracts = float(oi_data.get("openInterest", 0))
            oi_usd = oi_contracts * mark_price

            return PerpMarketData(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                bid=best_bid,
                ask=best_ask,
                mark_price=mark_price,
                funding_rate=funding_rate,
                funding_rate_8h=funding_rate,  # Binance uses 8H intervals
                next_funding_time=datetime.fromtimestamp(next_funding_ts / 1000) if next_funding_ts else None,
                open_interest_usd=oi_usd,
                open_interest_contracts=oi_contracts,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Binance perp data error for %s: %s", symbol, exc)
            return None
