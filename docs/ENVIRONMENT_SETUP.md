# Environment Setup

## Backend

Configure `backend/.env` from `backend/.env.example`. Required values:

- `DATABASE_URL`: PostgreSQL psycopg URL.
- `FRONTEND_URL`: allowed CORS origin.
- `APP_ENV`, `APP_DEBUG`, `APP_SECRET_KEY`.
- Optional future AI values: `AI_API_KEY`, `OLLAMA_BASE_URL`.

## Frontend

Copy `frontend/.env.example` to `frontend/.env`. It contains only public `VITE_*` values.

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_APP_NAME=PYQVERSE
VITE_APP_ENV=development
```

Never place database passwords or private API keys in frontend files.

## Supabase Auth

Backend placeholders:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
ADMIN_BOOTSTRAP_TOKEN=
```

Frontend placeholders:

```text
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

Custom SMTP is deferred until deployment. Supabase default email restrictions apply in development.

## Start

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cd frontend
npm run dev
```
