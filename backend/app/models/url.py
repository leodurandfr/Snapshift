import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

url_tags = Table(
    "url_tags",
    Base.metadata,
    Column("url_id", UUID(as_uuid=True), ForeignKey("monitored_urls.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class MonitoredURL(Base):
    __tablename__ = "monitored_urls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewports: Mapped[list] = mapped_column(
        JSONB,
        default=[
            {"width": 1440, "height": 900, "label": "Desktop 1440"},
            {"width": 390, "height": 844, "label": "Mobile 390"},
        ],
    )
    schedule: Mapped[str] = mapped_column(String(50), default="daily")
    full_page: Mapped[bool] = mapped_column(Boolean, default=True)
    archive_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dismiss_cookies: Mapped[bool] = mapped_column(Boolean, default=True)
    change_threshold: Mapped[float] = mapped_column(Float, default=0.02)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    tags = relationship("Tag", secondary=url_tags, back_populates="urls", lazy="selectin")
    captures = relationship("Capture", back_populates="monitored_url", lazy="dynamic", passive_deletes=True)
    jobs = relationship("CaptureJob", back_populates="monitored_url", lazy="dynamic", passive_deletes=True)
