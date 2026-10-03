import logging
from pathlib import Path

import pytest

from ingestion.fetch import FetchError
from ingestion.pipeline import IngestionPipeline
from tests.conftest import FakeResponse, FakeSession, listing_handler

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sections"

_TAXONOMY_PAGES = {
    0: (
        '<a href="/content/lec-with-room">A</a>'
        '<a href="/content/ind-no-meetings">B</a>'
        '<a href="/content/missing-page">C</a>'
    ),
    1: "",
}

_SECTION_HTML = {
    "/content/lec-with-room": (FIXTURES / "lec_with_room.html").read_text(),
    "/content/ind-no-meetings": (FIXTURES / "ind_no_meetings.html").read_text(),
}


def _handler(path: str, params: dict | None) -> FakeResponse:
    if path.startswith("/taxonomy/term/"):
        page = (params or {}).get("page", 0)
        return FakeResponse(200, text=_TAXONOMY_PAGES.get(page, ""))
    if path in _SECTION_HTML:
        return FakeResponse(200, text=_SECTION_HTML[path])
    return FakeResponse(404)


def test_pipeline_end_to_end_counts_and_yields():
    session = FakeSession(_handler)
    pipeline = IngestionPipeline(session, rate_limit_seconds=0)

    sections = list(pipeline.run(taxonomy_term_id=8573))

    assert [s.slug for s in sections] == ["lec-with-room", "ind-no-meetings"]
    assert pipeline.stats.read == 3  # includes the 404 path
    assert pipeline.stats.accepted == 1  # lec-with-room
    assert pipeline.stats.rejected == 1  # ind-no-meetings, wrong type
    assert pipeline.stats.failed == 1  # missing-page, 404


def test_pipeline_survives_a_malformed_section_page():
    taxonomy_pages = {
        0: '<a href="/content/broken">A</a><a href="/content/lec-with-room">B</a>',
        1: "",
    }
    section_html = {
        "/content/broken": "<html><body>not a section page at all</body></html>",
        "/content/lec-with-room": (FIXTURES / "lec_with_room.html").read_text(),
    }

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/taxonomy/term/"):
            page = (params or {}).get("page", 0)
            return FakeResponse(200, text=taxonomy_pages.get(page, ""))
        return FakeResponse(200, text=section_html[path])

    session = FakeSession(handler)
    pipeline = IngestionPipeline(session, rate_limit_seconds=0)

    sections = list(pipeline.run(taxonomy_term_id=8573))

    # the broken page is skipped, not fatal - the next section still comes through
    assert [s.slug for s in sections] == ["lec-with-room"]
    assert pipeline.stats.read == 2
    assert pipeline.stats.failed == 1
    assert pipeline.stats.accepted == 1


def test_pipeline_propagates_a_taxonomy_page_fetch_failure(
    caplog: pytest.LogCaptureFixture,
):
    """A failure enumerating the term (unlike a single section's fetch/parse
    failure) means we don't know what sections we missed - it must not be
    swallowed into a truncated-but-looks-successful run."""

    def handler(path: str, params: dict | None) -> FakeResponse:
        assert path.startswith("/taxonomy/term/")
        return FakeResponse(403, text="Forbidden by WAF")

    session = FakeSession(handler)
    pipeline = IngestionPipeline(session, rate_limit_seconds=0)

    with caplog.at_level(logging.ERROR, logger="ingestion.pipeline"):
        with pytest.raises(FetchError):
            list(pipeline.run(taxonomy_term_id=8573))

    assert any("enumerate" in record.message for record in caplog.records)
    assert pipeline.stats.read == 0


def test_pipeline_propagates_max_pages_exceeded():
    """The enumerate_section_urls max_pages guard is reachable through the
    pipeline, not just the generator directly."""
    taxonomy_pages = {n: '<a href="/content/repeated">A</a>' for n in range(10)}

    def handler(path: str, params: dict | None) -> FakeResponse:
        page = (params or {}).get("page", 0)
        return FakeResponse(200, text=taxonomy_pages.get(page, ""))

    session = FakeSession(handler)
    pipeline = IngestionPipeline(session, rate_limit_seconds=0, max_pages=3)

    with pytest.raises(RuntimeError, match="max_pages"):
        list(pipeline.run(taxonomy_term_id=8573))


def test_pipeline_logs_parse_failures_with_the_slug(caplog: pytest.LogCaptureFixture):
    taxonomy_pages = {0: '<a href="/content/broken">A</a>', 1: ""}
    section_html = {
        "/content/broken": "<html><body>not a section page at all</body></html>"
    }

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/taxonomy/term/"):
            page = (params or {}).get("page", 0)
            return FakeResponse(200, text=taxonomy_pages.get(page, ""))
        return FakeResponse(200, text=section_html[path])

    session = FakeSession(handler)
    pipeline = IngestionPipeline(session, rate_limit_seconds=0)

    with caplog.at_level(logging.ERROR, logger="ingestion.pipeline"):
        list(pipeline.run(taxonomy_term_id=8573))

    assert any("broken" in record.message for record in caplog.records)
    assert caplog.records[0].exc_info is not None


def test_pipeline_logs_progress_every_n_sections(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="ingestion.pipeline")
    session = FakeSession(
        listing_handler(
            "lec-with-room",  # accepted
            "ind-no-meetings",  # rejected: IND
            "vanished",  # failed: 404
            "lec-general-assignment",  # rejected: no assigned room
            "grp-with-room",  # 5th - after the last full batch of 2
        )
    )
    pipeline = IngestionPipeline(session, rate_limit_seconds=0, progress_every=2)

    list(pipeline.run(taxonomy_term_id=8573))

    messages = [r.getMessage() for r in caplog.records]
    assert "enumerating sections for taxonomy term 8573" in messages
    assert [m for m in messages if m.startswith("progress:")] == [
        "progress: 2 sections read (1 accepted, 1 rejected, 0 failed)",
        "progress: 4 sections read (1 accepted, 2 rejected, 1 failed)",
    ]
