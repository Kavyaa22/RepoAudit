# Architecture

RepoAudit is a monorepo with a **Feature → Operation → Layer** convention.

## Layout

```
RepoAudit/
├── package.json              # Root scripts
├── docs/
├── scripts/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI factory → uvicorn app.main:app
│   │   ├── api/v1/           # System routes + router assembly
│   │   ├── core/             # Shared infrastructure (no business features)
│   │   ├── modules/          # Feature modules
│   │   ├── scheduler/
│   │   ├── workers/
│   │   └── events/
│   ├── src/repoaudit/        # Legacy engines (migrating into modules/)
│   ├── workspace/ | knowledge/ | logs/ | temp/
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── app/              # Feature pages (mirrors backend modules)
        ├── config/ | lib/ | services/ | providers/ | layouts/ | router/
        └── …
```

## Backend module convention

`modules/<feature>/<operation>/{router,service,schema,dto,validator}.py` plus `shared/`.

Mounting happens only in `app/api/v1/router.py`.

## Frontend feature convention

`src/app/<feature>/<operation>/{page.tsx, api/, services/, hooks/, ui/, types/, validation/, utils/}`.

## Run

```bash
# backend
cd backend && pip install -e ".[web]" && uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev

# or from root
npm run dev:backend
npm run dev
```

## Env files

- Backend: `backend/.env` (from `backend/.env.example`)
- Frontend: `frontend/.env` (from `frontend/.env.example`; `VITE_*` only)

Do not keep a root `.env`.
