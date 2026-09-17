import time
from collections.abc import Callable
from typing import Protocol

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from app.config import get_settings

BASE_URL = "https://classes.berkeley.edu"


class FetchError(Exception):
    """A URL could not be fetched after retries, or returned a hard failure."""


class SectionResponse(Protocol):
    status_code: int
    text: str


class SectionSession(Protocol):
    def get(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> SectionResponse: ...


def build_session() -> requests.Session:
    """A curl_cffi session impersonating a real browser's TLS handshake.

    classes.berkeley.edu blocks plain Python HTTP clients (httpx, requests)
    with a 403 based on their TLS fingerprint alone - confirmed this isn't a
    User-Agent or rate-limiting check, curl and curl-impersonate clients get
    through immediately and repeatedly with no special spacing needed. The
    User-Agent header is still overridden with our own identifiable value
    (below the TLS layer, so it doesn't affect the fingerprint) as a matter
    of being a polite, identifiable scraper, not to evade detection.
    """
    settings = get_settings()
    return requests.Session(
        base_url=BASE_URL,
        headers={"User-Agent": settings.scraper_user_agent},
        timeout=settings.scraper_timeout_seconds,
        impersonate="chrome",
    )


def fetch(
    session: SectionSession,
    path: str,
    *,
    rate_limit_seconds: float,
    params: dict[str, str | int] | None = None,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> SectionResponse:
    """GETs `path`, sleeping `rate_limit_seconds` before every attempt.

    Retries transient failures - network/timeout errors and any non-404
    4xx/5xx response - up to `max_attempts` times. A 404 is treated as a
    hard, non-retryable failure - it means the section disappeared between
    enumeration and fetch, not a blip worth retrying.
    """
    last_error: Exception | None = None
    for _attempt in range(1, max_attempts + 1):
        sleep(rate_limit_seconds)
        try:
            response = session.get(path, params=params)
        except RequestException as exc:
            last_error = exc
            continue

        if response.status_code == 404:
            raise FetchError(f"{path} returned 404 (not retried)")
        if response.status_code >= 400:
            last_error = FetchError(f"{path} returned {response.status_code}")
            continue

        return response

    raise FetchError(f"failed to fetch {path} after {max_attempts} attempts") from last_error
