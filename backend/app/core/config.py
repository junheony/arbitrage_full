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

    # Database / 데이터베이스
    database_url: str = Field(
        default="",
        description="PostgreSQL connection URL (leave empty for SQLite).",
    )
    secret_key: str = Field(
        default="CHANGE_THIS_IN_PRODUCTION_MINIMUM_32_CHARS",
        description="Secret key for JWT and encryption (min 32 chars).",
    )

    # Market universe / 마켓 구성
    trading_symbols: list[str] = Field(
        default_factory=lambda: [
            # Top market cap coins tradeable on Binance, OKX, Upbit, Bithumb
            "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "DOGE/USDT",
            "ADA/USDT", "LINK/USDT", "AVAX/USDT", "DOT/USDT", "TRX/USDT",
            "BCH/USDT", "NEAR/USDT", "SHIB/USDT", "UNI/USDT", "APT/USDT",
            "HBAR/USDT", "FIL/USDT", "ARB/USDT", "ATOM/USDT", "ETC/USDT",
            "XLM/USDT", "ALGO/USDT", "AAVE/USDT", "ENA/USDT", "PEPE/USDT",
            "SUI/USDT", "ONDO/USDT", "WLD/USDT", "RENDER/USDT", "POL/USDT",
            "BONK/USDT", "CHZ/USDT", "PENDLE/USDT", "SEI/USDT", "BLUR/USDT",
            "FLOW/USDT", "ENS/USDT", "SAND/USDT", "MANA/USDT", "AXS/USDT",
            "OP/USDT", "EGLD/USDT", "GRT/USDT", "ASTR/USDT", "PYTH/USDT",
            "JUP/USDT", "ZRO/USDT", "W/USDT", "TIA/USDT", "ARKM/USDT",
            "CELO/USDT", "GMT/USDT", "INJ/USDT", "THETA/USDT", "BIGTIME/USDT",
            "MASK/USDT",
        ],
        description="Symbols to monitor across connectors (56 coins from top 100 market cap).",
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

    # Perpetual futures connectors / 무기한 선물 커넥터
    enable_perp_connectors: bool = Field(
        default=True,
        description="Enable perpetual futures connectors for funding arbitrage.",
    )
    enable_binance_perp: bool = Field(
        default=True,
        description="Enable Binance perpetual futures connector.",
    )
    enable_bybit_perp: bool = Field(
        default=True,
        description="Enable Bybit perpetual futures connector.",
    )
    enable_hyperliquid_perp: bool = Field(
        default=False,
        description="Enable Hyperliquid DEX perpetual connector (also powers based.one).",
    )
    enable_lighter_perp: bool = Field(
        default=False,
        description="Enable Lighter DEX perpetual connector.",
    )
    enable_edgex_perp: bool = Field(
        default=False,
        description="Enable EdgeX perpetual connector.",
    )
    min_open_interest_usd: float = Field(
        default=100_000.0,
        description="Minimum open interest in USD to consider for perp arbitrage.",
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
    min_kimchi_allocation_pct: float = Field(
        5.0,
        description="Minimum allocation % to show kimchi premium opportunity (filters noise).",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
