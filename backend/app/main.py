from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.api.ws import router as ws_router
from app.config import settings
from app.services.scheduler import CaptureScheduler
from app.services.ws_manager import ws_manager

capture_scheduler = CaptureScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure storage directories exist
    for subdir in ("screenshots", "thumbnails", "archives", "diffs"):
        (settings.storage_path / subdir).mkdir(parents=True, exist_ok=True)

    # Start scheduler + WebSocket listener
    await capture_scheduler.start()
    await ws_manager.start()

    yield

    # Shutdown
    await ws_manager.stop()
    await capture_scheduler.stop()


app = FastAPI(
    title="Snapshift",
    description="Visual web monitoring — automated full-page captures with page archives",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
