import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import CaptureJob, JobStatus
from app.services.notifier import job_to_dict
from app.services.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    if token != settings.api_token:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(ws)

    # Send current active jobs so the client is immediately in sync
    try:
        async with async_session() as db:
            result = await db.execute(
                select(CaptureJob).where(
                    CaptureJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
                )
            )
            active_jobs = result.scalars().all()

            init_message = json.dumps(
                {
                    "type": "init",
                    "jobs": [job_to_dict(j) for j in active_jobs],
                }
            )
            await ws.send_text(init_message)

        # Keep connection alive — we only push, never read client messages
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)
