from collections.abc import Iterator
from dataclasses import dataclass

from ingestion.enumerate import enumerate_section_urls
from ingestion.fetch import FetchError, SectionSession, fetch
from ingestion.filter import classify, is_accepted
from ingestion.parse import parse_section
from ingestion.types import ParsedSection


@dataclass
class PipelineStats:
    read: int = 0
    accepted: int = 0
    rejected: int = 0
    failed: int = 0


class IngestionPipeline:
    """Enumerates, fetches, parses, and classifies a term's sections.

    This does not write to a database - it yields ParsedSection objects for
    a persistence layer to consume once the Epic 2 schema exists. `stats`
    tracks the same read/accepted/rejected/failed shape ImportRun will
    eventually need to record.
    """

    def __init__(self, session: SectionSession, *, rate_limit_seconds: float):
        self.session = session
        self.rate_limit_seconds = rate_limit_seconds
        self.stats = PipelineStats()

    def run(self, term_id: int) -> Iterator[ParsedSection]:
        section_paths = enumerate_section_urls(
            self.session, term_id, rate_limit_seconds=self.rate_limit_seconds
        )
        for path in section_paths:
            self.stats.read += 1
            slug = path.removeprefix("/content/")
            try:
                response = fetch(self.session, path, rate_limit_seconds=self.rate_limit_seconds)
            except FetchError:
                self.stats.failed += 1
                continue

            try:
                section = classify(parse_section(response.text, slug=slug))
            except Exception:
                # A single malformed section page shouldn't abort a whole
                # term's scrape - catches this broadly (not just parse_section's
                # own ValueError) since real-world HTML can fail in ways the
                # parser doesn't explicitly anticipate.
                self.stats.failed += 1
                continue

            if is_accepted(section):
                self.stats.accepted += 1
            else:
                self.stats.rejected += 1
            yield section
