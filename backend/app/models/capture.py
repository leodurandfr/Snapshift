import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CaptureStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class Capture(Base):
    __tablename__ = "captures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitored_urls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    viewport_label: Mapped[str] = mapped_column(Text, nullable=False)
    viewport_width: Mapped[int] = mapped_column(Integer, nullable=False)
    viewport_height: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[CaptureStatus] = mapped_column(
        Enum(CaptureStatus), default=CaptureStatus.SUCCESS
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    monitored_url = relationship("MonitoredURL", back_populates="captures")
