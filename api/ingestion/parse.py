import re
from datetime import datetime, time, timedelta

from bs4 import BeautifulSoup, Tag

from ingestion.types import ParsedMeeting, ParsedSection

_DAY_CODES = {
    "Mo": 0,
    "Tu": 1,
    "We": 2,
    "Th": 3,
    "Fr": 4,
    "Sa": 5,
    "Su": 6,
}

_TIME_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}\s*[ap]m)\s*-\s*(?P<end>\d{1,2}:\d{2}\s*[ap]m)",
    re.IGNORECASE,
)

# Trailing room token: an optional single letter prefix, then a digit, then
# any run of alnum/hyphen characters (e.g. "242", "3030", "B56", "242A").
_ROOM_SPLIT_RE = re.compile(r"^(?P<building>.+?)\s+(?P<room>[A-Za-z]?\d[\dA-Za-z-]*)$")


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_time(text: str) -> time:
    return datetime.strptime(text.strip(), "%I:%M %p").time()


def _parse_days(days_div: Tag) -> list[int]:
    day_span = days_div.find_all("span")
    if len(day_span) < 2:
        return []
    text = _normalize_ws(day_span[-1].get_text())
    if not text:
        return []
    return [_DAY_CODES[code.strip()] for code in text.split(",") if code.strip()]


def _parse_time_range(time_div: Tag) -> tuple[time, time] | None:
    time_spans = time_div.find_all("span")
    if len(time_spans) < 2:
        return None
    text = _normalize_ws(time_spans[-1].get_text())
    match = _TIME_RANGE_RE.search(text)
    if not match:
        return None
    start = _parse_time(match.group("start"))
    end = _parse_time(match.group("end"))
    # Berkeley displays the end time inclusive of its last minute (e.g. a
    # standard 89-minute TuTh block shows as "10:00 am - 11:29 am"). The
    # true half-open boundary is one minute later.
    end = (datetime.combine(datetime.min, end) + timedelta(minutes=1)).time()
    if end <= start:
        # A displayed end time of 11:59pm would roll into the next day here,
        # producing an end before start - no real Berkeley class meets that
        # late, but fail loudly rather than silently write an inverted
        # range. Caught by pipeline.py's per-section failure handling.
        raise ValueError(
            f"meeting end time {end} is not after start time {start} "
            "(likely a midnight-crossing meeting, which isn't supported)"
        )
    return start, end


def _split_building_room(text: str) -> tuple[str | None, str | None]:
    match = _ROOM_SPLIT_RE.match(text)
    if not match:
        return None, None
    return match.group("building").strip(), match.group("room").strip()


def _parse_location(
    location_div: Tag | None,
) -> tuple[str | None, str | None, str | None]:
    """Returns (building_name, room_number, location_raw)."""
    if location_div is None:
        return None, None, None
    # Most rooms are a campus-map link, but some buildings (e.g. "Social
    # Sciences Building 155") are plain text with no link, so both are split.
    # Text with no trailing room number, like "Internet/Online" or
    # "Requested General Assignment", doesn't split.
    link = location_div.find("a")
    text = _normalize_ws((link or location_div).get_text())
    if not text:
        return None, None, None
    building, room = _split_building_room(text)
    return building, room, text


def parse_section(html: str, slug: str) -> ParsedSection:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article", class_="sf")
    if article is None:
        raise ValueError(f"no section article found for {slug}")

    source_record_id = article.get("data-history-node-id") or slug
    type_span = article.find("span", class_="sf--title--code")
    section_type = _normalize_ws(type_span.get_text()) if type_span else ""

    meetings: list[ParsedMeeting] = []
    building_name: str | None = None
    room_number: str | None = None
    location_raw: str | None = None

    for details in article.find_all("div", class_="sf--meeting-details"):
        days_div = details.find("div", class_="sf--meeting-days")
        time_div = details.find("div", class_="sf--meeting-time")
        location_div = details.find("div", class_="sf--location")

        days = _parse_days(days_div) if days_div else []
        time_range = _parse_time_range(time_div) if time_div else None
        block_building, block_room, block_location_raw = _parse_location(location_div)

        # First meeting block with a resolvable location wins; sections
        # observed in practice have exactly one meeting-details block, so
        # this only matters if a rare section has more than one.
        if location_raw is None:
            building_name, room_number, location_raw = (
                block_building,
                block_room,
                block_location_raw,
            )

        if not days or time_range is None:
            continue
        start, end = time_range
        for day in days:
            meetings.append(
                ParsedMeeting(day_of_week=day, start_time=start, end_time=end)
            )

    return ParsedSection(
        source_record_id=str(source_record_id),
        slug=slug,
        section_type=section_type,
        building_name=building_name,
        room_number=room_number,
        location_raw=location_raw,
        meetings=meetings,
    )
