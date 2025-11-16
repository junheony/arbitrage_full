from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)

from app.models.opportunity import Opportunity, OpportunityType
from app.services.opportunity_engine import OpportunityEngine

router = APIRouter()


def _resolve_engine_from_app(app: any) -> OpportunityEngine:
    engine: OpportunityEngine | None = getattr(app.state, "opportunity_engine", None)
    if engine is None:
        detail = "Opportunity engine not initialised / 기회 엔진이 초기화되지 않았습니다"
        raise HTTPException(
            status_code=503,
            detail=detail,
        )
    return engine


def get_engine(request: Request) -> OpportunityEngine:
    return _resolve_engine_from_app(request.app)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok / 정상"}


@router.get("/opportunities", response_model=list[Opportunity])
async def list_opportunities(
    request: Request,
    limit: int = 25,
) -> list[Opportunity]:
    engine = get_engine(request)
    return engine.latest()[:limit]


@router.get("/signals/tether-bot", response_model=list[Opportunity])
async def tether_bot_signals(
    request: Request,
    limit: int = 5,
) -> list[Opportunity]:
    engine = get_engine(request)
    signals = [opp for opp in engine.latest() if opp.type == OpportunityType.KIMCHI_PREMIUM]
    return signals[:limit]


async def _serve_opportunities_ws(
    websocket: WebSocket, engine: OpportunityEngine
) -> None:
    await websocket.accept()
    queue = engine.subscribe()
    try:
        await websocket.send_json([opp.model_dump(mode='json') for opp in engine.latest()])
        while True:
            opportunities = await queue.get()
            await websocket.send_json([opp.model_dump(mode='json') for opp in opportunities])
    except WebSocketDisconnect:
        pass
    finally:
        engine.unsubscribe(queue)
        await _drain_queue(queue)


@router.websocket("/ws/opportunities")
async def opportunities_ws(
    websocket: WebSocket,
) -> None:
    try:
        engine = _resolve_engine_from_app(websocket.app)
    except HTTPException as exc:
        raise WebSocketException(code=403, reason=exc.detail) from exc
    await _serve_opportunities_ws(websocket, engine)


async def _drain_queue(queue: asyncio.Queue[list[Opportunity]]) -> None:
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break


@router.websocket("/ws")
async def opportunities_ws_alias(
    websocket: WebSocket,
) -> None:
    try:
        engine = _resolve_engine_from_app(websocket.app)
    except HTTPException as exc:
        raise WebSocketException(code=403, reason=exc.detail) from exc
    await _serve_opportunities_ws(websocket, engine)
