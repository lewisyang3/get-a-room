import re
from collections.abc import Iterator

from ingestion.fetch import SectionSession, fetch

# classes.berkeley.edu/taxonomy/term/{term_id} is permitted by robots.txt;
# /search/ is not (and its results are rendered client-side anyway).
_CONTENT_LINK_RE = re.compile(r'href="(/content/[^"]+)"')


def enumerate_section_urls(
    session: SectionSession,
    term_id: int,
    *,
    rate_limit_seconds: float,
) -> Iterator[str]:
    """Yields /content/{slug} paths for every section in a term.

    Pages classes.berkeley.edu/taxonomy/term/{term_id}?page=N starting at 0
    and stops as soon as a page yields no section links, rather than
    relying on a known page count. Termination is based on the raw
    (pre-dedup) link count for that page, not the net-new count - a page
    that happens to repeat only already-seen links doesn't necessarily mean
    the end of the pager, and stopping there would silently drop whatever
    real sections follow.
    """
    page = 0
    seen: set[str] = set()
    while True:
        response = fetch(
            session,
            f"/taxonomy/term/{term_id}",
            params={"page": page},
            rate_limit_seconds=rate_limit_seconds,
        )
        links = _CONTENT_LINK_RE.findall(response.text)
        if not links:
            return
        for link in links:
            if link not in seen:
                seen.add(link)
                yield link
        page += 1
