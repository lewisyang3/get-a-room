import logging
from collections.abc import Iterator
from collections import Counter
from dataclasses import dataclass, field

from ingestion.enumerate import enumerate_section_urls
from ingestion.fetch import FetchError, SectionSession, fetch
from ingestion.filter import classify, is_accepted
from ingestion.parse import parse_section
from ingestion.types import ParsedSection

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    read: int = 0
    accepted: int = 0
    rejected: int = 0
    failed: int = 0
    # How many sections were rejected for each `classify()` reason.
    rejection_reasons: Counter[str] = field(default_factory=Counter)


class IngestionPipeline:
    """Enumerates, fetches, parses, and classifies a term's sections.

    This does not write to a database - it yields ParsedSection objects for
    a persistence layer to consume once the Epic 2 schema exists. `stats`
    tracks the same read/accepted/rejected/failed shape ImportRun will
    eventually need to record.
    """

    def __init__(
        self,
        session: SectionSession,
        *,
        rate_limit_seconds: float,
        max_pages: int = 5000,
        progress_every: int = 100,
    ):
        self.session = session
        self.rate_limit_seconds = rate_limit_seconds
        self.max_pages = max_pages
        self.progress_every = progress_every
        self.stats = PipelineStats()

    def run(self, taxonomy_term_id: int) -> Iterator[ParsedSection]:
        section_paths = enumerate_section_urls(
            self.session,
            taxonomy_term_id,
            rate_limit_seconds=self.rate_limit_seconds,
            max_pages=self.max_pages,
        )
        logger.info("enumerating sections for taxonomy term %s", taxonomy_term_id)
        while True:
            # Top of the loop: the previous section is fully handled,
            # including whatever the consumer did with it after the yield.
            if self.stats.read and self.stats.read % self.progress_every == 0:
                logger.info(
                    "progress: %d sections read (%d accepted, %d rejected, "
                    "%d failed)",
                    self.stats.read,
                    self.stats.accepted,
                    self.stats.rejected,
                    self.stats.failed,
                )
            try:
                path = next(section_paths)
            except StopIteration:
                return
            except (FetchError, RuntimeError):
                # Unlike a single section's fetch/parse failure below, a
                # failure enumerating the term means we don't know what
                # sections we missed - treating it as "run complete" would
                # silently produce a truncated-but-looks-successful import.
                logger.exception(
                    "failed to enumerate sections for term %s", taxonomy_term_id
                )
                raise

            self.stats.read += 1
            slug = path.removeprefix("/content/")
            try:
                response = fetch(
                    self.session, path, rate_limit_seconds=self.rate_limit_seconds
                )
            except FetchError as exc:
                logger.warning("failed to fetch %s: %s", path, exc)
                self.stats.failed += 1
                continue

            try:
                section = classify(parse_section(response.text, slug=slug))
            except Exception:
                # A single malformed section page shouldn't abort a whole
                # term's scrape - catches this broadly (not just parse_section's
                # own ValueError) since real-world HTML can fail in ways the
                # parser doesn't explicitly anticipate. logger.exception
                # captures type/message/traceback so a real parser regression
                # (e.g. an unrecognized day abbreviation) is distinguishable
                # from routine malformed pages, instead of just silently
                # nudging stats.failed.
                logger.exception("failed to parse section %s (%s)", slug, path)
                self.stats.failed += 1
                continue

            if is_accepted(section):
                self.stats.accepted += 1
            else:
                self.stats.rejected += 1
                self.stats.rejection_reasons[section.rejection_reason] += 1
            yield section
