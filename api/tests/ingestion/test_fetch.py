import pytest
from curl_cffi.requests.exceptions import Timeout

from ingestion.fetch import FetchError, fetch
from tests.ingestion.conftest import FakeResponse, FakeSession


def _fake_sleep_recorder():
    calls: list[float] = []

    def sleep(seconds: float) -> None:
        calls.append(seconds)

    return sleep, calls


def test_fetch_retries_on_5xx_then_succeeds():
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return FakeResponse(503)
        return FakeResponse(200, text="ok")

    session = FakeSession(handler)
    sleep, sleep_calls = _fake_sleep_recorder()

    response = fetch(session, "/content/whatever", rate_limit_seconds=1.0, sleep=sleep)

    assert response.status_code == 200
    assert attempts["count"] == 3
    assert sleep_calls == [1.0, 1.0, 1.0]


def test_fetch_retries_on_timeout():
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise Timeout("slow")
        return FakeResponse(200, text="ok")

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    response = fetch(session, "/content/whatever", rate_limit_seconds=0.1, sleep=sleep)

    assert response.status_code == 200
    assert attempts["count"] == 2


def test_fetch_404_is_not_retried():
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        return FakeResponse(404)

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="404"):
        fetch(session, "/content/gone", rate_limit_seconds=0.1, sleep=sleep)

    assert attempts["count"] == 1


def test_fetch_gives_up_after_max_attempts():
    def handler(path: str, params: dict | None) -> FakeResponse:
        return FakeResponse(503)

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="after 3 attempts"):
        fetch(session, "/content/broken", rate_limit_seconds=0.1, max_attempts=3, sleep=sleep)
