from pathlib import Path

from ingestion.pipeline import IngestionPipeline
from tests.ingestion.conftest import FakeResponse, FakeSession

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

    sections = list(pipeline.run(term_id=8573))

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

    sections = list(pipeline.run(term_id=8573))

    # the broken page is skipped, not fatal - the next section still comes through
    assert [s.slug for s in sections] == ["lec-with-room"]
    assert pipeline.stats.read == 2
    assert pipeline.stats.failed == 1
    assert pipeline.stats.accepted == 1
