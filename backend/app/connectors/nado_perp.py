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


class NadoPerpConnector(PerpConnector):
    """Fetches Nado DEX perpetual futures data / Nado DEX 무기한 선물 데이터 수집.

    Nado is built on Ink L2 with off-chain sequencer for low latency trading.
    1시간 단위 펀딩비를 사용합니다.
    """

    venue_type = "perp"

    # Nado API base URLs (Ink Mainnet)
    GATEWAY_URL = "https://gateway.prod.nado.xyz/v1"
    # Archive URL without trailing path - requests are made to root
    ARCHIVE_URL = "https://archive.prod.nado.xyz"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "nado"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url=self.GATEWAY_URL,
            timeout=timeout * 2,
            headers={"Content-Type": "application/json"},
        )
        self._archive_client = httpx.AsyncClient(
            base_url=self.ARCHIVE_URL,
            timeout=timeout * 2,
            headers={
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        self._product_map: dict[str, int] = {}  # symbol -> product_id
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Fetch product IDs on first use / 최초 사용시 상품 ID 조회."""
        if self._initialized:
            return
        try:
            response = await self._client.get("/query", params={"type": "symbols", "product_type": "perp"})
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                # symbols is a dict with symbol names as keys
                symbols_data = data.get("data", {}).get("symbols", {})
                for symbol_name, item in symbols_data.items():
                    product_id = item.get("product_id")
                    if symbol_name and product_id is not None:
                        # Convert "BTC-PERP" to "BTC/USDT" format
                        base = symbol_name.replace("-PERP", "")
                        standard_symbol = f"{base}/USDT"
                        self._product_map[standard_symbol] = product_id

            self._initialized = True
            logger.info("Nado initialized with %d products / Nado 초기화 완료: %d개 상품",
                       len(self._product_map), len(self._product_map))
        except Exception as exc:
            logger.warning("Nado initialization failed: %s / 초기화 실패: %s", exc, exc)
            self._initialized = True  # Don't retry on every call

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Fetch order book quotes for perpetual futures / 무기한 선물 호가 조회."""
        await self._ensure_initialized()
        tasks = [self._fetch_quote(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.debug("Nado quote failed for %s: %s", symbol, result)
                continue
            if result:
                quotes.append(result)
        return quotes

    async def fetch_funding_rates(self) -> Sequence[FundingRate]:
        """Fetch current funding rates for all symbols / 모든 심볼의 펀딩비 조회."""
        await self._ensure_initialized()
        tasks = [self._fetch_funding_rate(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        funding_rates: list[FundingRate] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.debug("Nado funding rate failed for %s: %s", symbol, result)
                continue
            if result:
                funding_rates.append(result)
        return funding_rates

    async def fetch_perp_market_data(self) -> Sequence[PerpMarketData]:
        """Fetch combined market data (quotes + funding + OI) / 통합 시장 데이터 조회."""
        await self._ensure_initialized()
        tasks = [self._fetch_perp_data(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        data: list[PerpMarketData] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.debug("Nado perp data failed for %s: %s", symbol, result)
                continue
            if result:
                data.append(result)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        await self._ensure_initialized()
        product_id = self._product_map.get(symbol)
        if product_id is None:
            return 0.0
        try:
            # Use all_products endpoint to get OI
            response = await self._client.get("/query", params={"type": "all_products"})
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                # Parse open interest from product data
                # Note: Actual field name may vary based on API response
                products = data.get("data", {}).get("perp_products", [])
                for product in products:
                    if product.get("product_id") == product_id:
                        oi_x18 = product.get("total_open_interest_x18", "0")
                        return float(oi_x18) / 1e18
            return 0.0
        except Exception as exc:
            logger.debug("Nado OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()
        await self._archive_client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch order book for a single symbol / 단일 심볼 호가 조회."""
        product_id = self._product_map.get(symbol)
        if product_id is None:
            return None

        base, quote = symbol.split("/")

        try:
            response = await self._client.get(
                "/query",
                params={"type": "market_price", "product_id": product_id}
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                return None

            price_data = data.get("data", {})
            # Prices are x18 scaled
            bid_x18 = price_data.get("bid_x18", "0")
            ask_x18 = price_data.get("ask_x18", "0")

            best_bid = float(bid_x18) / 1e18
            best_ask = float(ask_x18) / 1e18

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
            logger.debug("Nado quote error for %s: %s", symbol, exc)
            return None

    async def _fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate for a single symbol / 단일 심볼 펀딩비 조회.

        Nado uses 1-hour funding intervals (unlike 8h for most CEXs).
        """
        product_id = self._product_map.get(symbol)
        if product_id is None:
            return None

        base, quote = symbol.split("/")

        try:
            # Funding rate from archive endpoint
            response = await self._archive_client.post(
                "/v1",
                json={"funding_rate": {"product_id": product_id}}
            )
            response.raise_for_status()
            data = response.json()

            funding_rate_x18 = data.get("funding_rate_x18", "0")
            # This is 24h rate, convert to hourly then to 8h for comparison
            funding_rate_24h = float(funding_rate_x18) / 1e18
            # Nado uses 1h funding, so hourly rate = 24h rate / 24
            funding_rate_1h = funding_rate_24h / 24
            # Convert to 8h equivalent for comparison
            funding_rate_8h = funding_rate_1h * 8

            # Get mark price from market price endpoint
            price_resp = await self._client.get(
                "/query",
                params={"type": "market_price", "product_id": product_id}
            )
            price_resp.raise_for_status()
            price_data = price_resp.json()

            mark_price = 0.0
            if price_data.get("status") == "success":
                bid_x18 = float(price_data.get("data", {}).get("bid_x18", "0"))
                ask_x18 = float(price_data.get("data", {}).get("ask_x18", "0"))
                mark_price = (bid_x18 + ask_x18) / 2 / 1e18

            oi_usd = await self.fetch_open_interest(symbol)

            return FundingRate(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                funding_rate=funding_rate_1h,  # 1h rate (Nado's native interval)
                funding_rate_8h=funding_rate_8h,  # Normalized for comparison
                next_funding_time=None,  # Nado has continuous funding
                open_interest_usd=oi_usd,
                mark_price=mark_price,
                index_price=None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.debug("Nado funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        product_id = self._product_map.get(symbol)
        if product_id is None:
            return None

        base, quote = symbol.split("/")

        try:
            # Fetch price and funding in parallel
            price_task = self._client.get(
                "/query",
                params={"type": "market_price", "product_id": product_id}
            )
            funding_task = self._archive_client.post(
                "/v1",
                json={"funding_rate": {"product_id": product_id}}
            )

            price_resp, funding_resp = await asyncio.gather(
                price_task, funding_task, return_exceptions=True
            )

            if isinstance(price_resp, Exception):
                raise price_resp
            if isinstance(funding_resp, Exception):
                # Continue without funding data
                funding_rate_8h = 0.0
            else:
                funding_resp.raise_for_status()
                funding_data = funding_resp.json()
                funding_rate_24h = float(funding_data.get("funding_rate_x18", "0")) / 1e18
                funding_rate_1h = funding_rate_24h / 24
                funding_rate_8h = funding_rate_1h * 8

            price_resp.raise_for_status()
            price_data = price_resp.json()

            if price_data.get("status") != "success":
                return None

            bid_x18 = float(price_data.get("data", {}).get("bid_x18", "0"))
            ask_x18 = float(price_data.get("data", {}).get("ask_x18", "0"))

            best_bid = bid_x18 / 1e18
            best_ask = ask_x18 / 1e18
            mark_price = (best_bid + best_ask) / 2

            if best_bid <= 0 or best_ask <= 0:
                return None

            oi_usd = await self.fetch_open_interest(symbol)

            return PerpMarketData(
                exchange=self.name,
                symbol=symbol,
                base_asset=base,
                quote_currency=quote,
                bid=best_bid,
                ask=best_ask,
                mark_price=mark_price,
                funding_rate=funding_rate_8h / 8,  # Store 1h rate
                funding_rate_8h=funding_rate_8h,
                next_funding_time=None,
                open_interest_usd=oi_usd,
                open_interest_contracts=None,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.debug("Nado perp data error for %s: %s", symbol, exc)
            return None
