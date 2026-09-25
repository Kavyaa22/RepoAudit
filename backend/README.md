# RepoAudit backend

Python FastAPI backend for RepoAudit. Local package sources live under `src/repoaudit` and `app/`.

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[web]"

# Preferred dev server (reloads only app/ + src/, never workspace/)
python run_dev.py
```

Do **not** use bare `python -m uvicorn app.main:app --reload` — that watches `workspace/` clones and can wipe in-memory state / fight with scan.
