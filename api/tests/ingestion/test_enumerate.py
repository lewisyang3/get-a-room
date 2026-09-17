from ingestion.enumerate import enumerate_section_urls
from tests.ingestion.conftest import FakeResponse, FakeSession

_PAGES = {
    0: '<a href="/content/course-a-lec-001">A</a> <a href="/content/course-b-lec-001">B</a>',
    1: '<a href="/content/course-c-dis-001">C</a>',
    2: "",
}


def _make_session(pages: dict[int, str]) -> FakeSession:
    def handler(path: str, params: dict | None) -> FakeResponse:
        page = (params or {}).get("page", 0)
        return FakeResponse(200, text=pages.get(page, ""))

    return FakeSession(handler)


def test_enumerate_stops_at_first_empty_page():
    session = _make_session(_PAGES)

    urls = list(enumerate_section_urls(session, term_id=8573, rate_limit_seconds=0))

    assert urls == [
        "/content/course-a-lec-001",
        "/content/course-b-lec-001",
        "/content/course-c-dis-001",
    ]
    # stops as soon as page 2 comes back empty - never requests page 3
    assert [call[1]["page"] for call in session.calls] == [0, 1, 2]


def test_enumerate_dedupes_links_within_a_page():
    dupe_page = {0: '<a href="/content/x-lec-001">X</a> <a href="/content/x-lec-001">X again</a>', 1: ""}
    session = _make_session(dupe_page)

    urls = list(enumerate_section_urls(session, term_id=8573, rate_limit_seconds=0))

    assert urls == ["/content/x-lec-001"]
