import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Capture, CaptureStatus, MonitoredURL
from app.services.browsertrix import BrowsertrixService
from app.services.storage import StorageBackend
from app.services.thumbnail import generate_thumbnail

logger = logging.getLogger(__name__)


class CaptureOrchestrator:
    def __init__(self, storage: StorageBackend):
        self.storage = storage
        self.browsertrix = BrowsertrixService()

    async def execute(
        self,
        db: AsyncSession,
        url: MonitoredURL,
    ) -> Capture:
        capture_id = uuid.uuid4()
        crawl_dir = Path(settings.browsertrix_crawl_dir) / str(capture_id)
        capture = Capture(
            id=capture_id,
            url_id=url.id,
            viewport_label="Archive",
            viewport_width=0,
            viewport_height=0,
            status=CaptureStatus.SUCCESS,
        )

        try:
            result = await self.browsertrix.capture(url.url, capture_id)

            if not result:
                capture.status = CaptureStatus.ERROR
                capture.error_message = "Browsertrix capture failed"
                capture.captured_at = datetime.utcnow()
                db.add(capture)
                await db.commit()
                await db.refresh(capture)
                return capture

            try:
                # 1. Save WACZ archive
                archive_data = result.wacz_path.read_bytes()
                archive_rel_path = await self.storage.save_file(
                    "archives", f"{capture_id}.wacz", archive_data
                )
                capture.archive_path = archive_rel_path
                capture.archive_size = len(archive_data)

                # 2. Save screenshot + thumbnail if available
                if result.screenshot_path:
                    screenshot_data = result.screenshot_path.read_bytes()
                    image_path = await self.storage.save_file(
                        "screenshots", f"{capture_id}.png", screenshot_data
                    )
                    capture.image_path = image_path
                    capture.file_size = len(screenshot_data)

                    try:
                        thumb_data = generate_thumbnail(screenshot_data)
                        thumb_path = await self.storage.save_file(
                            "thumbnails", f"{capture_id}.webp", thumb_data
                        )
                        capture.thumbnail_path = thumb_path
                    except Exception as e:
                        logger.warning("Thumbnail generation failed: %s", e)

            finally:
                self.browsertrix.cleanup(crawl_dir, capture_id)

            capture.captured_at = datetime.utcnow()
            logger.info("Capture OK: %s", url.url)

        except Exception as e:
            capture.status = CaptureStatus.ERROR
            capture.error_message = str(e)[:500]
            logger.error("Capture failed: %s — %s", url.url, e)

        finally:
            # Always cleanup crawl dir, even on failure
            self.browsertrix.cleanup(crawl_dir, capture_id)

        db.add(capture)
        await db.commit()
        await db.refresh(capture)
        return capture
