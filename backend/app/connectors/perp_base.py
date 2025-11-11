from __future__ import annotations

import abc
from typing import Sequence

from app.connectors.base import MarketConnector
from app.models.market_data import FundingRate, PerpMarketData


class PerpConnector(MarketConnector):
    """Abstract base class for perpetual futures connectors / 무기한 선물 커넥터를 위한 추상 기본 클래스.

    This extends MarketConnector to also provide funding rate and open interest data.
    MarketConnector를 확장하여 펀딩비와 미결제약정 데이터도 제공합니다.
    """

    @abc.abstractmethod
    async def fetch_funding_rates(self) -> Sequence[FundingRate]:
        """Return the latest funding rates for all symbols / 모든 심볼의 최신 펀딩비를 반환합니다."""
        pass

    @abc.abstractmethod
    async def fetch_perp_market_data(self) -> Sequence[PerpMarketData]:
        """Return combined market data (quotes + funding) for all symbols.

        호가와 펀딩비를 결합한 시장 데이터를 반환합니다.

        This is a convenience method that combines fetch_quotes and fetch_funding_rates.
        fetch_quotes와 fetch_funding_rates를 결합한 편의 메서드입니다.
        """
        pass

    @abc.abstractmethod
    async def fetch_open_interest(self, symbol: str) -> float:
        """Return the open interest in USD for a given symbol.

        해당 심볼의 USD 기준 미결제약정을 반환합니다.

        Args:
            symbol: The perpetual futures symbol (e.g., "BTC/USDT:USDT")
                    무기한 선물 심볼 (예: "BTC/USDT:USDT")

        Returns:
            Open interest in USD / USD 기준 미결제약정
        """
        pass
