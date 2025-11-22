from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Iterable, Sequence

import httpx

from app.connectors.perp_base import PerpConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote
from app.models.market_data import FundingRate, PerpMarketData

logger = logging.getLogger(__name__)


class HyperliquidPerpConnector(PerpConnector):
    """Fetches Hyperliquid DEX perpetual futures data / 하이퍼리퀴드 DEX 무기한 선물 데이터 수집."""

    venue_type = "perp"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "hyperliquid"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://api.hyperliquid.xyz",
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        # Map standard symbols to Hyperliquid format
        self._symbol_map = self._build_symbol_map()

    def _build_symbol_map(self) -> dict[str, str]:
        """Map standard symbols (BTC/USDT) to Hyperliquid format (BTC) / 심볼 형식 매핑."""
        symbol_map = {}
        for symbol in self._symbols:
            base, _ = symbol.split("/")
            symbol_map[symbol] = base
        return symbol_map

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Fetch order book quotes for perpetual futures / 무기한 선물 호가 조회."""
        tasks = [self._fetch_quote(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning("Hyperliquid quote failed for %s: %s", symbol, result)
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
                logger.warning("Hyperliquid funding rate failed for %s: %s", symbol, result)
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
                logger.warning("Hyperliquid perp data failed for %s: %s", symbol, result)
                continue
            if result:
                data.append(result)
        return data

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD for a symbol / 심볼의 USD 기준 미결제약정 조회."""
        hl_symbol = self._symbol_map.get(symbol, symbol.split("/")[0])
        try:
            response = await self._client.post("/info", json={"type": "metaAndAssetCtxs"})
            response.raise_for_status()
            data = response.json()

            # Find the asset
            for asset_ctx in data[1]:  # assetCtxs is second element
                if asset_ctx.get("coin") == hl_symbol:
                    oi_value = float(asset_ctx.get("openInterest", 0))
                    mark_price = float(asset_ctx.get("markPx", 0))
                    return oi_value * mark_price

            return 0.0
        except Exception as exc:
            logger.warning("Hyperliquid OI fetch failed for %s: %s", symbol, exc)
            return 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_quote(self, symbol: str) -> MarketQuote | None:
        """Fetch order book for a single symbol / 단일 심볼 호가 조회."""
        base, quote = symbol.split("/")
        hl_symbol = self._symbol_map.get(symbol, base)

        try:
            response = await self._client.post("/info", json={"type": "l2Book", "coin": hl_symbol})
            response.raise_for_status()
            data = response.json()

            # Check if symbol exists
            if not data or "levels" not in data:
                logger.debug("Hyperliquid: Symbol %s (%s) not found or no data", symbol, hl_symbol)
                return None

            levels = data.get("levels", [])
            if len(levels) < 2:
                return None

            bids = levels[0]  # bids
            asks = levels[1]  # asks

            if not bids or not asks:
                return None

            # Hyperliquid format: [[price, size], ...]
            best_bid = float(bids[0][0]["px"])
            best_ask = float(asks[0][0]["px"])

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
            # Only log at debug level for missing symbols to reduce noise
            logger.debug("Hyperliquid depth error for %s (%s): %s", symbol, hl_symbol, exc)
            return None

    async def _fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate for a single symbol / 단일 심볼 펀딩비 조회."""
        base, quote = symbol.split("/")
        hl_symbol = self._symbol_map.get(symbol, base)

        try:
            response = await self._client.post("/info", json={"type": "metaAndAssetCtxs"})
            response.raise_for_status()
            data = response.json()

            # Find the asset in assetCtxs
            for asset_ctx in data[1]:  # assetCtxs is second element
                if asset_ctx.get("coin") == hl_symbol:
                    funding_rate = float(asset_ctx.get("funding", 0))
                    mark_price = float(asset_ctx.get("markPx", 0))
                    oi_value = float(asset_ctx.get("openInterest", 0))
                    oi_usd = oi_value * mark_price

                    # Hyperliquid funding rate is per hour, convert to 8H
                    funding_rate_8h = funding_rate * 8

                    return FundingRate(
                        exchange=self.name,
                        symbol=symbol,
                        base_asset=base,
                        quote_currency=quote,
                        funding_rate=funding_rate,
                        funding_rate_8h=funding_rate_8h,
                        next_funding_time=None,  # Hyperliquid doesn't provide next funding time
                        open_interest_usd=oi_usd,
                        mark_price=mark_price,
                        index_price=None,  # Not provided by Hyperliquid
                        timestamp=datetime.utcnow(),
                    )

            return None
        except Exception as exc:
            logger.warning("Hyperliquid funding rate error for %s: %s", symbol, exc)
            return None

    async def _fetch_perp_data(self, symbol: str) -> PerpMarketData | None:
        """Fetch combined perp market data / 통합 무기한 선물 데이터 조회."""
        base, quote = symbol.split("/")
        hl_symbol = self._symbol_map.get(symbol, base)

        try:
            # Fetch order book and meta in parallel
            book_task = self._client.post("/info", json={"type": "l2Book", "coin": hl_symbol})
            meta_task = self._client.post("/info", json={"type": "metaAndAssetCtxs"})

            book_resp, meta_resp = await asyncio.gather(book_task, meta_task, return_exceptions=True)

            if isinstance(book_resp, Exception):
                raise book_resp
            if isinstance(meta_resp, Exception):
                raise meta_resp

            book_resp.raise_for_status()
            meta_resp.raise_for_status()

            book_data = book_resp.json()
            meta_data = meta_resp.json()

            # Parse order book
            levels = book_data.get("levels", [])
            if len(levels) < 2:
                return None

            bids = levels[0]
            asks = levels[1]
            if not bids or not asks:
                return None

            best_bid = float(bids[0][0]["px"])
            best_ask = float(asks[0][0]["px"])

            # Find asset in meta
            asset_ctx = None
            for ctx in meta_data[1]:
                if ctx.get("coin") == hl_symbol:
                    asset_ctx = ctx
                    break

            if not asset_ctx:
                return None

            funding_rate = float(asset_ctx.get("funding", 0))
            mark_price = float(asset_ctx.get("markPx", 0))
            oi_value = float(asset_ctx.get("openInterest", 0))
            oi_usd = oi_value * mark_price

            # Hyperliquid funding is per hour, convert to 8H
            funding_rate_8h = funding_rate * 8

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
                open_interest_contracts=oi_value,
                timestamp=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("Hyperliquid perp data error for %s: %s", symbol, exc)
            return None
