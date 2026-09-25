"""Application settings loaded from environment."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _normalize_origin(origin: str) -> str:
    origin = origin.strip().rstrip("/")
    if not origin:
        return ""
    # Railway template vars often inject bare domains (no scheme).
    if "://" not in origin:
        origin = f"https://{origin}"
    return origin


class Settings(BaseSettings):
    """Central settings for the FastAPI app (core infrastructure only)."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RepoAudit"
    app_version: str = "0.4.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    cors_origins: str | list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "https://repository-audit.up.railway.app",
        ]
    )
    cors_origin_regex: str = r"https://.*\.up\.railway\.app"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        """Accept JSON list, comma-separated origins, or single domain (Railway/Render-friendly)."""
        if value is None or value == "":
            return [
                "http://localhost:5173",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "https://repository-audit.up.railway.app",
            ]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                import json

                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [_normalize_origin(str(item)) for item in parsed if str(item).strip()]
                except Exception:  # noqa: BLE001
                    pass
            # Fallback for comma-separated or single origin string
            cleaned = text.strip("[]'\"")
            return [
                origin
                for part in cleaned.split(",")
                if (origin := _normalize_origin(part))
            ]
        if isinstance(value, (list, tuple)):
            return [_normalize_origin(str(item)) for item in value if str(item).strip()]
        return []

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Auth / JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    auth_disabled: bool = False

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_redirect_uri: str = "http://localhost:8001/api/v1/github/oauth/callback"
    github_oauth_frontend_redirect: str = "http://localhost:5173/dashboard"
    github_oauth_scopes: str = "read:user,user:email,repo"

    # LLM (shared AI helpers)
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    anthropic_api_key: str = ""
    default_model: str = Field(default="openrouter/google/gemini-2.5-flash-lite", validation_alias="DEFAULT_MODEL")
    model_lite: str = Field(default="openrouter/google/gemini-2.5-flash-lite", validation_alias="MODEL_LITE")
    model_complex: str = Field(default="openrouter/google/gemini-2.5-flash-lite", validation_alias="MODEL_COMPLEX")
    model_summary: str = Field(default="", validation_alias="MODEL_SUMMARY")
    model_wiki: str = Field(default="", validation_alias="MODEL_WIKI")
    model_planner: str = Field(default="", validation_alias="MODEL_PLANNER")
    model_investigator: str = Field(default="", validation_alias="MODEL_INVESTIGATOR")
    model_audit: str = Field(default="", validation_alias="MODEL_AUDIT")
    model_chat: str = Field(default="", validation_alias="MODEL_CHAT")

    # Runtime paths
    workspace_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "workspace")
    knowledge_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "knowledge")
    logs_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "logs")
    temp_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "temp")
    data_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "data")


def get_settings() -> Settings:
    return Settings()
