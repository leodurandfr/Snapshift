import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.schemas.tag import TagResponse


def _normalize_url(v: str) -> str:
    v = v.strip()
    if v and not v.startswith(("http://", "https://")):
        v = f"https://{v}"
    return v


def _validate_url(v: str) -> str:
    """Validate that the URL has a resolvable-looking hostname (with a TLD)."""
    parsed = urlparse(v)
    if not parsed.scheme or parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    hostname = parsed.hostname
    if not hostname or "." not in hostname:
        raise ValueError(
            f"Invalid hostname '{hostname}': must include a domain extension "
            f"(e.g. '{hostname}.com')"
        )
    return v


class ViewportConfig(BaseModel):
    width: int = Field(..., ge=320, le=3840)
    height: int = Field(..., ge=480, le=2160)
    label: str = Field(..., min_length=1, max_length=50)


DEFAULT_VIEWPORTS = [
    ViewportConfig(width=1440, height=900, label="Desktop 1440"),
    ViewportConfig(width=390, height=844, label="Mobile 390"),
]


class URLCreate(BaseModel):
    url: str
    label: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, v: str) -> str:
        return _validate_url(_normalize_url(v))

    viewports: list[ViewportConfig] = Field(default_factory=lambda: DEFAULT_VIEWPORTS.copy())
    schedule: str = Field(default="daily", pattern=r"^(every_\d+h|daily|weekly|monthly)$")
    full_page: bool = True
    archive_enabled: bool = True
    dismiss_cookies: bool = True
    change_threshold: float = Field(default=0.02, ge=0.0, le=1.0)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)


class URLUpdate(BaseModel):
    url: str | None = None
    label: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_url(_normalize_url(v))
    viewports: list[ViewportConfig] | None = None
    schedule: str | None = Field(default=None, pattern=r"^(every_\d+h|daily|weekly|monthly)$")
    full_page: bool | None = None
    archive_enabled: bool | None = None
    dismiss_cookies: bool | None = None
    change_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None
    tag_ids: list[uuid.UUID] | None = None


class URLResponse(BaseModel):
    id: uuid.UUID
    url: str
    label: str | None
    viewports: list[ViewportConfig]
    schedule: str
    full_page: bool
    archive_enabled: bool
    dismiss_cookies: bool
    change_threshold: float
    is_active: bool
    created_at: datetime
    updated_at: datetime
    tags: list[TagResponse] = Field(default_factory=list)
    last_capture_id: uuid.UUID | None = None
    last_capture_at: datetime | None = None
    last_capture_status: str | None = None
    last_thumbnail: str | None = None

    model_config = {"from_attributes": True}


class URLListResponse(BaseModel):
    items: list[URLResponse]
    total: int
