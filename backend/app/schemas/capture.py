import uuid
from datetime import datetime

from pydantic import BaseModel


class CaptureResponse(BaseModel):
    id: uuid.UUID
    url_id: uuid.UUID
    viewport_label: str
    viewport_width: int
    viewport_height: int
    image_path: str | None
    thumbnail_path: str | None
    archive_path: str | None
    archive_size: int | None
    diff_image_path: str | None
    diff_score: float | None
    file_size: int | None
    captured_at: datetime
    status: str
    error_message: str | None

    model_config = {"from_attributes": True}


class CaptureListResponse(BaseModel):
    items: list[CaptureResponse]
    total: int
