import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from curl_cffi import requests
from curl_cffi.requests.exceptions import (
    ConnectionError,
    DNSError,
    ProxyError,
    RequestException,
    SSLError,
    Timeout,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://classes.berkeley.edu"

# Seconds to wait before each retry. Together they ride out an outage of about
# 2.5 minutes - a few seconds of downtime used to fail a listing page, and with
# it a whole import hours in.
RETRY_WAITS = (5.0, 30.0, 120.0)

# Actual connectivity failures - worth retrying, since the same request may
# succeed a moment later. Anything else deriving from RequestException (e.g.
# InvalidURL, MissingSchema) is a permanent error that retrying won't fix.
_RETRYABLE_ERRORS = (Timeout, ConnectionError, SSLError, DNSError, ProxyError)


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
# so failing immediately avoids waiting out every retry
# on something that will never succeed.
_HARD_FAIL_STATUSES = {401, 403, 404}


_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _error_detail(response: SectionResponse) -> str:
    # An HTML error page's title says what went wrong ("504 - Target not
    # responding"); otherwise the start of the body.
    title = _TITLE_RE.search(response.text)
    text = title.group(1) if title else response.text
    snippet = " ".join(text.split())[:200]
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
    retry_waits: Sequence[float] = RETRY_WAITS,
    sleep: Callable[[float], None] = time.sleep,
) -> SectionResponse:
    """GETs `path`, sleeping `rate_limit_seconds` before the first attempt.

    Retries transient failures - _RETRYABLE_ERRORS and any 4xx/5xx not in
    _HARD_FAIL_STATUSES - once per entry in `retry_waits`, sleeping that long
    first (never less than `rate_limit_seconds`) and logging a warning. A
    hard-fail status, or a non-retryable RequestException (e.g. InvalidURL -
    a malformed path won't become valid on retry), raises immediately
    without retrying.
    """
    max_attempts = len(retry_waits) + 1
    target = (
        f"{path}?{'&'.join(f'{k}={v}' for k, v in params.items())}" if params else path
    )
    last_error: Exception | None = None
    last_problem = ""  # last_error, worded for the retry warning
    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            sleep(rate_limit_seconds)
        else:
            wait = max(retry_waits[attempt - 2], rate_limit_seconds)
            logger.warning(
                "%s: %s; retrying in %gs (retry %d of %d)",
                target,
                last_problem,
                wait,
                attempt - 1,
                len(retry_waits),
            )
            sleep(wait)
        try:
            response = session.get(path, params=params)
        except _RETRYABLE_ERRORS as exc:
            last_error = exc
            last_problem = f"{type(exc).__name__}: {exc}"
            continue
        except RequestException as exc:
            raise FetchError(f"{path} failed: {exc}") from exc

        if response.status_code in _HARD_FAIL_STATUSES:
            raise FetchError(f"{path} returned {_error_detail(response)} (not retried)")
        if response.status_code >= 400:
            last_problem = f"returned {_error_detail(response)}"
            last_error = FetchError(f"{target} {last_problem}")
            continue

        return response

    raise FetchError(
        f"failed to fetch {target} after {max_attempts} attempts"
    ) from last_error
