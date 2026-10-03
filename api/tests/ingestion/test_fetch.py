import pytest
from curl_cffi.requests.exceptions import ConnectionError, InvalidURL, Timeout

from ingestion.fetch import FetchError, fetch
from tests.conftest import FakeResponse, FakeSession


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


def test_fetch_retries_on_connection_error():
    """Not just Timeout - any network-level RequestException is retryable."""
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ConnectionError("reset")
        return FakeResponse(200, text="ok")

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    response = fetch(session, "/content/whatever", rate_limit_seconds=0.1, sleep=sleep)

    assert response.status_code == 200
    assert attempts["count"] == 2


def test_fetch_invalid_url_is_not_retried():
    """A non-retryable RequestException (e.g. a malformed path) fails fast
    with a FetchError instead of burning max_attempts on something that
    will never succeed, unlike Timeout/ConnectionError above."""
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        raise InvalidURL("bad url")

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError) as exc_info:
        fetch(session, "/content/bad path", rate_limit_seconds=0.1, sleep=sleep)

    assert attempts["count"] == 1
    assert isinstance(exc_info.value.__cause__, InvalidURL)


def test_fetch_403_is_not_retried():
    """403 (most likely our TLS-impersonated session getting bot-blocked) is
    a hard fail like 404, not a transient error - retrying identically
    won't fix it, so don't burn max_attempts * rate_limit_seconds on it."""
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        return FakeResponse(403, text="Forbidden by WAF")

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="not retried") as exc_info:
        fetch(session, "/content/blocked", rate_limit_seconds=0.1, sleep=sleep)

    assert attempts["count"] == 1
    assert "Forbidden by WAF" in str(exc_info.value)


def test_fetch_401_is_not_retried():
    def handler(path: str, params: dict | None) -> FakeResponse:
        return FakeResponse(401)

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="not retried"):
        fetch(session, "/content/blocked", rate_limit_seconds=0.1, sleep=sleep)


def test_fetch_429_retries_then_raises_fetch_error():
    """429 (rate limited) is a transient failure worth retrying, unlike
    401/403/404 - confirms the hard-fail set doesn't over-broadly cover
    every non-2xx status."""

    def handler(path: str, params: dict | None) -> FakeResponse:
        return FakeResponse(429)

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="after 3 attempts") as exc_info:
        fetch(
            session,
            "/content/limited",
            rate_limit_seconds=0.1,
            max_attempts=3,
            sleep=sleep,
        )
    assert "429" in str(exc_info.value.__cause__)


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
        fetch(
            session,
            "/content/broken",
            rate_limit_seconds=0.1,
            max_attempts=3,
            sleep=sleep,
        )
