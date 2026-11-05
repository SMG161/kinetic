"""Process-wide configuration, read from environment variables or a .env file."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KINETIC_", env_file=".env")

    database_url: str
    # Signs access tokens. Anyone holding it can mint a token for any person.
    jwt_secret: str = Field(min_length=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()
