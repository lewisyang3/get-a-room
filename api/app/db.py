from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# Fail fast if the database stops answering, rather than waiting on the OS's
# TCP timeout, so /ready returns 503 before a host's health check gives up.
# pool_pre_ping replaces pooled connections the database has closed, e.g. after
# Heroku Postgres maintenance, instead of failing a request on each one.
engine = create_engine(
    settings.database_url,
    connect_args={"connect_timeout": 5},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
