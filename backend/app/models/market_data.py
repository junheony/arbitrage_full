from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FundingRate(BaseModel):
    """Perpetual futures funding rate data / 무기한 선물 펀딩비 데이터."""

    exchange: str = Field(description="Exchange name / 거래소 이름")
    symbol: str = Field(description="Symbol (e.g., BTC/USDT:USDT) / 심볼")
    base_asset: str = Field(description="Base asset (e.g., BTC) / 기초 자산")
    quote_currency: str = Field(description="Quote currency (e.g., USDT) / 결제 통화")

    # Funding rate data / 펀딩비 데이터
    funding_rate: float = Field(description="Current funding rate (decimal, e.g., 0.0001 = 0.01%) / 현재 펀딩비")
    funding_rate_8h: float = Field(description="Annualized to 8H for comparison / 8시간 기준으로 정규화")
    next_funding_time: Optional[datetime] = Field(default=None, description="Next funding timestamp / 다음 펀딩 시간")

    # Open Interest data / 미결제약정 데이터
    open_interest_usd: Optional[float] = Field(default=None, description="Open interest in USD / USD 기준 미결제약정")
    open_interest_contracts: Optional[float] = Field(default=None, description="Open interest in contracts / 계약 기준 미결제약정")

    # Price data / 가격 데이터
    mark_price: Optional[float] = Field(default=None, description="Mark price / 표시 가격")
    index_price: Optional[float] = Field(default=None, description="Index price / 지수 가격")

    # Metadata / 메타데이터
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    venue_type: Literal["perp"] = "perp"

    @property
    def funding_rate_apr(self) -> float:
        """Annualized funding rate / 연환산 펀딩비."""
        # Assuming funding happens every 8 hours (3 times per day)
        return self.funding_rate * 3 * 365


class PerpMarketData(BaseModel):
    """Combined perpetual market data with quote and funding / 무기한 선물 시장 데이터 (호가 + 펀딩비)."""

    exchange: str
    symbol: str
    base_asset: str
    quote_currency: str

    # Quote data / 호가 데이터
    bid: float
    ask: float
    mark_price: float

    # Funding data / 펀딩 데이터
    funding_rate: float
    funding_rate_8h: float
    next_funding_time: Optional[datetime] = None

    # Open Interest / 미결제약정
    open_interest_usd: float
    open_interest_contracts: Optional[float] = None

    # Metadata / 메타데이터
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    venue_type: Literal["perp"] = "perp"

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        """Bid-ask spread in basis points / 호가 스프레드 (bps)."""
        return ((self.ask - self.bid) / self.mid_price) * 10000
