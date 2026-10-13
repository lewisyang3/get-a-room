from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "local"
    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/get_a_room"
    )
    allowed_origins: str = "http://localhost:3000"

    scraper_rate_limit_seconds: float = 1.0
    scraper_timeout_seconds: float = 30.0
    scraper_user_agent: str = "GetARoomBot/0.1 (+https://github.com/lewisyang3/get-a-room; polite academic-schedule scraper)"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg2_scheme(cls, value: str) -> str:
        """Accepts Heroku's `postgres://` URL, which SQLAlchemy 2 rejects."""
        if value.startswith("postgres://"):
            return "postgresql+psycopg2://" + value.removeprefix("postgres://")
        return value

    @property
    def allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
