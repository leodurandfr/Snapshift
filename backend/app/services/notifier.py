import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CaptureJob


def job_to_dict(job: CaptureJob) -> dict:
    return {
        "id": str(job.id),
        "url_id": str(job.url_id),
        "viewport_label": job.viewport_label,
        "viewport_width": job.viewport_width,
        "viewport_height": job.viewport_height,
        "status": job.status.value if hasattr(job.status, "value") else job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }


async def notify_job_update(db: AsyncSession, job: CaptureJob) -> None:
    """Send a PostgreSQL NOTIFY with the job state. Call before db.commit()
    so the notification is delivered atomically with the status change."""
    payload = json.dumps({"type": "job_update", "job": job_to_dict(job)})
    await db.execute(text("SELECT pg_notify('job_updates', :payload)"), {"payload": payload})
