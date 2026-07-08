"""Environment-based application settings.

Every external dependency is optional. With an empty environment the app runs
fully offline: SQLite for storage, the deterministic reasoning engine for the
agent, and pure-Python retrieval for the knowledge base.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    # Default: local SQLite file. Set DATABASE_URL to a Postgres/Supabase DSN
    # to point the exact same code at a hosted database.
    database_url: str = "sqlite:///./northwind.db"

    # --- LLM provider ---
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_judge_model: str = "claude-sonnet-5"

    # --- Retrieval ---
    cohere_api_key: str | None = None

    # --- Voice (STT / TTS) ---
    deepgram_api_key: str | None = None
    openai_api_key: str | None = None      # Whisper STT fallback
    elevenlabs_api_key: str | None = None

    # --- Tracing ---
    langsmith_api_key: str | None = None
    langsmith_project: str = "northwind-support-ai"

    # --- Business rules ---
    refund_approval_threshold_cents: int = 15000
    return_window_days: int = 30
    session_cost_cap_usd: float = 0.50
    max_tool_iterations: int = 6

    # Reliability safeguards (Track A). When on, irreversible actions require the
    # agent to have verified eligibility first — enforced at the tool layer, not
    # just requested in the prompt. Toggle off to A/B the reliability benchmark.
    reliability_fixes: bool = True

    # --- App ---
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_available(self) -> bool:
        """True when a real Claude key is configured."""
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
