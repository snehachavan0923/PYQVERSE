# Database Setup

PYQVERSE uses Supabase PostgreSQL with SQLAlchemy and psycopg 3.

Create `backend/.env` with:

```text
DATABASE_URL=postgresql+psycopg://postgres.project-ref:URL_ENCODED_PASSWORD@pooler-host:5432/postgres
```

The repository uses the Session Pooler host because direct IPv6 DNS may be unavailable in local development.

Commands:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/python -m app.services.seed_academic_catalog
```

Never run destructive database commands. Schema changes must use Alembic migrations.
