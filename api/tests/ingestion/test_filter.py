from pathlib import Path

from ingestion.filter import classify, is_accepted
from ingestion.parse import parse_section
from ingestion.types import ParsedSection

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sections"


def _parse(name: str) -> ParsedSection:
    return parse_section((FIXTURES / name).read_text(), slug=name)


def test_lec_with_room_is_accepted():
    section = classify(_parse("lec_with_room.html"))
    assert is_accepted(section)
    assert section.rejection_reason is None


def test_grp_with_room_is_accepted():
    section = classify(_parse("grp_with_room.html"))
    assert is_accepted(section)


def test_dis_with_room_is_accepted():
    section = classify(_parse("dis_with_room.html"))
    assert is_accepted(section)


def test_sem_with_room_is_accepted():
    assert is_accepted(classify(_parse("sem_with_room.html")))


def test_std_with_room_is_accepted():
    assert is_accepted(classify(_parse("std_with_room.html")))


def test_lec_general_assignment_is_rejected():
    section = classify(_parse("lec_general_assignment.html"))
    assert not is_accepted(section)
    assert section.rejection_reason == "general_assignment_requested"


def test_grp_missing_location_is_rejected_even_though_type_is_in_scope():
    section = classify(_parse("grp_missing_location.html"))
    assert not is_accepted(section)
    assert section.rejection_reason == "missing_location"


def test_ind_section_is_rejected_by_type():
    section = classify(_parse("ind_no_meetings.html"))
    assert not is_accepted(section)
    assert section.rejection_reason == "section_type_not_room_occupying:IND"


def test_lec_meeting_three_days_is_accepted():
    assert is_accepted(classify(_parse("lec_three_days.html")))


def test_grp_with_two_meeting_blocks_is_accepted():
    assert is_accepted(classify(_parse("grp_two_meeting_blocks.html")))


def test_online_lec_is_rejected():
    section = classify(_parse("lec_online.html"))
    assert not is_accepted(section)
    assert section.rejection_reason == "online"


def test_location_without_a_room_number_is_rejected():
    section = classify(_parse("lec_unparseable_location.html"))
    assert not is_accepted(section)
    assert section.rejection_reason == "unparseable_location"
