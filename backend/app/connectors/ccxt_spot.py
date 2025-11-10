from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Sequence

import ccxt

from app.connectors.base import MarketConnector
from app.models.opportunity import MarketQuote

logger = logging.getLogger(__name__)


class CCXTSpotConnector(MarketConnector):
    """Fetches spot order book quotes via CCXT. / CCXT를 통해 현물 주문장을 수집합니다."""

    venue_type = "spot"

    def __init__(self, exchange_id: str, symbols: Iterable[str]) -> None:
        self.name = exchange_id
        self._symbols = list(symbols)
        exchange_class = getattr(ccxt, exchange_id)
        self._client: ccxt.Exchange = exchange_class({"enableRateLimit": True})

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        quotes: list[MarketQuote] = []
        for symbol in self._symbols:
            quote = await self._fetch_symbol(symbol)
            if quote:
                quotes.append(quote)
        return quotes

    async def _fetch_symbol(self, symbol: str) -> MarketQuote | None:
        try:
            order_book = await asyncio.to_thread(self._client.fetch_order_book, symbol, 5)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "CCXT %s fetch failed for %s: %s / CCXT %s 심볼 %s 조회 실패: %s",
                self.name,
                symbol,
                exc,
                self.name,
                symbol,
                exc,
            )
            return None

        bids = order_book.get("bids") or []
        asks = order_book.get("asks") or []
        if not bids or not asks:
            return None

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        return MarketQuote(
            exchange=self.name,
            venue_type="spot",
            symbol=symbol,
            bid=float(best_bid),
            ask=float(best_ask),
            timestamp=datetime.utcnow(),
        )

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)
