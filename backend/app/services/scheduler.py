import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database import async_session
from app.models import CaptureJob, JobStatus, MonitoredURL
from app.services.notifier import notify_job_update

logger = logging.getLogger(__name__)

SCHEDULE_MAP = {
    "every_1h": IntervalTrigger(hours=1),
    "every_2h": IntervalTrigger(hours=2),
    "every_6h": IntervalTrigger(hours=6),
    "every_12h": IntervalTrigger(hours=12),
    "daily": CronTrigger(hour=6, minute=0),
    "weekly": CronTrigger(day_of_week="mon", hour=6, minute=0),
    "monthly": CronTrigger(day=1, hour=6, minute=0),
}


def _parse_schedule(schedule: str):
    if schedule in SCHEDULE_MAP:
        return SCHEDULE_MAP[schedule]
    # Try to parse "every_Xh" pattern
    if schedule.startswith("every_") and schedule.endswith("h"):
        try:
            hours = int(schedule[6:-1])
            return IntervalTrigger(hours=hours)
        except ValueError:
            pass
    return SCHEDULE_MAP["daily"]


class CaptureScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def start(self):
        await self._load_all_urls()
        self._add_retention_job()
        self.scheduler.start()
        logger.info("Scheduler started")

    def _add_retention_job(self):
        from app.services.retention import cleanup_old_captures

        self.scheduler.add_job(
            cleanup_old_captures,
            trigger=CronTrigger(hour=3, minute=0),
            id="retention_cleanup",
            replace_existing=True,
            misfire_grace_time=7200,
        )
        logger.info("Retention cleanup job scheduled (daily at 3:00 AM)")

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _load_all_urls(self):
        async with async_session() as db:
            result = await db.execute(
                select(MonitoredURL).where(MonitoredURL.is_active == True)
            )
            urls = result.scalars().all()
            for url in urls:
                self._add_job(url)
            logger.info(f"Loaded {len(urls)} URL schedules")

    def _add_job(self, url: MonitoredURL):
        job_id = f"url_{url.id}"
        trigger = _parse_schedule(url.schedule)
        self.scheduler.add_job(
            self._create_capture_jobs,
            trigger=trigger,
            id=job_id,
            args=[str(url.id)],
            replace_existing=True,
            misfire_grace_time=3600,
        )

    def add_url(self, url: MonitoredURL):
        self._add_job(url)
        logger.info(f"Added schedule for {url.url} ({url.schedule})")

    def remove_url(self, url_id: str):
        job_id = f"url_{url_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed schedule for URL {url_id}")

    def update_url(self, url: MonitoredURL):
        if url.is_active:
            self._add_job(url)
        else:
            self.remove_url(str(url.id))

    @staticmethod
    async def _create_capture_jobs(url_id: str):
        import uuid as uuid_mod

        async with async_session() as db:
            url = await db.get(MonitoredURL, uuid_mod.UUID(url_id))
            if not url or not url.is_active:
                return

            # One job per URL (browsertrix captures the full page)
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
            logger.info(f"Created capture job for {url.url}")
