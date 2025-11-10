from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Sequence

import httpx

from app.connectors.base import MarketConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote

logger = logging.getLogger(__name__)


class BithumbSpotConnector(MarketConnector):
    """Pulls KRW order book data from Bithumb. / 빗썸 원화 주문장을 수집합니다."""

    venue_type = "spot"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "bithumb"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://api.bithumb.com",
            timeout=timeout,
            headers={"User-Agent": "ArbitrageCommand/0.1"},
        )

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        tasks = [self._fetch_symbol(symbol) for symbol in self._symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: list[MarketQuote] = []
        for symbol, result in zip(self._symbols, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Bithumb fetch failed for %s: %s / 빗썸 %s 조회 실패: %s",
                    symbol,
                    result,
                    symbol,
                    result,
                )
                continue
            if result:
                quotes.append(result)
        return quotes

    async def _fetch_symbol(self, symbol: str) -> MarketQuote | None:
        base_asset = symbol.split("/")[0]
        try:
            response = await self._client.get(f"/public/orderbook/{base_asset}_KRW")
            response.raise_for_status()
        except Exception as exc:  # pylint: disable=broad-except
            return None

        payload = response.json()
        data = payload.get("data") or {}
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        if not bids or not asks:
            return None

        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        return MarketQuote(
            exchange=self.name,
            venue_type="spot",
            symbol=f"{base_asset}/KRW",
            base_asset=base_asset,
            quote_currency="KRW",
            bid=best_bid,
            ask=best_ask,
            timestamp=datetime.utcnow(),
        )

    async def close(self) -> None:
        await self._client.aclose()
