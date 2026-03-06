import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.url import url_tags


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(7), default="#6366f1")

    # Relationships
    urls = relationship("MonitoredURL", secondary=url_tags, back_populates="tags", lazy="selectin")
