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


class OkxSpotConnector(MarketConnector):
    """Fetches OKX spot order book snapshots. / OKX 현물 주문장을 수집합니다."""

    venue_type = "spot"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "okx"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://www.okx.com",
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
                    "OKX fetch failed for %s: %s / OKX %s 조회 실패: %s",
                    symbol,
                    result,
                    symbol,
                    result,
                )
                continue
            if result:
                quotes.append(result)
        return quotes

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_symbol(self, symbol: str) -> MarketQuote | None:
        base, quote = symbol.split("/")
        inst_id = f"{base}-{quote}"
        try:
            response = await self._client.get(
                "/api/v5/market/books",
                params={"instId": inst_id, "sz": 5},
            )
            response.raise_for_status()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "OKX depth error for %s: %s / OKX 호가 조회 오류 (%s): %s",
                symbol,
                exc,
                symbol,
                exc,
            )
            return None

        payload = response.json()
        data = payload.get("data") or []
        if not data:
            return None
        book = data[0]
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            return None

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        return MarketQuote(
            exchange=self.name,
            venue_type="spot",
            symbol=symbol,
            base_asset=base,
            quote_currency=quote,
            bid=best_bid,
            ask=best_ask,
            timestamp=datetime.utcnow(),
        )
