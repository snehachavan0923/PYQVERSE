from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_database_connection() -> dict[str, object]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT version() AS version, current_database() AS database")
        ).mappings().one()
        vector_row = connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') AS available")
        ).mappings().one()
        return {**dict(row), "pgvector_available": bool(vector_row["available"])}
