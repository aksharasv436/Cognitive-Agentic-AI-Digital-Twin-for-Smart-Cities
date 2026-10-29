import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

        async with self._lock:
            self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        async with self._lock:
            connections = list(self.active_connections)

        disconnected = []

        async def send(connection):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        await asyncio.gather(
            *(send(connection) for connection in connections)
        )

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


async def broadcast_all(views, events, stats, incidents, sim_state):
    for sector_id, view in views.items():
        await manager.broadcast({
            "type": "TELEMETRY_UPDATE",
            "data": view,
        })

    await manager.broadcast({
        "type": "STATE",
        "data": {
            "analytics": stats,
            "incidents": incidents,
            "events": events,
            "sim": sim_state,
        },
    })