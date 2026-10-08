import logging

import pytest
from curl_cffi.requests.exceptions import ConnectionError, InvalidURL, Timeout

from ingestion.fetch import RETRY_WAITS, FetchError, fetch
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
    # The rate limit before the first attempt, then the first two retry waits.
    assert sleep_calls == [1.0, 5.0, 30.0]


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
    with a FetchError instead of burning retries on something that
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
    won't fix it, so don't wait out the retries on it."""
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
            retry_waits=(0.1, 0.1),
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
            retry_waits=(0.1, 0.1),
            sleep=sleep,
        )


def test_fetch_gives_up_after_every_retry_by_default():
    def handler(path: str, params: dict | None) -> FakeResponse:
        return FakeResponse(504, text="Target not responding")

    session = FakeSession(handler)
    sleep, sleep_calls = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="after 4 attempts"):
        fetch(session, "/content/down", rate_limit_seconds=1.0, sleep=sleep)

    assert len(session.calls) == len(RETRY_WAITS) + 1
    assert sleep_calls == [1.0, *RETRY_WAITS]


def test_fetch_never_waits_less_than_the_rate_limit_before_a_retry():
    def handler(path: str, params: dict | None) -> FakeResponse:
        return FakeResponse(503)

    session = FakeSession(handler)
    sleep, sleep_calls = _fake_sleep_recorder()

    with pytest.raises(FetchError):
        fetch(
            session,
            "/content/down",
            rate_limit_seconds=2.0,
            retry_waits=(0.5, 10.0),
            sleep=sleep,
        )

    assert sleep_calls == [2.0, 2.0, 10.0]


def test_fetch_logs_each_retry(caplog):
    attempts = {"count": 0}

    def handler(path: str, params: dict | None) -> FakeResponse:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return FakeResponse(504, text="Target not responding")
        if attempts["count"] == 2:
            raise Timeout("slow")
        return FakeResponse(200, text="ok")

    session = FakeSession(handler)
    sleep, _ = _fake_sleep_recorder()

    with caplog.at_level(logging.WARNING, logger="ingestion.fetch"):
        fetch(
            session,
            "/taxonomy/term/8588",
            params={"page": 412},
            rate_limit_seconds=1.0,
            sleep=sleep,
        )

    assert [r.getMessage() for r in caplog.records] == [
        "/taxonomy/term/8588?page=412: returned 504: Target not responding; "
        "retrying in 5s (retry 1 of 3)",
        "/taxonomy/term/8588?page=412: Timeout: slow; retrying in 30s (retry 2 of 3)",
    ]


def test_fetch_logs_nothing_on_a_first_try_success(caplog):
    session = FakeSession(lambda path, params: FakeResponse(200, text="ok"))
    sleep, _ = _fake_sleep_recorder()

    with caplog.at_level(logging.WARNING, logger="ingestion.fetch"):
        fetch(session, "/content/fine", rate_limit_seconds=1.0, sleep=sleep)

    assert caplog.records == []


def test_fetch_hard_failures_wait_only_the_rate_limit():
    session = FakeSession(lambda path, params: FakeResponse(404))
    sleep, sleep_calls = _fake_sleep_recorder()

    with pytest.raises(FetchError, match="not retried"):
        fetch(session, "/content/gone", rate_limit_seconds=1.0, sleep=sleep)

    assert sleep_calls == [1.0]


def test_fetch_reports_an_error_pages_title():
    page = (
        "<!DOCTYPE HTML><html><head><title>504 - Target not responding</title>"
        "</head><body><h1>Gateway</h1></body></html>"
    )
    session = FakeSession(lambda path, params: FakeResponse(504, text=page))
    sleep, _ = _fake_sleep_recorder()

    with pytest.raises(FetchError) as exc_info:
        fetch(session, "/content/down", rate_limit_seconds=0, sleep=sleep)

    assert str(exc_info.value.__cause__) == (
        "/content/down returned 504: 504 - Target not responding"
    )
