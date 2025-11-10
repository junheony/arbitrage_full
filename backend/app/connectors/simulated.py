from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Iterable, Literal, Sequence

from app.connectors.base import MarketConnector
from app.models.opportunity import MarketQuote

class SimulatedConnector(MarketConnector):
    """Generates pseudo-random market quotes that resemble exchange feeds. / 거래소 시세를 모사하는 의사난수 호가를 생성합니다."""

    def __init__(
        self,
        name: str,
        venue_type: Literal["spot", "perp"],
        base_spreads_bps: float,
        symbols: Iterable[str],
    ):
        self.name = name
        self.venue_type = venue_type
        self._base_spread = base_spreads_bps / 10000
        self._last_timestamp = datetime.utcnow()
        self._symbols = list(symbols)

    async def fetch_quotes(self) -> Sequence[MarketQuote]:
        # Introduce slight delay to mimic network jitter.
        await asyncio.sleep(random.uniform(0.0, 0.05))
        quotes: list[MarketQuote] = []
        now = datetime.utcnow()
        for symbol in self._symbols:
            mid = self._generate_mid_price(symbol, now)
            spread = mid * self._base_spread
            variance = spread * random.uniform(0.5, 1.5)
            bid = mid - variance / 2
            ask = mid + variance / 2
            base, quote = symbol.split("/")
            quotes.append(
                MarketQuote(
                    exchange=self.name,
                    venue_type=self.venue_type,
                    symbol=symbol,
                    base_asset=base,
                    quote_currency=quote,
                    bid=round(bid, 2),
                    ask=round(ask, 2),
                    timestamp=now,
                )
            )
        self._last_timestamp = now
        return quotes

    def _generate_mid_price(self, symbol: str, now: datetime) -> float:
        seed = hash((self.name, symbol, now.replace(second=0, microsecond=0)))
        random.seed(seed)
        base_price = {
            "BTC/USDT": 63000,
            "ETH/USDT": 3200,
            "XRP/USDT": 0.58,
        }[symbol]
        drift = random.uniform(-0.01, 0.01) * base_price
        micro_noise = random.gauss(0, base_price * 0.001)
        # Introduce premium/discount bias per exchange to mimic 김프 (Korean premium) dynamics.
        bias = {
            "upbit": base_price * 0.004,  # Positive premium
            "binance": base_price * 0.0,
            "okx": base_price * -0.0015,
            "bybit": base_price * -0.0005,
            "bithumb": base_price * 0.003,
        }.get(self.name, 0.0)
        return base_price + drift + micro_noise + bias
