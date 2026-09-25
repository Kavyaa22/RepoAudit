"""Database / migration notes.

Relational schema lives in ``migrations/`` (SQL applied via Supabase).
Immutable engine artifacts stay on disk under workspace/knowledge.
"""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

__all__ = ["MIGRATIONS_DIR"]
