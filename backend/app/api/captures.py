import uuid

from fastapi import APIRouter, Body, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy import select, func

from app.api.deps import AuthToken, DbSession
from app.config import settings
from app.models import Capture, MonitoredURL
from app.schemas.capture import CaptureListResponse, CaptureResponse
from app.services.storage import LocalStorage

router = APIRouter(prefix="/captures", tags=["captures"])


@router.get("", response_model=CaptureListResponse)
async def list_captures(
    db: DbSession,
    _token: AuthToken,
    url_id: uuid.UUID | None = Query(default=None),
    viewport_label: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(Capture)
    if url_id:
        query = query.where(Capture.url_id == url_id)
    if viewport_label:
        query = query.where(Capture.viewport_label == viewport_label)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Capture.captured_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    captures = result.scalars().all()

    return CaptureListResponse(items=captures, total=total)


@router.get("/{capture_id}", response_model=CaptureResponse)
async def get_capture(capture_id: uuid.UUID, db: DbSession, _token: AuthToken):
    capture = await db.get(Capture, capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")
    return capture


@router.get("/{capture_id}/screenshot")
async def get_screenshot(capture_id: uuid.UUID, db: DbSession, _token: AuthToken):
    capture = await db.get(Capture, capture_id)
    if not capture or not capture.image_path:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    file_path = settings.storage_path / capture.image_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot file missing")

    return FileResponse(file_path, media_type="image/png")


@router.get("/{capture_id}/thumbnail")
async def get_thumbnail(capture_id: uuid.UUID, db: DbSession, _token: AuthToken):
    capture = await db.get(Capture, capture_id)
    if not capture or not capture.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    file_path = settings.storage_path / capture.thumbnail_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")

    return FileResponse(file_path, media_type="image/webp")


@router.get("/{capture_id}/archive")
async def get_archive(capture_id: uuid.UUID, db: DbSession, token: AuthToken):
    capture = await db.get(Capture, capture_id)
    if not capture or not capture.archive_path:
        raise HTTPException(status_code=404, detail="Archive not found")

    file_path = settings.storage_path / capture.archive_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archive file missing")

    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=f"capture-{capture.id}.wacz",
        headers={
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{capture_id}/archive-preview")
async def get_archive_preview(
    capture_id: uuid.UUID,
    db: DbSession,
    token: AuthToken,
):
    capture = await db.get(Capture, capture_id)
    if not capture or not capture.archive_path:
        raise HTTPException(status_code=404, detail="Archive not found")

    # Load original URL for ReplayWeb.page
    url_obj = await db.get(MonitoredURL, capture.url_id)
    original_url = url_obj.url if url_obj else ""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/replaywebpage@2.4.3/ui.js"></script>
<style>html,body{{margin:0;height:100%;overflow:hidden}}
replay-web-page{{display:block;width:100%;height:100%}}</style>
</head><body>
<replay-web-page source="/api/captures/{capture_id}/archive?token={token}"
  url="{original_url}" embed="replayonly" replayBase="/api/replay/">
</replay-web-page>
</body></html>"""
    return HTMLResponse(content=html)


@router.delete("/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capture(capture_id: uuid.UUID, db: DbSession, _token: AuthToken):
    capture = await db.get(Capture, capture_id)
    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    storage = LocalStorage(settings.storage_path)
    for path in (capture.image_path, capture.thumbnail_path, capture.archive_path, capture.diff_image_path):
        if path:
            try:
                await storage.delete_file(path)
            except Exception:
                pass

    await db.delete(capture)
    await db.commit()


@router.post("/delete-batch", status_code=status.HTTP_204_NO_CONTENT)
async def delete_captures_batch(
    db: DbSession,
    _token: AuthToken,
    capture_ids: list[uuid.UUID] = Body(..., embed=True),
):
    storage = LocalStorage(settings.storage_path)
    for cid in capture_ids:
        capture = await db.get(Capture, cid)
        if not capture:
            continue
        for path in (capture.image_path, capture.thumbnail_path, capture.archive_path, capture.diff_image_path):
            if path:
                try:
                    await storage.delete_file(path)
                except Exception:
                    pass
        await db.delete(capture)

    await db.commit()
