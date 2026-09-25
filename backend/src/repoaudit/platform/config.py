"""configuration management for repoaudit."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Prefer backend/.env (not monorepo root)
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_BACKEND_ROOT / ".env")
load_dotenv()  # fallback: process cwd / inherited env

_CONFIG_DIR = Path.home() / ".repoaudit"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

GEMINI_FLASH_LITE = "openrouter/google/gemini-2.5-flash-lite"

# shortcuts so users don't have to type full provider/model strings
MODEL_ALIASES = {
    "deepseek": "deepseek/deepseek-chat",
    "flash": GEMINI_FLASH_LITE,
    "flash-lite": GEMINI_FLASH_LITE,
    "gemini-flash": GEMINI_FLASH_LITE,
    "gemini-flash-lite": GEMINI_FLASH_LITE,
    "gemma": "openrouter/google/gemma-4-26b-a4b-it:free",
    "nemotron": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    "nemotron-super": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    "laguna": "openrouter/poolside/laguna-s-2.1:free",
    "laguna-xs": "openrouter/poolside/laguna-xs-2.1:free",
    "north-code": "openrouter/cohere/north-mini-code:free",
    "qwen": "openrouter/qwen/qwen-2.5-7b-instruct:free",
    "llama": "openrouter/meta-llama/llama-3.2-3b-instruct:free",
    "opus": "anthropic/claude-opus-4-6",
    "claude": "anthropic/claude-sonnet-4-6",
    "gpt": "gpt-5.4",
    "gpt-mini": "gpt-5.4-mini",
    "gemini": GEMINI_FLASH_LITE,
}


def resolve_model(name: str) -> str:
    return MODEL_ALIASES.get(name, name)


@dataclass
class Config:
    model: str = GEMINI_FLASH_LITE
    model_lite: str = GEMINI_FLASH_LITE
    model_complex: str = GEMINI_FLASH_LITE

    # Per-operation overrides (default to empty string to fall back to model_lite / model_complex / model)
    model_summary: str = ""
    model_wiki: str = ""
    model_planner: str = ""
    model_investigator: str = ""
    model_audit: str = ""
    model_chat: str = ""

    api_key: str = ""
    api_base: str = ""
    language: str = "en"
    max_file_size: int = 200 * 1024  # 200 KB
    max_files: int = 1000
    output_dir: str = "./wiki"
    concurrency: int = 5

    def get_operation_models(self) -> dict[str, str]:
        return {
            "summary": resolve_model(self.model_summary or self.model_lite or self.model),
            "wiki": resolve_model(self.model_wiki or self.model_complex or self.model),
            "planner": resolve_model(self.model_planner or self.model_complex or self.model),
            "investigator": resolve_model(self.model_investigator or self.model_complex or self.model),
            "audit": resolve_model(self.model_audit or self.model_complex or self.model),
            "chat": resolve_model(self.model_chat or self.model_lite or self.model),
        }

    @classmethod
    def load(cls) -> Config:
        """Load config from file, then override with env vars."""
        data: dict = {}
        if _CONFIG_FILE.exists():
            try:
                data = json.loads(_CONFIG_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        cfg = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

        # env overrides
        if val := os.getenv("REPOAUDIT_MODEL") or os.getenv("DEFAULT_MODEL"):
            cfg.model = val
        if val := os.getenv("MODEL_LITE"):
            cfg.model_lite = val
        if val := os.getenv("MODEL_COMPLEX"):
            cfg.model_complex = val
        if val := os.getenv("MODEL_SUMMARY"):
            cfg.model_summary = val
        if val := os.getenv("MODEL_WIKI"):
            cfg.model_wiki = val
        if val := os.getenv("MODEL_PLANNER"):
            cfg.model_planner = val
        if val := os.getenv("MODEL_INVESTIGATOR"):
            cfg.model_investigator = val
        if val := os.getenv("MODEL_AUDIT"):
            cfg.model_audit = val
        if val := os.getenv("MODEL_CHAT"):
            cfg.model_chat = val

        if val := os.getenv("REPOAUDIT_API_KEY"):
            cfg.api_key = val
        if val := os.getenv("REPOAUDIT_API_BASE"):
            cfg.api_base = val
        if val := os.getenv("REPOAUDIT_LANG"):
            cfg.language = val

        # fall back to common provider keys
        if not cfg.api_key:
            for env_key in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
                if val := os.getenv(env_key):
                    cfg.api_key = val
                    break

        cfg.model = resolve_model(cfg.model)
        cfg.model_lite = resolve_model(cfg.model_lite)
        cfg.model_complex = resolve_model(cfg.model_complex)
        cfg.model_summary = resolve_model(cfg.model_summary) if cfg.model_summary else ""
        cfg.model_wiki = resolve_model(cfg.model_wiki) if cfg.model_wiki else ""
        cfg.model_planner = resolve_model(cfg.model_planner) if cfg.model_planner else ""
        cfg.model_investigator = resolve_model(cfg.model_investigator) if cfg.model_investigator else ""
        cfg.model_audit = resolve_model(cfg.model_audit) if cfg.model_audit else ""
        cfg.model_chat = resolve_model(cfg.model_chat) if cfg.model_chat else ""
        return cfg

    def save(self) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "model": self.model,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "language": self.language,
        }
        # don't persist empty values
        data = {k: v for k, v in data.items() if v}
        _CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
