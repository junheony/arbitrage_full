from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional


class OpportunityType(str, Enum):
    SPOT_CROSS = "spot_cross"
    SPOT_VS_PERP = "spot_vs_perp"
    PERP_PERP_SPREAD = "perp_perp_spread"
    FUNDING_ARB = "funding_arb"
    KIMCHI_PREMIUM = "kimchi_premium"


class MarketQuote(BaseModel):
    exchange: str
    venue_type: Literal["spot", "perp", "fx"]
    symbol: str
    base_asset: str
    quote_currency: str
    bid: float
    ask: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2


class OpportunityLeg(BaseModel):
    exchange: str
    venue_type: Literal["spot", "perp", "fx"]
    side: Literal["buy", "sell"]
    symbol: str
    price: float
    quantity: float


class Opportunity(BaseModel):
    id: str
    type: OpportunityType
    symbol: str
    spread_bps: float
    expected_pnl_pct: float
    notional: float
    timestamp: datetime
    description: str
    legs: list[OpportunityLeg]
    metadata: Optional[dict[str, Any]] = None
