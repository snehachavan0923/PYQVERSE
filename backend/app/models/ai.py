import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.database.base import Base


class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("student_profiles.id", ondelete="SET NULL"))
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(100))
    prompt_metadata: Mapped[dict | None] = mapped_column(JSONB)
    source_document_references: Mapped[list | None] = mapped_column(JSONB)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    prompt_text: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
