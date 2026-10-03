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
    assert (body["day_of_week"], body["time"]) == (FRIDAY, "10:00")
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

    assert response.status_code == 422


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
    "params",
    [
        {"day_of_week": FRIDAY},
        {"time": "10:00"},
        {"day_of_week": 7, "time": "10:00"},
        {"day_of_week": -1, "time": "10:00"},
        {"day_of_week": FRIDAY, "time": "25:00"},
        {"day_of_week": FRIDAY, "time": "10:00+02:00"},
        {"day_of_week": FRIDAY, "time": "10:00Z"},
    ],
)
def test_invalid_day_or_time_is_rejected(client: TestClient, term: Term, params):
    assert _get(client, term, **params).status_code == 422


def test_term_id_is_required(client: TestClient):
    assert client.get("/availability").status_code == 422
