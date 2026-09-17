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


# 404: the section disappeared between enumeration and fetch.
# 401/403: most likely our TLS-impersonated session getting bot-blocked
# (see build_session's docstring) - retrying identically won't fix that,
# so failing immediately avoids burning max_attempts * rate_limit_seconds
# on something that will never succeed.
_HARD_FAIL_STATUSES = {401, 403, 404}


def _error_detail(response: SectionResponse) -> str:
    snippet = " ".join(response.text.split())[:200]
    return f"{response.status_code}" + (f": {snippet}" if snippet else "")


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

    Retries transient failures - network/timeout errors and any 4xx/5xx not
    in _HARD_FAIL_STATUSES - up to `max_attempts` times. A hard-fail status
    raises immediately without retrying, since retrying identically won't
    fix it (see _HARD_FAIL_STATUSES).
    """
    last_error: Exception | None = None
    for _attempt in range(1, max_attempts + 1):
        sleep(rate_limit_seconds)
        try:
            response = session.get(path, params=params)
        except RequestException as exc:
            last_error = exc
            continue

        if response.status_code in _HARD_FAIL_STATUSES:
            raise FetchError(f"{path} returned {_error_detail(response)} (not retried)")
        if response.status_code >= 400:
            last_error = FetchError(f"{path} returned {_error_detail(response)}")
            continue

        return response

    raise FetchError(f"failed to fetch {path} after {max_attempts} attempts") from last_error
