from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Sequence

import httpx

from app.connectors.base import MarketConnector
from app.core.config import get_settings
from app.models.opportunity import MarketQuote

logger = logging.getLogger(__name__)


class KRWUSDForexConnector(MarketConnector):
    """Retrieves USD/KRW forex rate from Dunamu API. / 두나무 API를 통해 달러/원 환율을 취득합니다."""

    venue_type = "forex"

    def __init__(self) -> None:
        self.name = "dunamu_fx"
        timeout = get_settings().public_rest_timeout
        self._dunamu = httpx.AsyncClient(
            base_url="https://quotation-api-cdn.dunamu.com",
            timeout=timeout,
            headers={"User-Agent": "ArbitrageCommand/0.1"},
        )
        self._fallback = httpx.AsyncClient(
            base_url="https://api.exchangerate-api.com",
            timeout=timeout,
            headers={"User-Agent": "ArbitrageCommand/0.1"},
        )
        self._upbit = httpx.AsyncClient(
            base_url="https://api.upbit.com",
            timeout=timeout,
            headers={"User-Agent": "ArbitrageCommand/0.1"},
        )

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        quote = await self._fetch_dunamu()
        if quote:
            return [quote]
        quote = await self._fetch_exchangerate_host()
        if quote:
            return [quote]
        # Try Upbit USDT/KRW as fallback / 업비트 USDT/KRW를 폴백으로 사용
        quote = await self._fetch_upbit_usdt_krw()
        if quote:
            return [quote]
        # Fallback to fixed rate if all APIs fail
        logger.warning("Using fixed USD/KRW rate (1400) / 고정 환율(1400원) 사용")
        return [MarketQuote(
            exchange="fixed_rate",
            venue_type="fx",
            symbol="USD/KRW",
            base_asset="USD",
            quote_currency="KRW",
            bid=1400.0,
            ask=1400.0,
            timestamp=datetime.utcnow(),
        )]

    async def close(self) -> None:
        await self._dunamu.aclose()
        await self._fallback.aclose()
        await self._upbit.aclose()

    async def _fetch_dunamu(self) -> Optional[MarketQuote]:
        try:
            response = await self._dunamu.get(
                "/v1/forex/recent", params={"codes": "FRX.KRWUSD"}
            )
            response.raise_for_status()
            payload = response.json()
            if not payload:
                return None
            data = payload[0]
            base_price = float(data.get("basePrice"))
            now = datetime.utcnow()
            return MarketQuote(
                exchange=self.name,
                venue_type="fx",
                symbol="USD/KRW",
                base_asset="USD",
                quote_currency="KRW",
                bid=base_price,
                ask=base_price,
                timestamp=now,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "KRW/USD forex fetch failed: %s / 환율 조회 실패: %s",
                exc,
                exc,
            )
            return None

    async def _fetch_exchangerate_host(self) -> Optional[MarketQuote]:
        try:
            response = await self._fallback.get("/v4/latest/USD")
            response.raise_for_status()
            payload = response.json()
            rate = float(payload.get("rates", {}).get("KRW"))
            if not rate or rate <= 0:
                return None
            now = datetime.utcnow()
            return MarketQuote(
                exchange="exchangerate_api",
                venue_type="fx",
                symbol="USD/KRW",
                base_asset="USD",
                quote_currency="KRW",
                bid=rate,
                ask=rate,
                timestamp=now,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Fallback forex fetch failed: %s / 대체 환율 조회 실패: %s",
                exc,
                exc,
            )
            return None

    async def _fetch_upbit_usdt_krw(self) -> Optional[MarketQuote]:
        """
        Fetch USDT/KRW rate from Upbit as fallback.
        업비트 USDT/KRW 환율을 폴백으로 사용.
        """
        try:
            response = await self._upbit.get("/v1/orderbook", params={"markets": "KRW-USDT"})
            response.raise_for_status()
            payload = response.json()
            if not payload:
                return None
            orderbook = payload[0]["orderbook_units"][0]
            bid = float(orderbook["bid_price"])
            ask = float(orderbook["ask_price"])
            mid = (bid + ask) / 2.0
            now = datetime.utcnow()
            logger.info(
                "Using Upbit USDT/KRW as forex rate: %.2f / 업비트 USDT/KRW 환율 사용: %.2f",
                mid,
                mid,
            )
            return MarketQuote(
                exchange="upbit_usdt",
                venue_type="fx",
                symbol="USD/KRW",
                base_asset="USD",
                quote_currency="KRW",
                bid=mid,
                ask=mid,
                timestamp=now,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Upbit USDT/KRW forex fetch failed: %s / 업비트 USDT/KRW 환율 조회 실패: %s",
                exc,
                exc,
            )
            return None
