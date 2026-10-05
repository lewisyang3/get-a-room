import math
from collections.abc import Callable, Iterator
from datetime import datetime, time, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.availability import get_now
from app.main import app
from app.models.models import AvailabilityInterval, Building, Room, Term

THURSDAY, FRIDAY = 3, 4

# The `term` fixture is Fall 2025 (2025-08-27 to 2025-12-12), in
# America/Los_Angeles: PDT (UTC-7) until 2025-11-02, then PST (UTC-8).
FRIDAY_10AM_PDT = datetime(2025, 9, 5, 17, 0, tzinfo=timezone.utc)

Free = dict[int, list[tuple[time, time]]]


def _add_room(
    db: Session, term: Term, building: Building, room_number: str, free: Free
) -> Room:
    room = Room(building_id=building.building_id, room_number=room_number)
    db.add(room)
    db.flush()
    for day_of_week, intervals in free.items():
        for start, end in intervals:
            db.add(
                AvailabilityInterval(
                    room_id=room.room_id,
                    term_id=term.term_id,
                    day_of_week=day_of_week,
                    start_time=start,
                    end_time=end,
                    computed_at=datetime.now(timezone.utc),
                )
            )
    return room


@pytest.fixture
def rooms(db: Session, term: Term) -> dict[str, Room]:
    dwinelle = Building(name="Dwinelle", short_code="DWINELLE")
    etcheverry = Building(name="Etcheverry", short_code="ETCHEVERRY")
    db.add_all([dwinelle, etcheverry])
    db.flush()
    created = {
        # Booked Fridays 14:00-17:00, free all of Thursday.
        "dwinelle_242": _add_room(
            db,
            term,
            dwinelle,
            "242",
            {
                THURSDAY: [(time(7), time(22))],
                FRIDAY: [(time(7), time(14)), (time(17), time(22))],
            },
        ),
        # Free 60 minutes from Friday 10:00.
        "dwinelle_109": _add_room(
            db, term, dwinelle, "109", {FRIDAY: [(time(7), time(11))]}
        ),
        # Free 59 minutes from Friday 10:00.
        "etcheverry_3106": _add_room(
            db, term, etcheverry, "3106", {FRIDAY: [(time(7), time(10, 59))]}
        ),
    }
    db.commit()
    return created


@pytest.fixture
def clock() -> Iterator[Callable[[datetime], None]]:
    """Pins the endpoint's "now"; call it with an aware datetime."""

    def set_now(now: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: now

    yield set_now
    app.dependency_overrides.pop(get_now, None)


def _get(client: TestClient, term: Term, **params):
    return client.get("/availability", params={"term_id": term.term_id, **params})


def _assert_invalid(response, param: str) -> None:
    """A 422 in FastAPI's validation-error format, blaming `param`."""
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert ["query", param] in [error["loc"] for error in detail], detail
    assert all(error["msg"] for error in detail)


def _results(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return response.json()["results"]


def _room_keys(response) -> list[tuple[str, str]]:
    assert response.status_code == 200, response.text
    return [(r["building_name"], r["room_number"]) for r in _results(response)]


# --- "now" ---


def test_now_returns_rooms_free_in_the_terms_timezone(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    clock(FRIDAY_10AM_PDT)

    response = _get(client, term)

    assert response.status_code == 200
    room = rooms["dwinelle_109"]
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (2, 50, 0)
    assert (body["date"], body["day_of_week"], body["time"]) == (
        "2025-09-05",
        FRIDAY,
        "10:00",
    )
    assert body["results"] == [
        {
            "room_id": room.room_id,
            "building_id": room.building_id,
            "building_code": "DWINELLE",
            "building_name": "Dwinelle",
            "room_number": "109",
            "available_from": "10:00",
            "available_until": "11:00",
            "available_minutes": 60,
            "distance_meters": None,
        },
        {
            "room_id": rooms["dwinelle_242"].room_id,
            "building_id": rooms["dwinelle_242"].building_id,
            "building_code": "DWINELLE",
            "building_name": "Dwinelle",
            "room_number": "242",
            "available_from": "10:00",
            "available_until": "14:00",
            "available_minutes": 240,
            "distance_meters": None,
        },
    ]


def test_now_is_truncated_to_the_minute(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    clock(FRIDAY_10AM_PDT.replace(second=45))

    [dwinelle_109, dwinelle_242] = _results(_get(client, term))

    assert dwinelle_242["available_from"] == "10:00"
    assert dwinelle_242["available_minutes"] == 240


def test_now_uses_the_local_weekday_not_the_utc_one(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    """Friday 01:00 UTC is still Thursday 18:00 in Berkeley."""
    clock(datetime(2025, 9, 5, 1, 0, tzinfo=timezone.utc))

    response = _get(client, term)

    assert _room_keys(response) == [("Dwinelle", "242")]
    assert (response.json()["day_of_week"], response.json()["time"]) == (
        THURSDAY,
        "18:00",
    )
    assert _results(response)[0]["available_from"] == "18:00"
    assert _results(response)[0]["available_minutes"] == 240


@pytest.mark.parametrize(
    "now",
    [
        # Friday 10:00 PDT, before the 2025-11-02 fall-back.
        datetime(2025, 10, 31, 17, 0, tzinfo=timezone.utc),
        # Friday 10:00 PST, after it - one hour later in UTC.
        datetime(2025, 11, 7, 18, 0, tzinfo=timezone.utc),
    ],
)
def test_now_follows_local_clock_time_across_dst(
    client: TestClient, term: Term, rooms: dict[str, Room], clock, now: datetime
):
    clock(now)

    response = _get(client, term)

    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]
    assert {r["available_from"] for r in _results(response)} == {"10:00"}


@pytest.mark.parametrize(
    "now",
    [
        # The Friday before the term starts.
        datetime(2025, 8, 22, 17, 0, tzinfo=timezone.utc),
        # The Friday after it ends.
        datetime(2025, 12, 19, 18, 0, tzinfo=timezone.utc),
    ],
)
def test_now_outside_the_term_returns_no_rooms(
    client: TestClient, term: Term, rooms: dict[str, Room], clock, now: datetime
):
    clock(now)

    assert _room_keys(_get(client, term)) == []


def test_now_on_the_terms_last_local_day_is_inside_the_term(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    """Friday 2025-12-12 21:00 PST is already Saturday in UTC."""
    clock(datetime(2025, 12, 13, 5, 0, tzinfo=timezone.utc))

    assert _room_keys(_get(client, term)) == [("Dwinelle", "242")]


def test_an_explicit_day_and_time_ignore_the_clock(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    clock(datetime(2030, 1, 1, tzinfo=timezone.utc))

    response = _get(client, term, day_of_week=FRIDAY, time="10:00")

    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


# --- how long a room stays free (GAR-027) ---


def test_a_room_is_free_again_exactly_when_its_meeting_ends(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="17:00")

    [dwinelle_242] = _results(response)
    assert dwinelle_242["available_until"] == "22:00"
    assert dwinelle_242["available_minutes"] == 300


def test_a_room_is_not_free_during_its_meeting(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="16:59")

    assert _room_keys(response) == []


def test_searches_outside_the_daily_window_return_no_rooms(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    assert _room_keys(_get(client, term, day_of_week=THURSDAY, time="22:00")) == []
    assert _room_keys(_get(client, term, day_of_week=THURSDAY, time="06:59")) == []


# --- minimum duration (GAR-028) ---


def test_the_default_minimum_is_60_minutes(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="10:00")

    keys = _room_keys(response)
    assert ("Dwinelle", "109") in keys  # exactly 60 minutes
    assert ("Etcheverry", "3106") not in keys  # 59 minutes


def test_a_lower_minimum_includes_shorter_gaps(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=59)

    assert ("Etcheverry", "3106") in _room_keys(response)


def test_a_higher_minimum_excludes_shorter_gaps(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=240)

    assert _room_keys(response) == [("Dwinelle", "242")]


@pytest.mark.parametrize("minimum_minutes", ["0", "-5", "1441", "abc"])
def test_an_invalid_minimum_is_rejected(
    client: TestClient, term: Term, minimum_minutes: str
):
    response = _get(
        client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=minimum_minutes
    )

    _assert_invalid(response, "minimum_minutes")


# --- filters and ordering ---


def test_results_are_sorted_by_building_then_room(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=1)

    assert _room_keys(response) == [
        ("Dwinelle", "109"),
        ("Dwinelle", "242"),
        ("Etcheverry", "3106"),
    ]


def test_the_building_filter_limits_results(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(
        client,
        term,
        day_of_week=FRIDAY,
        time="10:00",
        minimum_minutes=1,
        building_id=rooms["etcheverry_3106"].building_id,
    )

    assert _room_keys(response) == [("Etcheverry", "3106")]


def test_rooms_not_in_use_are_never_returned(
    client: TestClient, db: Session, term: Term, rooms: dict[str, Room]
):
    rooms["dwinelle_109"].in_use = False
    db.commit()

    response = _get(client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=1)

    assert _room_keys(response) == [("Dwinelle", "242"), ("Etcheverry", "3106")]


def test_buildings_outside_coverage_are_never_returned(
    client: TestClient, db: Session, term: Term, rooms: dict[str, Room]
):
    rooms["etcheverry_3106"].building.included_in_coverage = False
    db.commit()

    response = _get(client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=1)

    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


def test_a_term_with_no_availability_returns_no_rooms(client: TestClient, term: Term):
    assert _room_keys(_get(client, term, day_of_week=FRIDAY, time="10:00")) == []


# --- invalid requests ---


def test_an_unknown_term_is_404(client: TestClient, term: Term):
    response = client.get(
        "/availability",
        params={"term_id": term.term_id + 1, "day_of_week": FRIDAY, "time": "10:00"},
    )

    assert response.status_code == 404


def test_an_unknown_term_is_404_for_now_too(client: TestClient, term: Term, clock):
    clock(FRIDAY_10AM_PDT)

    response = client.get("/availability", params={"term_id": term.term_id + 1})

    assert response.status_code == 404


@pytest.mark.parametrize(
    "params, blamed",
    [
        ({"day_of_week": FRIDAY}, "time"),
        ({"time": "10:00"}, "day_of_week"),
        ({"day_of_week": 7, "time": "10:00"}, "day_of_week"),
        ({"day_of_week": -1, "time": "10:00"}, "day_of_week"),
        ({"day_of_week": FRIDAY, "time": "25:00"}, "time"),
        ({"day_of_week": FRIDAY, "time": "10:00+02:00"}, "time"),
        ({"day_of_week": FRIDAY, "time": "10:00Z"}, "time"),
    ],
)
def test_invalid_day_or_time_is_rejected(
    client: TestClient, term: Term, params, blamed: str
):
    _assert_invalid(_get(client, term, **params), blamed)


def test_term_id_is_required(client: TestClient):
    _assert_invalid(client.get("/availability"), "term_id")


# --- building and room search (GAR-029) ---


@pytest.fixture
def annex_b5(db: Session, term: Term, rooms: dict[str, Room]) -> Room:
    """A room number with a letter, in a third building, free all Friday."""
    annex = Building(name="Hearst Field Annex", short_code="HFA")
    db.add(annex)
    db.flush()
    room = _add_room(db, term, annex, "B5", {FRIDAY: [(time(7), time(22))]})
    db.commit()
    return room


def _search(client: TestClient, term: Term, **params):
    return _get(
        client, term, day_of_week=FRIDAY, time="10:00", minimum_minutes=1, **params
    )


@pytest.mark.parametrize("code", ["DWINELLE", "dwinelle", "DwInElLe"])
def test_building_code_matches_ignoring_case(
    client: TestClient, term: Term, rooms: dict[str, Room], code: str
):
    response = _search(client, term, building_code=code)

    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


def test_building_code_must_match_exactly(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _search(client, term, building_code="DWIN")

    assert response.json()["total"] == 0
    assert _room_keys(response) == []


@pytest.mark.parametrize("name", ["dwin", "WINE", "Dwinelle"])
def test_building_name_matches_part_of_the_name_ignoring_case(
    client: TestClient, term: Term, rooms: dict[str, Room], name: str
):
    response = _search(client, term, building=name)

    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


@pytest.mark.parametrize("wildcard", ["%", "_", "D%e"])
def test_building_name_treats_wildcards_literally(
    client: TestClient, term: Term, rooms: dict[str, Room], wildcard: str
):
    assert _room_keys(_search(client, term, building=wildcard)) == []


def test_room_matches_exactly(client: TestClient, term: Term, rooms: dict[str, Room]):
    assert _room_keys(_search(client, term, room="242")) == [("Dwinelle", "242")]
    assert _room_keys(_search(client, term, room="24")) == []
    assert _room_keys(_search(client, term, room=" 242 ")) == [("Dwinelle", "242")]


def test_room_matches_ignoring_case(client: TestClient, term: Term, annex_b5: Room):
    assert _room_keys(_search(client, term, room="b5")) == [
        ("Hearst Field Annex", "B5")
    ]


def test_building_and_room_filters_apply_together(
    client: TestClient, term: Term, rooms: dict[str, Room], annex_b5: Room
):
    assert _room_keys(_search(client, term, building_code="dwinelle", room="242")) == [
        ("Dwinelle", "242")
    ]
    assert _room_keys(_search(client, term, building="annex", room="b5")) == [
        ("Hearst Field Annex", "B5")
    ]
    # Each filter matches something, but no room matches both.
    assert _room_keys(_search(client, term, building_code="HFA", room="242")) == []
    assert (
        _room_keys(
            _search(
                client,
                term,
                building_id=rooms["dwinelle_242"].building_id,
                building_code="ETCHEVERRY",
            )
        )
        == []
    )


# --- paging (GAR-029) ---


def test_pages_cover_every_room_once_in_order(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    pages = [_search(client, term, limit=1, offset=offset) for offset in range(3)]

    assert [response.json()["total"] for response in pages] == [3, 3, 3]
    assert [_room_keys(response) for response in pages] == [
        [("Dwinelle", "109")],
        [("Dwinelle", "242")],
        [("Etcheverry", "3106")],
    ]


def test_a_page_past_the_end_is_empty_but_keeps_the_total(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _search(client, term, limit=2, offset=10)

    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (3, 2, 10)
    assert body["results"] == []


def test_short_gaps_are_dropped_before_paging(
    client: TestClient, term: Term, rooms: dict[str, Room], annex_b5: Room
):
    """The 59-minute room sorts between the others; dropping it after
    LIMIT would leave this page short and miscount the total."""
    response = _get(client, term, day_of_week=FRIDAY, time="10:00", limit=2)

    assert response.json()["total"] == 3
    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]
    next_page = _get(client, term, day_of_week=FRIDAY, time="10:00", limit=2, offset=2)
    assert _room_keys(next_page) == [("Hearst Field Annex", "B5")]


def test_a_minimum_running_past_midnight_matches_nothing(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _get(client, term, day_of_week=FRIDAY, time="21:00", minimum_minutes=181)

    body = response.json()
    assert (body["total"], body["results"]) == (0, [])
    assert (body["day_of_week"], body["time"]) == (FRIDAY, "21:00")


def test_now_outside_the_term_still_reports_the_moment_searched(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    clock(datetime(2025, 8, 22, 17, 0, tzinfo=timezone.utc))

    body = _get(client, term).json()

    assert (body["total"], body["day_of_week"], body["time"]) == (0, FRIDAY, "10:00")


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"room": ""},
        {"room": " "},
        {"building": " "},
        {"building_code": ""},
    ],
)
def test_invalid_search_or_paging_is_rejected(client: TestClient, term: Term, params):
    [blamed] = params
    _assert_invalid(_search(client, term, **params), blamed)


# --- a selected date and time (GAR-030) ---


def _at(client: TestClient, term: Term, at: str, **params):
    return _get(client, term, at=at, **params)


def test_at_a_local_date_and_time_matches_that_weekday_and_time(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _at(client, term, "2025-09-05T10:00")

    body = response.json()
    assert (body["date"], body["day_of_week"], body["time"]) == (
        "2025-09-05",
        FRIDAY,
        "10:00",
    )
    weekly = _get(client, term, day_of_week=FRIDAY, time="10:00").json()
    assert body["results"] == weekly["results"]
    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


@pytest.mark.parametrize(
    "at",
    [
        "2025-09-05T17:00Z",
        "2025-09-05T17:00:00+00:00",
        # Already Saturday in Tokyo, but Friday 10:00 in Berkeley.
        "2025-09-06T02:00+09:00",
    ],
)
def test_at_with_a_utc_offset_is_converted_to_the_terms_timezone(
    client: TestClient, term: Term, rooms: dict[str, Room], at: str
):
    body = _at(client, term, at).json()

    assert (body["date"], body["day_of_week"], body["time"]) == (
        "2025-09-05",
        FRIDAY,
        "10:00",
    )
    assert body["total"] == 2


@pytest.mark.parametrize("at", ["2025-11-07T10:00", "2025-11-07T18:00Z"])
def test_at_after_the_dst_change_searches_local_clock_time(
    client: TestClient, term: Term, rooms: dict[str, Room], at: str
):
    """After 2025-11-02 Berkeley is UTC-8, so 10:00 local is 18:00Z."""
    response = _at(client, term, at)

    assert response.json()["time"] == "10:00"
    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


def test_at_uses_the_local_date_for_the_terms_last_day(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    """05:00Z on Dec 13 is still Friday Dec 12, 21:00, the term's last day."""
    response = _at(client, term, "2025-12-13T05:00Z")

    assert response.json()["date"] == "2025-12-12"
    assert _room_keys(response) == [("Dwinelle", "242")]


@pytest.mark.parametrize(
    "at, expected_date",
    [
        ("2025-12-13T10:00", "2025-12-13"),  # the day after the term ends
        ("2025-08-22T10:00", "2025-08-22"),  # the Friday before it starts
    ],
)
def test_at_outside_the_term_returns_no_rooms(
    client: TestClient,
    term: Term,
    rooms: dict[str, Room],
    at: str,
    expected_date: str,
):
    body = _at(client, term, at).json()

    assert (body["total"], body["results"]) == (0, [])
    assert body["date"] == expected_date


def test_at_a_past_date_in_the_term_still_works(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    clock(datetime(2025, 11, 20, 20, 0, tzinfo=timezone.utc))

    response = _at(client, term, "2025-09-05T10:00")

    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]


@pytest.mark.parametrize(
    "params",
    [
        {"at": "2025-09-05T10:00:30"},
        {"at": "2025-09-05T10:00:59.999"},
        {"day_of_week": FRIDAY, "time": "10:00:30"},
    ],
)
def test_searches_ignore_seconds(
    client: TestClient, term: Term, rooms: dict[str, Room], params
):
    """Every search is to the minute, as "now" is: 10:00:30 searches 10:00,
    so the response's time, available_from, and available_minutes agree."""
    response = _get(client, term, **params)

    to_the_minute = _get(client, term, day_of_week=FRIDAY, time="10:00")
    assert response.json()["time"] == "10:00"
    assert _results(response) == _results(to_the_minute)
    assert _room_keys(response) == [("Dwinelle", "109"), ("Dwinelle", "242")]
    assert [r["available_minutes"] for r in _results(response)] == [60, 240]


def test_at_without_a_time_means_midnight(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    """Midnight is outside the 07:00-22:00 window, so no rooms match."""
    body = _at(client, term, "2025-09-05").json()

    assert (body["date"], body["time"], body["total"]) == ("2025-09-05", "00:00", 0)


def test_at_works_with_filters_and_paging(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _at(client, term, "2025-09-05T10:00", building_code="dwinelle", limit=1)

    assert response.json()["total"] == 2
    assert _room_keys(response) == [("Dwinelle", "109")]


def test_a_weekday_and_time_search_has_no_date(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    body = _get(client, term, day_of_week=FRIDAY, time="10:00").json()

    assert body["date"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"at": "2025-09-05T10:00", "day_of_week": FRIDAY},
        {"at": "2025-09-05T10:00", "time": "10:00"},
        {"at": "2025-09-05T10:00", "day_of_week": FRIDAY, "time": "10:00"},
        {"at": "2025-13-01T10:00"},
        {"at": "2025-09-05T25:00"},
        {"at": "not-a-date"},
    ],
)
def test_invalid_at_is_rejected(client: TestClient, term: Term, params):
    _assert_invalid(_get(client, term, **params), "at")


# --- sorting by distance (GAR-037) ---

EVANS = (37.87362, -122.25768)
DWINELLE = (37.87073, -122.26074)
# A point just outside Evans Hall.
NEAR_EVANS = {"near_latitude": 37.8736, "near_longitude": -122.2577}


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


@pytest.fixture
def located_rooms(db: Session, term: Term) -> None:
    """Rooms free all Friday in buildings with and without coordinates."""
    buildings = [
        Building(
            name="Dwinelle",
            short_code="DWINELLE",
            latitude=DWINELLE[0],
            longitude=DWINELLE[1],
        ),
        Building(
            name="Evans", short_code="EVANS", latitude=EVANS[0], longitude=EVANS[1]
        ),
        # The same distance as Evans, so their rooms must not interleave.
        Building(
            name="Evans Annex",
            short_code="EVANS-ANNEX",
            latitude=EVANS[0],
            longitude=EVANS[1],
        ),
        Building(name="Hearst Field Annex", short_code="HFA"),
    ]
    db.add_all(buildings)
    db.flush()
    dwinelle, evans, annex, hfa = buildings
    for building, numbers in [
        (dwinelle, ["109", "242"]),
        (evans, ["10", "11"]),
        (annex, ["1", "20"]),
        (hfa, ["B5"]),
    ]:
        for number in numbers:
            _add_room(db, term, building, number, {FRIDAY: [(time(7), time(22))]})
    db.commit()


def test_near_sorts_nearest_first_with_unknown_locations_last(
    client: TestClient, term: Term, located_rooms
):
    response = _search(client, term, **NEAR_EVANS)

    assert _room_keys(response) == [
        ("Evans", "10"),
        ("Evans", "11"),
        ("Evans Annex", "1"),
        ("Evans Annex", "20"),
        ("Dwinelle", "109"),
        ("Dwinelle", "242"),
        ("Hearst Field Annex", "B5"),
    ]


def test_near_reports_each_buildings_approximate_distance(
    client: TestClient, term: Term, located_rooms
):
    point = (NEAR_EVANS["near_latitude"], NEAR_EVANS["near_longitude"])
    distances = {
        r["building_name"]: r["distance_meters"]
        for r in _results(_search(client, term, **NEAR_EVANS))
    }

    assert distances["Hearst Field Annex"] is None
    for name, location in [("Evans", EVANS), ("Dwinelle", DWINELLE)]:
        assert isinstance(distances[name], int)
        assert distances[name] == pytest.approx(
            _haversine_meters(point, location), rel=0.01, abs=1
        )


def test_near_pages_stay_in_order(client: TestClient, term: Term, located_rooms):
    everything = _room_keys(_search(client, term, **NEAR_EVANS))

    pages = [
        _room_keys(_search(client, term, limit=3, offset=offset, **NEAR_EVANS))
        for offset in (0, 3, 6)
    ]

    assert [key for page in pages for key in page] == everything


def test_without_near_the_order_and_distances_are_unchanged(
    client: TestClient, term: Term, located_rooms
):
    response = _search(client, term)

    assert _room_keys(response)[:2] == [("Dwinelle", "109"), ("Dwinelle", "242")]
    assert {r["distance_meters"] for r in _results(response)} == {None}


@pytest.mark.parametrize(
    ("params", "blamed"),
    [
        ({"near_latitude": 37.87}, "near_longitude"),
        ({"near_longitude": -122.26}, "near_latitude"),
        ({"near_latitude": 91, "near_longitude": 0}, "near_latitude"),
        ({"near_latitude": 0, "near_longitude": -181}, "near_longitude"),
        ({"near_latitude": "north", "near_longitude": 0}, "near_latitude"),
    ],
)
def test_near_rejects_an_incomplete_or_invalid_point(
    client: TestClient, term: Term, params: dict, blamed: str
):
    _assert_invalid(_search(client, term, **params), blamed)
