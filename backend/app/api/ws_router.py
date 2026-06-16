"""
WebSocket router — client entry point for real-time market-pulse delivery.

Endpoints
─────────
  WS  /ws/market-pulse      Client connects and waits for AnalysisResult pushes
  GET /ws/status            Live connection stats for ops dashboards
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.websocket_manager import (
    ConnectionManager,
    WSMessage,
    WSMessageType,
    get_connection_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

ManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]


@router.websocket("/market-pulse")
async def market_pulse_ws(
    websocket: WebSocket,
    manager: ConnectionManager = Depends(get_connection_manager),
) -> None:
    """
    Persistent WebSocket channel for receiving real-time AnalysisResult payloads.

    On connect:  sends connection_ack with the assigned client_id.
    While open:  client may send any text (reserved for future subscription commands).
    On close:    client is removed from broadcast pool automatically.
    """
    client_id = await manager.connect(websocket)

    ack = WSMessage(
        type=WSMessageType.CONNECTION_ACK,
        client_id=client_id,
        message=f"Connected to Market Pulse Intelligence. Your client ID: {client_id}",
    )
    await websocket.send_json(ack.model_dump(mode="json"))

    try:
        while True:
            # Keep the connection alive; log any client-sent frames.
            # Future: parse JSON commands for per-currency-pair subscriptions.
            text = await websocket.receive_text()
            logger.debug("WS %s → server: %.120s", client_id, text)
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
        logger.info("WS %s disconnected gracefully", client_id)


@router.get("/status")
async def ws_status(manager: ManagerDep) -> dict:
    """Return live WebSocket connection stats."""
    return {
        "active_connections": manager.connection_count(),
        "client_ids": manager.client_ids(),
    }
