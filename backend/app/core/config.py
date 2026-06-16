from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # API Keys
    finnhub_api_key: str = ""
    finnhub_base_url: str = "https://finnhub.io/api/v1"

    # App
    app_name: str = "Market Pulse Intelligence"
    debug: bool = False

    # HTTP Client
    request_timeout_seconds: int = 10
    max_retries: int = 3

    # AI Provider  ("anthropic" | "openai" | "gemini")
    ai_provider: Literal["anthropic", "openai", "gemini"] = "gemini"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Default models — overridable via env
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-1.5-flash"
    ai_max_tokens: int = 2048

    # Analysis cache
    ai_cache_ttl_seconds: int = 3600   # 1 hour
    ai_cache_max_size: int = 512

    # Autonomous event scheduler
    scheduler_enabled: bool = True
    scheduler_poll_interval: int = 60       # seconds between Finnhub polls
    scheduler_seen_ttl: int = 86_400        # 24 h — how long to remember event IDs
    scheduler_seen_max: int = 5_000         # max tracked IDs in memory


@lru_cache
def get_settings() -> Settings:
    return Settings()
