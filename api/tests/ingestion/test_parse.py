from datetime import time
from pathlib import Path

from ingestion.parse import parse_section
from ingestion.types import ParsedMeeting

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sections"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_lec_with_room_single_day():
    section = parse_section(_load("lec_with_room.html"), slug="lec-with-room")

    assert section.section_type == "LEC"
    assert section.building_name == "Dwinelle"
    assert section.room_number == "242"
    assert section.location_raw == "Dwinelle 242"
    assert section.meetings == [
        ParsedMeeting(day_of_week=4, start_time=time(14, 0), end_time=time(17, 0)),
    ]


def test_grp_with_room_two_days():
    section = parse_section(_load("grp_with_room.html"), slug="grp-with-room")

    assert section.section_type == "GRP"
    assert section.building_name == "Campbell Hall"
    assert section.room_number == "131"
    assert section.meetings == [
        ParsedMeeting(day_of_week=0, start_time=time(19, 0), end_time=time(20, 0)),
        ParsedMeeting(day_of_week=2, start_time=time(19, 0), end_time=time(20, 0)),
    ]


def test_dis_with_room_end_time_plus_one_minute():
    section = parse_section(_load("dis_with_room.html"), slug="dis-with-room")

    assert section.section_type == "DIS"
    assert section.building_name == "Valley Life Sciences"
    assert section.room_number == "3030"
    assert section.meetings == [
        ParsedMeeting(day_of_week=2, start_time=time(12, 0), end_time=time(13, 0)),
    ]


def test_lec_general_assignment_has_no_room():
    section = parse_section(_load("lec_general_assignment.html"), slug="lec-general-assignment")

    assert section.section_type == "LEC"
    assert section.building_name is None
    assert section.room_number is None
    assert section.location_raw == "Requested General Assignment"
    assert len(section.meetings) == 2  # Tu, Th


def test_grp_missing_location_div_is_empty():
    section = parse_section(_load("grp_missing_location.html"), slug="grp-missing-location")

    assert section.section_type == "GRP"
    assert section.building_name is None
    assert section.room_number is None
    assert section.location_raw is None
    assert len(section.meetings) == 1  # Th


def test_ind_section_has_no_meetings():
    section = parse_section(_load("ind_no_meetings.html"), slug="ind-no-meetings")

    assert section.section_type == "IND"
    assert section.meetings == []
    assert section.building_name is None
    assert section.room_number is None
