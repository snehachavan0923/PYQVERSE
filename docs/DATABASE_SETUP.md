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
.venv/bin/alembic current
.venv/bin/alembic upgrade head
.venv/bin/python -m app.services.seed_academic_catalog
```

Check the current revision first; run `alembic upgrade head` only after confirming the deployed revision is represented in this checkout. The seed command above is a static dry run. Apply catalog records only with the explicit `--apply` flag and appropriate approval.

Before upgrading an existing database, confirm its current Alembic revision is present in this checkout. The configured database currently reports `b6d2f8a1c947`, which is not represented by the repository migration history; reconcile that history before running `alembic upgrade head`.

Never run destructive database commands. Schema changes must use additive Alembic migrations.
