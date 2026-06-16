from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
