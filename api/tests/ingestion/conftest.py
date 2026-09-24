import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import Base
from app.models.models import Term, TermStatus


TERM_SOURCE_URL = "https://classes.berkeley.edu/taxonomy/term/8573"


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""


@dataclass
class FakeSession:
    """Duck-types the subset of curl_cffi.requests.Session that fetch() uses.

    Avoids depending on curl_cffi's real transport in tests - handler can
    return a FakeResponse or raise, exactly like a real session's .get().
    """

    handler: Callable[[str, dict | None], FakeResponse]
    calls: list[tuple[str, dict | None]] = field(default_factory=list)

    def get(self, path: str, params: dict | None = None) -> FakeResponse:
        self.calls.append((path, params))
        return self.handler(path, params)


def _test_database_url(app_url: str) -> URL:
    """The app's configured database, renamed with a `_test` suffix.

    Never reuses the app's own database name - drop_all() below must not
    be able to touch a developer's real dev database (same server, same
    credentials, different database), regardless of what DATABASE_URL is
    configured.
    """
    url = make_url(app_url)
    return url.set(database=f"{url.database}_test")


def _ensure_database_exists(url: URL) -> None:
    """Creates the test database on first run, if it doesn't exist yet.

    Connects to Postgres's built-in `postgres` maintenance database to
    issue CREATE DATABASE - the target database obviously can't be
    connected to for this until it exists. AUTOCOMMIT is required:
    Postgres refuses CREATE DATABASE inside a transaction block.
    """
    admin_engine = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def db_engine():
    """A real Postgres engine, against a dedicated `_test` database.

    Persistence logic (upserts, unique constraints, FK cascades) is
    Postgres-specific enough that SQLite would give false confidence.
    Uses `docker compose up db -d`'s server, but never the app's own
    configured database - see `_test_database_url`'s docstring for why.
    Skips cleanly (rather than failing) when the Postgres server itself
    isn't reachable, so `pytest` still works for anyone not running
    `docker compose up db` - unless REQUIRE_TEST_DB=1 (set in CI), where a
    skip would turn a broken database service into a green run.
    """
    test_url = _test_database_url(get_settings().database_url)
    try:
        _ensure_database_exists(test_url)
    except OperationalError as exc:
        message = f"Postgres not reachable at {test_url} - run `docker compose up db -d`: {exc}"
        if os.environ.get("REQUIRE_TEST_DB") == "1":
            pytest.fail(message)
        pytest.skip(message)

    engine = create_engine(test_url)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """A session against the real db, truncated after each test.

    Persistence code under test calls db.commit() itself, so a
    rollback-based transaction wrapper doesn't isolate tests - truncating
    every table after the test runs does instead.
    """
    # autoflush=False matches app/db.py's real SessionLocal - persistence
    # code is written flush-conscious (explicit db.flush() calls) because
    # production doesn't autoflush; using the default (True) here would
    # let a test pass on implicit-autoflush behavior that doesn't exist
    # in production.
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False)
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        with db_engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())


@pytest.fixture
def term(db: Session) -> Term:
    term = Term(
        name="Fall 2025",
        start_date=date(2025, 8, 27),
        end_date=date(2025, 12, 12),
        source_url=TERM_SOURCE_URL,
        status=TermStatus.ACTIVE,
    )
    db.add(term)
    db.commit()
    db.refresh(term)
    return term
