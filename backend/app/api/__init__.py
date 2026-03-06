from fastapi import APIRouter

from app.api.captures import router as captures_router
from app.api.replay import router as replay_router
from app.api.tags import router as tags_router
from app.api.urls import router as urls_router

router = APIRouter(prefix="/api")
router.include_router(urls_router)
router.include_router(tags_router)
router.include_router(captures_router)
router.include_router(replay_router)
