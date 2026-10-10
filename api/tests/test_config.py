import pytest

from app.config import Settings


def test_heroku_postgres_scheme_is_rewritten_for_psycopg2() -> None:
    settings = Settings(database_url="postgres://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg2://u:p@host:5432/db"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg2://u:p@host:5432/db",
        "postgresql://u:p@host:5432/db",
    ],
)
def test_sqlalchemy_urls_are_left_alone(url: str) -> None:
    assert Settings(database_url=url).database_url == url


def test_only_the_scheme_is_rewritten() -> None:
    settings = Settings(database_url="postgres://u:postgres://x@host:5432/db")
    assert settings.database_url == "postgresql+psycopg2://u:postgres://x@host:5432/db"
