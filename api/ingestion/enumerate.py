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
    relying on a known page count.
    """
    page = 0
    while True:
        response = fetch(
            session,
            f"/taxonomy/term/{term_id}",
            params={"page": page},
            rate_limit_seconds=rate_limit_seconds,
        )
        links = list(dict.fromkeys(_CONTENT_LINK_RE.findall(response.text)))
        if not links:
            return
        yield from links
        page += 1
