# PYQVERSE

AI-powered academic preparation platform initially designed for RVCE students.

> **Status:** Phase 2 — Database foundation complete, subject to local DNS recovery.
> Authentication, dashboards, uploads, AI tutor and quizzes remain for later phases.

---

## Overview

PYQVERSE is a full-stack web platform that will help students prepare for
examinations using previous-year question papers and AI assistance. Phase 1 only
establishes the development environment: a React + Vite + TypeScript frontend and
a FastAPI backend, both runnable locally and verified.

---

## Technology Stack

### Frontend
| Tool | Version |
| --- | --- |
| React | 19 |
| Vite | 8 |
| TypeScript | 7 |
| Tailwind CSS | 4 (Vite plugin) |
| React Router | 7 |
| Axios | 1 |

### Backend
| Tool | Version |
| --- | --- |
| Python | 3.13 |
| FastAPI | 0.165 |
| Uvicorn | 0.54 |
| Pydantic | 2.14 |
| SQLAlchemy | 2.1 |
| python-dotenv | 1.2 |
| psycopg | 3.3 |

### Planned for future phases
PostgreSQL + pgvector, Docker, Ollama, cloud AI APIs, PyMuPDF, Tesseract OCR,
OpenCV.

---

## Prerequisites

| Requirement | Minimum | Check command |
| --- | --- | --- |
| Node.js | 20.19+ / 22.12+ | `node --version` |
| npm | 10+ | `npm --version` |
| Python | 3.11+ (3.13 tested) | `python3 --version` (macOS) / `python --version` (Windows) |
| pip | 23+ | `pip --version` |
| Git | 2.40+ | `git --version` |

Docker is **not required** for Phase 1.

---

## Installation

### 1. Clone / enter the project

```bash
cd PYQVERSE
```

### 2. Environment variables

Copy the example file and edit values as needed. Never commit the real `.env`.

**macOS / Linux**
```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

**Windows (PowerShell)**
```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
```

The root `.env` currently only needs `FRONTEND_URL` for CORS. Other values are
placeholders for future phases.

### 3. Frontend setup

**macOS / Linux**
```bash
cd frontend
npm install
```

**Windows (PowerShell)**
```powershell
cd frontend
npm install
```

### 4. Backend setup

**macOS / Linux**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks activation, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## Running the Project

Run the two servers in **separate terminals**.

### Frontend

**macOS / Linux**
```bash
cd frontend
npm run dev
```

**Windows (PowerShell)**
```powershell
cd frontend
npm run dev
```

Open <http://localhost:5173>. The home page shows:

```
PYQVERSE
Development Environment Ready
Frontend is running successfully.
```

Other frontend commands:

```bash
npm run build     # type-check + production build
npm run preview   # preview production build on :4173
npm run lint      # run oxlint
```

### Backend

**macOS / Linux**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Windows (PowerShell)**
```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend endpoints:

| Endpoint | URL | Expected |
| --- | --- | --- |
| Root | <http://localhost:8000/> | `{"message":"PYQVERSE API is running", ...}` |
| Health | <http://localhost:8000/health> | `{"status":"ok"}` |
| Swagger docs | <http://localhost:8000/docs> | Interactive API docs |
| OpenAPI JSON | <http://localhost:8000/openapi.json> | OpenAPI schema |

---

## Environment Variables

Defined in `.env.example`:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection string (future) | — |
| `AI_API_KEY` | Cloud AI API key (future) | — |
| `OLLAMA_BASE_URL` | Local Ollama server URL (future) | `http://localhost:11434` |
| `FRONTEND_URL` | Allowed CORS origin | `http://localhost:5173` |

Frontend-only variable (`frontend/.env`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Backend base URL for Axios | `http://localhost:8000` |

> `.env` files are git-ignored. Only `.env.example` files are committed.

---

## Folder Structure

```
PYQVERSE/
├── .env.example
├── .gitignore
├── README.md
├── docs/
├── frontend/
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig*.json
│   └── src/
│       ├── assets/
│       ├── components/
│       ├── hooks/
│       ├── layouts/
│       │   └── MainLayout.tsx
│       ├── pages/
│       │   └── Home.tsx
│       ├── routes/
│       │   └── AppRoutes.tsx
│       ├── services/
│       │   └── api.ts
│       ├── types/
│       │   └── index.ts
│       ├── utils/
│       ├── index.css
│       └── main.tsx
└── backend/
    ├── .venv/              (git-ignored)
    ├── requirements.txt
    └── app/
        ├── __init__.py
        ├── main.py
        ├── api/
        │   ├── __init__.py
        │   └── routes.py
        ├── core/
        │   ├── __init__.py
        │   └── config.py
        ├── database/
        ├── models/
        ├── schemas/
        └── services/
```

---

## Verification Checklist

**Frontend**
```bash
cd frontend
npm run build          # should finish with no errors
npm run dev            # then open http://localhost:5173
```
- [ ] Page displays "PYQVERSE", "Development Environment Ready", "Frontend is running successfully."
- [ ] Tailwind styles are applied (dark background, styled headings).

**Backend**
```bash
cd backend
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] <http://localhost:8000/docs> loads the Swagger UI

**Git**
```bash
git status
```
- [ ] `node_modules/`, `.venv/`, `dist/`, and `.env` files are not tracked.

---

## Git

The repository is initialized locally. To connect a remote later:

```bash
git remote add origin <your-repository-url>
git push -u origin main
```

Do not commit secrets. Use `.env.example` for shared defaults.

---

## Phase 1 Scope

Included: environment setup, project scaffolding, Tailwind/Router/Axios
configuration, FastAPI app with `/` and `/health`, environment templates, Git
initialization, and documentation.

Excluded (future phases): authentication, dashboards, question-paper uploads,
AI tutor, quizzes, syllabus management, database schemas, external AI API
integration, Docker, OCR/PDF pipelines.
