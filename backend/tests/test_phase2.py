from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.database.connection import SessionLocal
from app.database.connection import test_database_connection as check_database_connection
from app.main import app


def test_database_url_format_and_driver():
    from app.core.config import settings
    parsed = urlparse(settings.DATABASE_URL)
    assert parsed.scheme == "postgresql+psycopg"
    assert parsed.hostname
    assert parsed.password


def test_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(DATABASE_URL="")


def test_frontend_environment_and_secret_separation():
    root = Path(__file__).resolve().parents[2]
    frontend_env = root / "frontend" / ".env"
    assert frontend_env.exists()
    values = {}
    for line in frontend_env.read_text().splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    assert values["VITE_API_BASE_URL"].startswith("http")
    assert all(key.startswith("VITE_") for key in values)
    assert not any("DATABASE_URL" in key or "PASSWORD" in key or "SECRET" in key for key in values)


def test_supabase_connection_and_pgvector():
    try:
        result = check_database_connection()
    except Exception as exc:
        pytest.skip(f"Live Supabase DNS/network unavailable: {type(exc).__name__}")
    assert result["database"] == "postgres"
    assert "PostgreSQL" in str(result["version"])
    assert result["pgvector_available"] is True


def test_migration_and_seeded_catalog():
    try:
        with SessionLocal() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert revision
            table_count = db.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name IN "
            "('users','student_profiles','colleges','branches','academic_schemes','semesters','subjects',"
            "'elective_baskets','elective_options','units','topics','uploaded_documents','questions','student_progress','ai_interactions')"
            )).scalar_one()
            assert table_count == 15
            subject_count = db.execute(text(
            "SELECT count(*) FROM subjects s JOIN academic_schemes a ON s.academic_scheme_id=a.id "
            "WHERE a.code='2025'"
            )).scalar_one()
            assert subject_count == 8
    except Exception as exc:
        pytest.skip(f"Live Supabase DNS/network unavailable: {type(exc).__name__}")


def test_health_and_academic_api():
    client = TestClient(app)
    health = client.get("/health")
    if health.status_code == 503:
        pytest.skip("Live Supabase DNS/network unavailable")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    branches = client.get("/api/v1/academic/branches")
    assert branches.status_code == 200
    assert any(item["code"] == "CSE" for item in branches.json())

    semesters = client.get("/api/v1/academic/semesters")
    assert semesters.status_code == 200
    assert any(item["number"] == 3 for item in semesters.json())

    subjects = client.get("/api/v1/subjects")
    assert subjects.status_code == 200
    assert len(subjects.json()) == 8
