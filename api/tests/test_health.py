from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_the_database_answers(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class UnreachableSession:
    """Fails every query the way psycopg2 does when Postgres is down."""

    def execute(self, *args, **kwargs):
        raise OperationalError(
            "SELECT 1",
            {},
            Exception(
                'connection to server at "db.internal" (10.0.0.5), port 5432 '
                'failed: FATAL: password authentication failed for user "app"'
            ),
        )


def test_ready_is_503_without_details_when_the_database_fails() -> None:
    app.dependency_overrides[get_db] = UnreachableSession
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    # Exactly this, so the host and user in the error never reach the caller.
    assert response.json() == {"detail": "database unavailable"}
