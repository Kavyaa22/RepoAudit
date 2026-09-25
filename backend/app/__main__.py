"""Allow ``python -m app`` with safe reload dirs (app/ + src/ only)."""

from app.main import run

if __name__ == "__main__":
    run(reload=True)
