import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AdministratorBootstrapRecord(Base):
    __tablename__ = "administrator_bootstrap_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    supabase_auth_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    completed_at: Mapped[datetime | None] = mapped_column()
