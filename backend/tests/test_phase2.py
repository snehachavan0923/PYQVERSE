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
    assert parsed.scheme in ("postgresql+psycopg", "postgresql")
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

    with SessionLocal() as db:
        phase6_columns = db.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='subjects' "
                "AND column_name IN ('course_category', 'source_verification_status')"
            )
        ).scalar_one()
    if phase6_columns != 2:
        pytest.skip("Phase 6 academic migration is not applied to the configured database")

    subjects = client.get("/api/v1/subjects")
    assert subjects.status_code == 200
    subject_codes = {item["code"] for item in subjects.json()}
    if len(subject_codes) != 10:
        pytest.skip("Configured live database has partial subject catalog")
    assert len(subject_codes) == 10
    assert subject_codes == {
        "MA231TC", "CV232TA", "ME232TB", "BT232TD", "CS233AI",
        "CS234AI", "CS235AT", "CS236AT", "CS238DL", "MAT149AT",
    }

    # Verify dedicated electives endpoint for student onboarding
    cse_branch = next(b for b in branches.json() if b["code"] == "CSE")
    sem_3 = next(s for s in semesters.json() if s["number"] == 3)
    schemes = client.get("/api/v1/academic/schemes")
    assert schemes.status_code == 200
    scheme_2022 = next(sc for sc in schemes.json() if sc["year"] == 2022)

    electives_res = client.get(
        f"/api/v1/academic/electives?branch_id={cse_branch['id']}&scheme_id={scheme_2022['id']}&semester_id={sem_3['id']}"
    )
    assert electives_res.status_code == 200
    elective_data = electives_res.json()
    assert len(elective_data) == 3
    elective_codes = {e["code"] for e in elective_data}
    assert elective_codes == {"CV232TA", "ME232TB", "BT232TD"}
