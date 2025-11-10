from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Sequence

import httpx

from app.connectors.base import MarketConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote

logger = logging.getLogger(__name__)


class UpbitSpotConnector(MarketConnector):
    """Pulls KRW order book data from Upbit. / 업비트 원화 주문장을 수집합니다."""

    venue_type = "spot"

    def __init__(self, symbols: Iterable[str]) -> None:
        self.name = "upbit"
        self._symbols = list(symbols)
        timeout = get_settings().public_rest_timeout
        self._client = httpx.AsyncClient(
            base_url="https://api.upbit.com",
            timeout=timeout,
            headers={"User-Agent": "ArbitrageCommand/0.1"},
        )

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        markets = ",".join(f"KRW-{symbol.split('/')[0]}" for symbol in self._symbols)
        try:
            response = await self._client.get(
                "/v1/orderbook", params={"markets": markets}
            )
            response.raise_for_status()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Upbit orderbook request failed: %s / 업비트 주문장 조회 실패: %s",
                exc,
                exc,
            )
            return []

        payload = response.json()
        quotes: list[MarketQuote] = []
        now = datetime.utcnow()
        for entry in payload:
            market = entry.get("market", "")
            base_asset = market.replace("KRW-", "")
            orderbook_units = entry.get("orderbook_units") or []
            if not orderbook_units:
                continue
            top = orderbook_units[0]
            bid = float(top.get("bid_price"))
            ask = float(top.get("ask_price"))
            quotes.append(
                MarketQuote(
                    exchange=self.name,
                    venue_type="spot",
                    symbol=f"{base_asset}/KRW",
                    base_asset=base_asset,
                    quote_currency="KRW",
                    bid=bid,
                    ask=ask,
                    timestamp=now,
                )
            )
        return quotes

    async def close(self) -> None:
        await self._client.aclose()
