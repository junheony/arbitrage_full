from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.connectors.binance_spot import BinanceSpotConnector
from app.connectors.bithumb_spot import BithumbSpotConnector
from app.connectors.ccxt_spot import CCXTSpotConnector
from app.connectors.fx_rates import KRWUSDForexConnector
from app.connectors.okx_spot import OkxSpotConnector
from app.connectors.simulated import SimulatedConnector
from app.connectors.upbit_spot import UpbitSpotConnector
from app.core.config import get_settings
from app.services.opportunity_engine import OpportunityEngine


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title=settings.app_name)

# Allow local frontend dev server during MVP.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
async def startup_event() -> None:
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

    connectors.append(
        SimulatedConnector(
            name="bybit",
            venue_type="perp",
            base_spreads_bps=8,
            symbols=settings.trading_symbols,
        )
    )

    if settings.enable_ccxt_spot:
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
