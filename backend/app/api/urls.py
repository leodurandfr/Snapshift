import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AuthToken, DbSession
from app.config import settings
from app.models import Capture, CaptureJob, JobStatus, MonitoredURL, Tag
from app.schemas.job import JobResponse
from app.schemas.url import URLCreate, URLListResponse, URLResponse, URLUpdate
from app.services.notifier import notify_job_update
from app.services.storage import LocalStorage

router = APIRouter(prefix="/urls", tags=["urls"])


def _url_to_response(url: MonitoredURL, last_capture: Capture | None = None) -> URLResponse:
    return URLResponse(
        id=url.id,
        url=str(url.url),
        label=url.label,
        viewports=url.viewports,
        schedule=url.schedule,
        full_page=url.full_page,
        archive_enabled=url.archive_enabled,
        dismiss_cookies=url.dismiss_cookies,
        change_threshold=url.change_threshold,
        is_active=url.is_active,
        created_at=url.created_at,
        updated_at=url.updated_at,
        tags=url.tags,
        last_capture_at=last_capture.captured_at if last_capture else None,
        last_capture_status=last_capture.status.value if last_capture else None,
        last_thumbnail=last_capture.thumbnail_path if last_capture else None,
    )


@router.get("", response_model=URLListResponse)
async def list_urls(
    db: DbSession,
    _token: AuthToken,
    tag: str | None = Query(default=None, description="Filter by tag name"),
    search: str | None = Query(default=None, description="Search in URL or label"),
    is_active: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(MonitoredURL).options(selectinload(MonitoredURL.tags))

    if tag:
        query = query.join(MonitoredURL.tags).where(Tag.name == tag)
    if search:
        query = query.where(
            MonitoredURL.url.ilike(f"%{search}%") | MonitoredURL.label.ilike(f"%{search}%")
        )
    if is_active is not None:
        query = query.where(MonitoredURL.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch with pagination
    query = query.order_by(MonitoredURL.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    urls = result.scalars().unique().all()

    # Get last capture for each URL
    items = []
    for url in urls:
        last_capture_q = (
            select(Capture)
            .where(Capture.url_id == url.id)
            .order_by(Capture.captured_at.desc())
            .limit(1)
        )
        last_capture = (await db.execute(last_capture_q)).scalar_one_or_none()
        items.append(_url_to_response(url, last_capture))

    return URLListResponse(items=items, total=total)


@router.post("", response_model=URLResponse, status_code=status.HTTP_201_CREATED)
async def create_url(data: URLCreate, db: DbSession, _token: AuthToken):
    # Check for duplicate URL
    existing = await db.execute(
        select(MonitoredURL).where(MonitoredURL.url == str(data.url))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="URL already monitored")

    # Resolve tags
    tags = []
    if data.tag_ids:
        for tag_id in data.tag_ids:
            tag = await db.get(Tag, tag_id)
            if not tag:
                raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
            tags.append(tag)

    url = MonitoredURL(
        url=str(data.url),
        label=data.label,
        viewports=[v.model_dump() for v in data.viewports],
        schedule=data.schedule,
        full_page=data.full_page,
        archive_enabled=data.archive_enabled,
        dismiss_cookies=data.dismiss_cookies,
        change_threshold=data.change_threshold,
        tags=tags,
    )
    db.add(url)
    await db.commit()
    await db.refresh(url)
    return _url_to_response(url)


@router.get("/{url_id}", response_model=URLResponse)
async def get_url(url_id: uuid.UUID, db: DbSession, _token: AuthToken):
    result = await db.execute(
        select(MonitoredURL).options(selectinload(MonitoredURL.tags)).where(MonitoredURL.id == url_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    last_capture_q = (
        select(Capture)
        .where(Capture.url_id == url.id)
        .order_by(Capture.captured_at.desc())
        .limit(1)
    )
    last_capture = (await db.execute(last_capture_q)).scalar_one_or_none()
    return _url_to_response(url, last_capture)


@router.put("/{url_id}", response_model=URLResponse)
async def update_url(url_id: uuid.UUID, data: URLUpdate, db: DbSession, _token: AuthToken):
    result = await db.execute(
        select(MonitoredURL).options(selectinload(MonitoredURL.tags)).where(MonitoredURL.id == url_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle tags separately
    tag_ids = update_data.pop("tag_ids", None)
    if tag_ids is not None:
        tags = []
        for tag_id in tag_ids:
            tag = await db.get(Tag, tag_id)
            if not tag:
                raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
            tags.append(tag)
        url.tags = tags

    # Handle viewports (convert to dicts)
    if "viewports" in update_data and update_data["viewports"] is not None:
        update_data["viewports"] = [v.model_dump() for v in update_data["viewports"]]

    for field, value in update_data.items():
        setattr(url, field, value)

    await db.commit()
    await db.refresh(url)
    return _url_to_response(url)


@router.delete("/{url_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_url(url_id: uuid.UUID, db: DbSession, _token: AuthToken):
    url = await db.get(MonitoredURL, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    # Delete capture files from storage before DB cascade removes the records
    result = await db.execute(select(Capture).where(Capture.url_id == url_id))
    captures = result.scalars().all()
    storage = LocalStorage(settings.storage_path)
    for capture in captures:
        for path in (capture.image_path, capture.thumbnail_path, capture.archive_path, capture.diff_image_path):
            if path:
                try:
                    await storage.delete_file(path)
                except Exception:
                    pass

    await db.delete(url)
    await db.commit()


@router.get("/{url_id}/jobs", response_model=list[JobResponse])
async def list_jobs(
    url_id: uuid.UUID,
    db: DbSession,
    _token: AuthToken,
    status: str | None = Query(default=None, description="Filter by status (pending, running, completed, failed)"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List recent capture jobs for a URL."""
    url = await db.get(MonitoredURL, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    query = select(CaptureJob).where(CaptureJob.url_id == url_id)
    if status:
        query = query.where(CaptureJob.status == JobStatus(status))
    query = query.order_by(CaptureJob.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{url_id}/capture-now", response_model=list[JobResponse])
async def capture_now(url_id: uuid.UUID, db: DbSession, _token: AuthToken):
    result = await db.execute(
        select(MonitoredURL).where(MonitoredURL.id == url_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    # One job per URL (browsertrix captures the full page independently of viewport)
    job = CaptureJob(
        url_id=url.id,
        viewport_label="Archive",
        viewport_width=0,
        viewport_height=0,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.flush()
    await notify_job_update(db, job)
    await db.commit()
    await db.refresh(job)
    return [job]
