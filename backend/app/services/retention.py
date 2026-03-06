import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Capture
from app.services.storage import LocalStorage

logger = logging.getLogger(__name__)


async def cleanup_old_captures():
    storage = LocalStorage(settings.storage_path)
    cutoff = datetime.utcnow() - timedelta(days=settings.default_retention_days)

    async with async_session() as db:
        result = await db.execute(
            select(Capture).where(Capture.captured_at < cutoff)
        )
        old_captures = result.scalars().all()

        if not old_captures:
            logger.info("Retention cleanup: nothing to delete")
            return

        deleted = 0
        for capture in old_captures:
            # Delete associated files
            for path in (capture.image_path, capture.thumbnail_path, capture.archive_path, capture.diff_image_path):
                if path:
                    try:
                        await storage.delete_file(path)
                    except Exception as e:
                        logger.warning(f"Failed to delete file {path}: {e}")

            await db.delete(capture)
            deleted += 1

        await db.commit()
        logger.info(f"Retention cleanup: deleted {deleted} captures older than {settings.default_retention_days} days")
