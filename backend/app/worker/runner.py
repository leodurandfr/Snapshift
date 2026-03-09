import asyncio
import logging
import signal
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import CaptureJob, JobStatus, MonitoredURL
from app.services.capture_orchestrator import CaptureOrchestrator
from app.services.notifier import notify_job_update
from app.services.storage import LocalStorage

logger = logging.getLogger(__name__)

JOB_TIMEOUT = settings.browsertrix_time_limit + 180  # capture + overhead
STALE_JOB_MINUTES = 20  # jobs RUNNING longer than this are considered stuck


class Worker:
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._running = False
        self._storage = LocalStorage(settings.storage_path)
        self._orchestrator = CaptureOrchestrator(self._storage)

    async def start(self):
        logger.info("Worker starting...")
        self._running = True

        await self._recover_stale_jobs()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)

        logger.info("Worker ready, polling for jobs")
        while self._running:
            try:
                processed = await self._poll_and_execute()
                if not processed:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(self.poll_interval)

        logger.info("Worker stopped")

    def _shutdown(self):
        logger.info("Shutdown signal received")
        self._running = False

    async def _poll_and_execute(self) -> bool:
        async with async_session() as db:
            job = await self._claim_job(db)
            if not job:
                return False

            logger.info(f"Processing job {job.id} for URL {job.url_id}")

            try:
                url = await db.get(MonitoredURL, job.url_id)
                if not url:
                    await self._fail_job(db, job, "Monitored URL not found")
                    return True

                await asyncio.wait_for(
                    self._orchestrator.execute(db=db, url=url),
                    timeout=JOB_TIMEOUT,
                )
                await self._complete_job(db, job)

            except asyncio.TimeoutError:
                logger.error(f"Job {job.id} timed out after {JOB_TIMEOUT}s")
                await self._fail_job(db, job, f"Capture timed out after {JOB_TIMEOUT}s")

            except Exception as e:
                logger.error(f"Job {job.id} failed: {e}")
                await self._fail_job(db, job, str(e)[:500])

            return True

    async def _claim_job(self, db: AsyncSession) -> CaptureJob | None:
        result = await db.execute(
            select(CaptureJob)
            .where(CaptureJob.status == JobStatus.PENDING)
            .order_by(CaptureJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await notify_job_update(db, job)
        await db.commit()
        await db.refresh(job)
        return job

    async def _complete_job(self, db: AsyncSession, job: CaptureJob):
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        await notify_job_update(db, job)
        await db.commit()

    async def _fail_job(self, db: AsyncSession, job: CaptureJob, error: str):
        job.status = JobStatus.FAILED
        job.completed_at = datetime.utcnow()
        job.error_message = error
        await notify_job_update(db, job)
        await db.commit()

    async def _recover_stale_jobs(self):
        """Fail jobs stuck in RUNNING/PENDING for too long (worker crash recovery)."""
        cutoff = datetime.utcnow() - timedelta(minutes=STALE_JOB_MINUTES)
        async with async_session() as db:
            result = await db.execute(
                select(CaptureJob)
                .where(
                    CaptureJob.status.in_([JobStatus.RUNNING, JobStatus.PENDING]),
                    CaptureJob.created_at < cutoff,
                )
            )
            stale_jobs = result.scalars().all()
            for job in stale_jobs:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error_message = "Recovered: job was stuck (worker crash or timeout)"
                await notify_job_update(db, job)
            if stale_jobs:
                await db.commit()
                logger.warning(f"Recovered {len(stale_jobs)} stale job(s)")
