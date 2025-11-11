from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.api.portfolio_routes import router as portfolio_router
from app.api.execution_routes import router as execution_router
from app.db.init_db import init_db
from app.connectors.binance_spot import BinanceSpotConnector
from app.connectors.bithumb_spot import BithumbSpotConnector
from app.connectors.fx_rates import KRWUSDForexConnector
from app.connectors.okx_spot import OkxSpotConnector
from app.connectors.simulated import SimulatedConnector
from app.connectors.upbit_spot import UpbitSpotConnector
from app.connectors.binance_perp import BinancePerpConnector
from app.connectors.bybit_perp import BybitPerpConnector
from app.connectors.hyperliquid_perp import HyperliquidPerpConnector
from app.connectors.lighter_perp import LighterPerpConnector
from app.connectors.edgex_perp import EdgeXPerpConnector
from app.core.config import get_settings
from app.services.opportunity_engine import OpportunityEngine

# Optional CCXT import / 선택적 CCXT 임포트
try:
    from app.connectors.ccxt_spot import CCXTSpotConnector
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("CCXT not available, ccxt_spot connector disabled / CCXT 사용 불가")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title=settings.app_name)

# Allow local frontend dev server during MVP.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth")
app.include_router(portfolio_router, prefix="/api/portfolio")
app.include_router(execution_router, prefix="/api/execution")


@app.on_event("startup")
async def startup_event() -> None:
    # Initialize database tables / 데이터베이스 테이블 초기화
    try:
        await init_db()
        logger.info("Database initialized. / 데이터베이스 초기화됨.")
    except Exception as exc:
        logger.warning("Database initialization skipped: %s / DB 초기화 생략: %s", exc, exc)

    connectors = []

    if settings.enable_public_rest_spot:
        connectors.extend(
            [
                BinanceSpotConnector(settings.trading_symbols),
                OkxSpotConnector(settings.trading_symbols),
                UpbitSpotConnector(settings.trading_symbols),
                BithumbSpotConnector(settings.trading_symbols),
            ]
        )
    else:
        connectors.extend(
            [
                SimulatedConnector(
                    name="binance",
                    venue_type="spot",
                    base_spreads_bps=5,
                    symbols=settings.trading_symbols,
                ),
                SimulatedConnector(
                    name="okx",
                    venue_type="spot",
                    base_spreads_bps=6,
                    symbols=settings.trading_symbols,
                ),
                SimulatedConnector(
                    name="upbit",
                    venue_type="spot",
                    base_spreads_bps=7,
                    symbols=settings.trading_symbols,
                ),
            ]
        )

    connectors.append(KRWUSDForexConnector())

    # Add perpetual futures connectors / 무기한 선물 커넥터 추가
    if settings.enable_perp_connectors:
        if settings.enable_binance_perp:
            try:
                connectors.append(BinancePerpConnector(settings.trading_symbols))
                logger.info("Binance perpetual futures connector enabled / 바이낸스 무기한 선물 커넥터 활성화")
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to initialize Binance perp connector: %s", exc)

        if settings.enable_bybit_perp:
            try:
                connectors.append(BybitPerpConnector(settings.trading_symbols))
                logger.info("Bybit perpetual futures connector enabled / 바이빗 무기한 선물 커넥터 활성화")
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to initialize Bybit perp connector: %s", exc)

        if settings.enable_hyperliquid_perp:
            try:
                connectors.append(HyperliquidPerpConnector(settings.trading_symbols))
                logger.info("Hyperliquid DEX perpetual connector enabled (also powers based.one) / 하이퍼리퀴드 DEX 무기한 선물 커넥터 활성화 (based.one도 지원)")
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to initialize Hyperliquid perp connector: %s", exc)

        if settings.enable_lighter_perp:
            try:
                connectors.append(LighterPerpConnector(settings.trading_symbols))
                logger.info("Lighter DEX perpetual connector enabled / Lighter DEX 무기한 선물 커넥터 활성화")
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to initialize Lighter perp connector: %s", exc)

        if settings.enable_edgex_perp:
            try:
                connectors.append(EdgeXPerpConnector(settings.trading_symbols))
                logger.info("EdgeX perpetual connector enabled / EdgeX 무기한 선물 커넥터 활성화")
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to initialize EdgeX perp connector: %s", exc)
    else:
        # Add simulated perpetual connector for demo / 데모용 시뮬레이션 무기한 선물 커넥터 추가
        connectors.append(
            SimulatedConnector(
                name="bybit",
                venue_type="perp",
                base_spreads_bps=8,
                symbols=settings.trading_symbols,
            )
        )

    if settings.enable_ccxt_spot and CCXT_AVAILABLE:
        for exchange_id in settings.ccxt_spot_exchanges:
            try:
                connectors.append(CCXTSpotConnector(exchange_id, settings.trading_symbols))
                logger.info(
                    "CCXT spot connector enabled: %s / CCXT 현물 커넥터 활성화: %s",
                    exchange_id,
                    exchange_id,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to initialise CCXT connector %s: %s / CCXT 커넥터 %s 초기화 실패: %s",
                    exchange_id,
                    exc,
                    exchange_id,
                    exc,
                )
    elif settings.enable_ccxt_spot and not CCXT_AVAILABLE:
        logger.warning("CCXT is enabled in settings but not installed / 설정에서 활성화되었지만 설치되지 않음")
    engine = OpportunityEngine(connectors=connectors)
    await engine.start()
    app.state.opportunity_engine = engine
    logger.info("Opportunity engine initialised. / 기회 엔진 초기화 완료.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    engine: OpportunityEngine | None = getattr(app.state, "opportunity_engine", None)
    if engine:
        await engine.stop()
        logger.info("Opportunity engine stopped. / 기회 엔진이 중지되었습니다.")
