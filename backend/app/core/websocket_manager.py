"""
WebSocket Connection Manager — real-time delivery layer for Market Pulse Intelligence.

Responsibilities
────────────────
  • Track active WebSocket connections (connect / disconnect lifecycle)
  • Broadcast AnalysisResult payloads to all connected clients
  • Prune stale connections automatically during broadcast
  • Provide a FastAPI-injectable singleton via get_connection_manager()

Thread-safety notes
───────────────────
  asyncio.Lock guards all mutations to _active.  Broadcast takes a snapshot
  before iterating so the lock is not held during I/O, then re-acquires it
  only to remove stale entries.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Message protocol
# ─────────────────────────────────────────────────────────────────────────────

class WSMessageType(str, Enum):
    CONNECTION_ACK = "connection_ack"
    ANALYSIS_RESULT = "analysis_result"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    DISCONNECT = "disconnect"


class WSMessage(BaseModel):
    type: WSMessageType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict | None = None
    client_id: str | None = None
    message: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Connection manager
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages all active WebSocket connections for the platform."""

    def __init__(self) -> None:
        self._active: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> str:
        """Accept connection, register it, return the assigned client_id."""
        await websocket.accept()
        client_id = uuid.uuid4().hex[:8]
        async with self._lock:
            self._active[client_id] = websocket
        logger.info(
            "WS connect: client_id=%s  total=%d", client_id, len(self._active)
        )
        return client_id

    async def disconnect(self, client_id: str) -> None:
        """Remove client from active pool (idempotent)."""
        async with self._lock:
            self._active.pop(client_id, None)
        logger.info(
            "WS disconnect: client_id=%s  remaining=%d", client_id, len(self._active)
        )

    async def disconnect_all(self) -> None:
        """Close and remove every active connection (used during app shutdown)."""
        async with self._lock:
            ids = list(self._active.keys())
        for cid in ids:
            await self.disconnect(cid)

    # ── Messaging ─────────────────────────────────────────────────────────────

    async def send_to(self, client_id: str, message: dict) -> bool:
        """
        Send a JSON message to one specific client.

        Returns True on success, False if the client is gone or the send fails.
        """
        async with self._lock:
            ws = self._active.get(client_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except (WebSocketDisconnect, RuntimeError):
            await self.disconnect(client_id)
            return False

    async def broadcast(self, message: dict) -> dict[str, int]:
        """
        Broadcast a JSON-serialisable dict to all connected clients.

        Stale / broken connections are pruned automatically.
        Returns {"sent": N, "failed": M}.
        """
        async with self._lock:
            snapshot = list(self._active.items())

        sent, stale = 0, []
        for client_id, ws in snapshot:
            try:
                await ws.send_json(message)
                sent += 1
            except (WebSocketDisconnect, RuntimeError, Exception) as exc:
                logger.warning("Broadcast failed for %s: %s", client_id, exc)
                stale.append(client_id)

        if stale:
            async with self._lock:
                for cid in stale:
                    self._active.pop(cid, None)

        logger.debug("Broadcast: sent=%d failed=%d", sent, len(stale))
        return {"sent": sent, "failed": len(stale)}

    async def broadcast_message(self, msg: WSMessage) -> dict[str, int]:
        """Convenience wrapper that accepts a WSMessage object."""
        return await self.broadcast(msg.model_dump(mode="json"))

    # ── Introspection ─────────────────────────────────────────────────────────

    def connection_count(self) -> int:
        return len(self._active)

    def client_ids(self) -> list[str]:
        return list(self._active.keys())


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency factory
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_connection_manager() -> ConnectionManager:
    """
    Return the process-wide ConnectionManager singleton.

    Override via app.dependency_overrides[get_connection_manager] in tests
    to inject a fresh, isolated instance per test.
    """
    return ConnectionManager()
