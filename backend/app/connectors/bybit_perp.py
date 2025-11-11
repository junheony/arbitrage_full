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


class BybitPerpConnector(PerpConnector):
    """Fetches Bybit USDT perpetual futures data / 바이빗 USDT 무기한 선물 데이터 수집."""

    venue_type = "perp"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "bybit"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://api.bybit.com",
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
                logger.warning("Bybit perp quote failed for %s: %s", symbol, result)
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
                logger.warning("Bybit funding rate failed for %s: %s", symbol, result)
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
                logger.warning("Bybit perp data failed for %s: %s", symbol, result)
                continue
            if result:
                data.append(result)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        base, quote = symbol.split("/")
        bybit_symbol = base + quote  # e.g., BTCUSDT
        try:
            response = await self._client.get(
                "/v5/market/open-interest",
                params={"category": "linear", "symbol": bybit_symbol, "intervalTime": "5min"},
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("result", {})
            items = result.get("list", [])
            if not items:
                return 0.0

            # Get the latest OI entry
            latest = items[0]
            oi_value = float(latest.get("openInterest", 0))

            # Bybit returns OI in base currency, need to convert to USD
            # Get mark price
            ticker_response = await self._client.get(
                "/v5/market/tickers", params={"category": "linear", "symbol": bybit_symbol}
            )
            ticker_response.raise_for_status()
            ticker_data = ticker_response.json()
            ticker_result = ticker_data.get("result", {})
            ticker_list = ticker_result.get("list", [])
            if not ticker_list:
                return 0.0

            mark_price = float(ticker_list[0].get("markPrice", 0))
            return oi_value * mark_price
        except Exception as exc:
            logger.warning("Bybit OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch order book for a single symbol / 단일 심볼 호가 조회."""
        base, quote = symbol.split("/")
        bybit_symbol = base + quote
        try:
            response = await self._client.get(
                "/v5/market/orderbook", params={"category": "linear", "symbol": bybit_symbol, "limit": 5}
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Bybit perp depth error for %s: %s", symbol, exc)
            return None

        payload = response.json()
        result = payload.get("result", {})
        bids = result.get("b", [])
        asks = result.get("a", [])
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
        bybit_symbol = base + quote
        try:
            # Get ticker for funding rate and mark price
            response = await self._client.get(
                "/v5/market/tickers", params={"category": "linear", "symbol": bybit_symbol}
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("result", {})
            items = result.get("list", [])
            if not items:
                return None

            item = items[0]
            funding_rate = float(item.get("fundingRate", 0))
            next_funding_ts = int(item.get("nextFundingTime", 0))
            mark_price = float(item.get("markPrice", 0))
            index_price = float(item.get("indexPrice", 0))

            # Bybit funding happens every 8 hours
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
            logger.warning("Bybit funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        base, quote = symbol.split("/")
        bybit_symbol = base + quote

        try:
            # Fetch ticker and order book in parallel
            ticker_task = self._client.get(
                "/v5/market/tickers", params={"category": "linear", "symbol": bybit_symbol}
            )
            depth_task = self._client.get(
                "/v5/market/orderbook", params={"category": "linear", "symbol": bybit_symbol, "limit": 5}
            )
            oi_task = self._client.get(
                "/v5/market/open-interest",
                params={"category": "linear", "symbol": bybit_symbol, "intervalTime": "5min"},
            )

            ticker_resp, depth_resp, oi_resp = await asyncio.gather(
                ticker_task, depth_task, oi_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(ticker_resp, Exception):
                raise ticker_resp
            if isinstance(depth_resp, Exception):
                raise depth_resp
            if isinstance(oi_resp, Exception):
                logger.warning("OI fetch failed for %s, using 0", symbol)
                oi_contracts = 0.0
            else:
                oi_resp.raise_for_status()
                oi_data = oi_resp.json()
                oi_result = oi_data.get("result", {})
                oi_items = oi_result.get("list", [])
                oi_contracts = float(oi_items[0].get("openInterest", 0)) if oi_items else 0.0

            ticker_resp.raise_for_status()
            depth_resp.raise_for_status()

            ticker_data = ticker_resp.json()
            depth_data = depth_resp.json()

            ticker_result = ticker_data.get("result", {})
            ticker_items = ticker_result.get("list", [])
            if not ticker_items:
                return None

            depth_result = depth_data.get("result", {})
            bids = depth_result.get("b", [])
            asks = depth_result.get("a", [])
            if not bids or not asks:
                return None

            ticker = ticker_items[0]
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mark_price = float(ticker.get("markPrice", 0))
            funding_rate = float(ticker.get("fundingRate", 0))
            next_funding_ts = int(ticker.get("nextFundingTime", 0))

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
                funding_rate_8h=funding_rate,  # Bybit uses 8H intervals
                next_funding_time=datetime.fromtimestamp(next_funding_ts / 1000) if next_funding_ts else None,
                open_interest_usd=oi_usd,
                open_interest_contracts=oi_contracts,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Bybit perp data error for %s: %s", symbol, exc)
            return None
