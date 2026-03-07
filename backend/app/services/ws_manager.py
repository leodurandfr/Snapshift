import asyncio
import logging

import asyncpg
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._pg_conn: asyncpg.Connection | None = None
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        self._pg_conn = await asyncpg.connect(dsn)
        await self._pg_conn.add_listener("job_updates", self._on_pg_notify)
        logger.info("WebSocket manager listening on job_updates channel")

    async def stop(self) -> None:
        if self._pg_conn:
            await self._pg_conn.remove_listener("job_updates", self._on_pg_notify)
            await self._pg_conn.close()
            self._pg_conn = None
        logger.info("WebSocket manager stopped")

    def _on_pg_notify(
        self,
        conn: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        task = asyncio.create_task(self._broadcast(payload))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WebSocket client disconnected (%d total)", len(self._connections))

    async def _broadcast(self, message: str) -> None:
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._connections -= dead


ws_manager = WebSocketManager()
