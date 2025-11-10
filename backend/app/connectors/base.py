from __future__ import annotations

import abc
from typing import Sequence

from app.models.opportunity import MarketQuote


class MarketConnector(abc.ABC):
    """Abstract base class for market data connectors. / 마켓 데이터 커넥터를 위한 추상 기본 클래스."""

    name: str

    @abc.abstractmethod
    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        """Return the latest tradable quotes for this venue. / 해당 거래소의 최신 호가를 반환합니다."""
