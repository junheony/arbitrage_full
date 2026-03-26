from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Iterable, Sequence

import httpx

from app.connectors.perp_base import PerpConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote
from app.models.market_data import FundingRate, PerpMarketData

logger = logging.getLogger(__name__)


class StandXPerpConnector(PerpConnector):
    """Fetches StandX perpetual futures data / StandX 무기한 선물 데이터 수집.

    StandX is a perpetual DEX with yield-bearing DUSD margin.
    Operates on BNB Chain and Solana.
    Note: 호가가 그리 튼튼하지 않아서 큰 볼륨은 힘들 수 있음.
    """

    venue_type = "perp"

    BASE_URL = "https://perps.standx.com"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "standx"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout * 2,
            headers={"Content-Type": "application/json"},
        )
        self._symbol_map = self._build_symbol_map()

    def _build_symbol_map(self) -> dict[str, str]:
        """Map standard symbols to StandX format / 심볼 형식 매핑.

        StandX uses BTC-USD format (DUSD is the quote currency).
        Currently only BTC-USD is supported.
        """
        symbol_map = {}
        for symbol in self._symbols:
            base, quote = symbol.split("/")
            # StandX uses BTC-USD format with DUSD as quote
            symbol_map[symbol] = f"{base}-USD"
        return symbol_map

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Fetch order book quotes for perpetual futures / 무기한 선물 호가 조회."""
        tasks = [self._fetch_quote(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.debug("StandX quote failed for %s: %s", symbol, result)
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
                logger.debug("StandX funding rate failed for %s: %s", symbol, result)
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
                logger.debug("StandX perp data failed for %s: %s", symbol, result)
                continue
            if result:
                data.append(result)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        standx_symbol = self._symbol_map.get(symbol, symbol.replace("/", ""))
        try:
            response = await self._client.get(
                "/api/query_symbol_market",
                params={"symbol": standx_symbol}
            )
            response.raise_for_status()
            data = response.json()
            oi = float(data.get("open_interest", 0))
            return oi
        except Exception as exc:
            logger.debug("StandX OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch order book for a single symbol / 단일 심볼 호가 조회."""
        base, quote = symbol.split("/")
        standx_symbol = self._symbol_map.get(symbol, f"{base}{quote}")

        try:
            # Use depth book for bid/ask
            response = await self._client.get(
                "/api/query_depth_book",
                params={"symbol": standx_symbol}
            )
            response.raise_for_status()
            data = response.json()

            bids = data.get("bids", [])
            asks = data.get("asks", [])

            if not bids or not asks:
                # Fallback to price endpoint
                price_resp = await self._client.get(
                    "/api/query_symbol_price",
                    params={"symbol": standx_symbol}
                )
                price_resp.raise_for_status()
                price_data = price_resp.json()

                best_bid = float(price_data.get("bid", 0))
                best_ask = float(price_data.get("ask", 0))

                if best_bid <= 0 or best_ask <= 0:
                    # Use mid price as fallback
                    mid = float(price_data.get("mid_price", 0) or price_data.get("last_price", 0))
                    if mid > 0:
                        spread = mid * 0.0005  # Assume 5 bps spread
                        best_bid = mid - spread
                        best_ask = mid + spread
                    else:
                        return None
            else:
                # Parse depth book
                best_bid = float(bids[0][0]) if isinstance(bids[0], list) else float(bids[0].get("price", 0))
                best_ask = float(asks[0][0]) if isinstance(asks[0], list) else float(asks[0].get("price", 0))

            if best_bid <= 0 or best_ask <= 0:
                return None

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
            logger.debug("StandX quote error for %s: %s", symbol, exc)
            return None

    async def _fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate for a single symbol / 단일 심볼 펀딩비 조회."""
        base, quote = symbol.split("/")
        standx_symbol = self._symbol_map.get(symbol, f"{base}{quote}")

        try:
            # Query recent funding rates (last hour)
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - 3600000  # 1 hour ago

            response = await self._client.get(
                "/api/query_funding_rates",
                params={
                    "symbol": standx_symbol,
                    "start_time": start_ms,
                    "end_time": now_ms,
                }
            )
            response.raise_for_status()
            data = response.json()

            # Get the most recent funding rate
            rates = data if isinstance(data, list) else data.get("rates", [])
            if not rates:
                return None

            latest = rates[-1] if isinstance(rates, list) else rates
            funding_rate = float(latest.get("funding_rate", 0))
            mark_price = float(latest.get("mark_price", 0))
            index_price = float(latest.get("index_price", 0))

            # StandX funding interval - assume 8h for now
            funding_rate_8h = funding_rate

            # Get open interest from market endpoint
            oi_usd = await self.fetch_open_interest(symbol)

            return FundingRate(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                funding_rate=funding_rate,
                funding_rate_8h=funding_rate_8h,
                next_funding_time=None,
                open_interest_usd=oi_usd,
                mark_price=mark_price if mark_price > 0 else None,
                index_price=index_price if index_price > 0 else None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.debug("StandX funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        base, quote = symbol.split("/")
        standx_symbol = self._symbol_map.get(symbol, f"{base}{quote}")

        try:
            # Fetch market data which includes price, OI, and more
            market_task = self._client.get(
                "/api/query_symbol_market",
                params={"symbol": standx_symbol}
            )
            price_task = self._client.get(
                "/api/query_symbol_price",
                params={"symbol": standx_symbol}
            )

            # Query recent funding rate
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - 3600000
            funding_task = self._client.get(
                "/api/query_funding_rates",
                params={
                    "symbol": standx_symbol,
                    "start_time": start_ms,
                    "end_time": now_ms,
                }
            )

            market_resp, price_resp, funding_resp = await asyncio.gather(
                market_task, price_task, funding_task, return_exceptions=True
            )

            # Parse market data
            oi_usd = 0.0
            if not isinstance(market_resp, Exception):
                market_resp.raise_for_status()
                market_data = market_resp.json()
                oi_usd = float(market_data.get("open_interest", 0))

            # Parse price data
            if isinstance(price_resp, Exception):
                raise price_resp
            price_resp.raise_for_status()
            price_data = price_resp.json()

            mark_price = float(price_data.get("mark_price", 0))
            last_price = float(price_data.get("last_price", 0))
            best_bid = float(price_data.get("bid", 0))
            best_ask = float(price_data.get("ask", 0))
            mid_price = float(price_data.get("mid_price", 0))

            # Fallback logic for bid/ask
            if best_bid <= 0 or best_ask <= 0:
                reference_price = mark_price or mid_price or last_price
                if reference_price > 0:
                    spread = reference_price * 0.0005
                    best_bid = reference_price - spread
                    best_ask = reference_price + spread
                else:
                    return None

            if mark_price <= 0:
                mark_price = (best_bid + best_ask) / 2

            # Parse funding rate
            funding_rate_8h = 0.0
            if not isinstance(funding_resp, Exception):
                funding_resp.raise_for_status()
                funding_data = funding_resp.json()
                rates = funding_data if isinstance(funding_data, list) else funding_data.get("rates", [])
                if rates:
                    latest = rates[-1] if isinstance(rates, list) else rates
                    funding_rate_8h = float(latest.get("funding_rate", 0))

            return PerpMarketData(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                bid=best_bid,
                ask=best_ask,
                mark_price=mark_price,
                funding_rate=funding_rate_8h,
                funding_rate_8h=funding_rate_8h,
                next_funding_time=None,
                open_interest_usd=oi_usd,
                open_interest_contracts=None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.debug("StandX perp data error for %s: %s", symbol, exc)
            return None
