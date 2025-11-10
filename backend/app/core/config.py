from functools import lru_cache
from typing import Literal, Sequence, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables. / 환경변수에서 불러오는 애플리케이션 설정."""

    app_name: str = "Arbitrage Backend / 아비트리지 백엔드"
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Data polling
    market_poll_interval: float = Field(3.0, description="Seconds between market snapshots.")
    max_spread_bps: float = Field(50.0, description="Ignore spreads wider than this (in bps).")

    # Simulation defaults
    simulated_base_notional: float = 10000.0
    simulated_fee_bps: float = 10.0

    # Market universe / 마켓 구성
    trading_symbols: list[str] = Field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
        description="Symbols to monitor across connectors.",
    )

    # Public REST spot connectors / 퍼블릭 REST 현물 커넥터
    enable_public_rest_spot: bool = Field(
        default=True,
        description="Enable Binance/OKX spot market data via public REST.",
    )
    public_rest_timeout: float = Field(3.0, description="HTTP timeout for public REST fetches.")

    enable_ccxt_spot: bool = Field(
        default=False,
        description="Enable real spot connectors via CCXT.",
    )
    ccxt_spot_exchanges: list[str] = Field(
        default_factory=lambda: ["binance", "okx"],
        description="CCXT exchange IDs for spot connectors.",
    )

    # Tether bot configuration / 테더봇 설정
    tether_total_equity_usd: float = Field(
        100000.0,
        description="Total equity considered for tether bot allocation (USD notional).",
    )
    tether_bot_curve: list[Tuple[float, float]] = Field(
        default_factory=lambda: [
            (-5.0, 1.0),
            (-2.0, 0.7),
            (-1.0, 0.5),
            (0.0, 0.2),
            (1.0, 0.05),
            (3.0, 0.0),
        ],
        description="Piecewise linear curve mapping premium % to allocation fraction.",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
