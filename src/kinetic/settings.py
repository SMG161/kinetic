"""Process-wide configuration, read from environment variables or a .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KINETIC_", env_file=".env")

    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
