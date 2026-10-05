"""GET /availability/buildings: how many rooms each building has free.

It shares its search with /availability, which test_availability.py covers in
depth, so these check the summary itself and spot-check the shared search.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.models import Room, Term
from tests.api.conftest import FRIDAY, FRIDAY_10AM_PDT, NEAR_EVANS, THURSDAY


def _summary(client: TestClient, term: Term, **params):
    return client.get(
        "/availability/buildings", params={"term_id": term.term_id, **params}
    )


def _friday_10am(client: TestClient, term: Term, **params):
    return _summary(client, term, day_of_week=FRIDAY, time="10:00", **params)


def _results(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return response.json()["results"]


def _counts(response) -> list[tuple[str, int]]:
    return [(b["building_name"], b["free_rooms"]) for b in _results(response)]


def test_counts_each_buildings_free_rooms_and_longest_stretch(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _friday_10am(client, term)

    assert response.status_code == 200
    body = response.json()
    dwinelle = rooms["dwinelle_242"].building
    # Etcheverry 3106 is free 59 minutes, under the default 60.
    assert body == {
        "date": None,
        "day_of_week": FRIDAY,
        "time": "10:00",
        "results": [
            {
                "building_id": dwinelle.building_id,
                "building_code": "DWINELLE",
                "building_name": "Dwinelle",
                # 242 until 14:00 and 109 until 11:00.
                "free_rooms": 2,
                "longest_free_until": "14:00",
                "longest_free_minutes": 240,
                "distance_meters": None,
            }
        ],
    }


def test_a_lower_minimum_counts_shorter_gaps(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    results = _results(_friday_10am(client, term, minimum_minutes=1))

    assert [
        (b["building_name"], b["free_rooms"], b["longest_free_until"]) for b in results
    ] == [("Dwinelle", 2, "14:00"), ("Etcheverry", 1, "10:59")]


def test_a_higher_minimum_drops_rooms_from_the_count(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    # Only 242 is free for 2 hours.
    response = _friday_10am(client, term, minimum_minutes=120)

    assert _counts(response) == [("Dwinelle", 1)]


def test_now_searches_the_terms_timezone(
    client: TestClient, term: Term, rooms: dict[str, Room], clock
):
    clock(FRIDAY_10AM_PDT)

    response = _summary(client, term)

    assert response.json()["date"] == "2025-09-05"
    assert _counts(response) == [("Dwinelle", 2)]


@pytest.mark.parametrize(
    "params",
    [
        {"building": "dwin"},
        {"building_code": "dwinelle"},
        {"room": "242"},
    ],
)
def test_filters_apply_before_counting(
    client: TestClient, term: Term, rooms: dict[str, Room], params
):
    response = _friday_10am(client, term, minimum_minutes=1, **params)

    expected = 1 if "room" in params else 2
    assert _counts(response) == [("Dwinelle", expected)]


def test_the_building_id_filter_limits_results(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _friday_10am(
        client,
        term,
        minimum_minutes=1,
        building_id=rooms["etcheverry_3106"].building_id,
    )

    assert _counts(response) == [("Etcheverry", 1)]


@pytest.mark.parametrize("minimum_minutes", [1, 60, 120])
def test_free_rooms_match_availabilitys_total(
    client: TestClient, term: Term, rooms: dict[str, Room], minimum_minutes
):
    search = {
        "day_of_week": FRIDAY,
        "time": "10:00",
        "minimum_minutes": minimum_minutes,
    }

    for building in _results(_summary(client, term, **search)):
        rooms_response = client.get(
            "/availability",
            params={
                "term_id": term.term_id,
                "building_id": building["building_id"],
                **search,
            },
        )
        assert building["free_rooms"] == rooms_response.json()["total"]


def test_near_sorts_nearest_first_with_unknown_locations_last(
    client: TestClient, term: Term, located_rooms
):
    response = _friday_10am(client, term, **NEAR_EVANS)

    assert _counts(response) == [
        ("Evans", 2),
        ("Evans Annex", 2),
        ("Dwinelle", 2),
        ("Hearst Field Annex", 1),
    ]


def test_near_reports_the_same_distances_as_availability(
    client: TestClient, term: Term, located_rooms
):
    search = {"day_of_week": FRIDAY, "time": "10:00", **NEAR_EVANS}
    rooms_response = client.get(
        "/availability", params={"term_id": term.term_id, **search}
    )
    room_distances = {
        r["building_id"]: r["distance_meters"] for r in rooms_response.json()["results"]
    }

    results = _results(_summary(client, term, **search))

    assert {b["building_id"]: b["distance_meters"] for b in results} == room_distances
    assert results[-1]["distance_meters"] is None


def test_without_near_buildings_are_sorted_by_name(
    client: TestClient, term: Term, located_rooms
):
    results = _results(_friday_10am(client, term))

    assert [b["building_name"] for b in results] == [
        "Dwinelle",
        "Evans",
        "Evans Annex",
        "Hearst Field Annex",
    ]
    assert all(b["distance_meters"] is None for b in results)


def test_rooms_not_in_use_are_never_counted(
    client: TestClient, db: Session, term: Term, rooms: dict[str, Room]
):
    rooms["dwinelle_109"].in_use = False
    db.commit()

    assert _counts(_friday_10am(client, term)) == [("Dwinelle", 1)]


def test_buildings_outside_coverage_are_left_out(
    client: TestClient, db: Session, term: Term, rooms: dict[str, Room]
):
    rooms["dwinelle_242"].building.included_in_coverage = False
    db.commit()

    assert _counts(_friday_10am(client, term, minimum_minutes=1)) == [("Etcheverry", 1)]


def test_a_date_outside_the_term_reports_the_moment_but_no_buildings(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _summary(client, term, at="2026-01-09T10:00")

    assert response.status_code == 200
    body = response.json()
    assert (body["date"], body["day_of_week"], body["time"]) == (
        "2026-01-09",
        FRIDAY,
        "10:00",
    )
    assert body["results"] == []


def test_a_minimum_running_past_midnight_matches_nothing(
    client: TestClient, term: Term, rooms: dict[str, Room]
):
    response = _summary(
        client, term, day_of_week=THURSDAY, time="21:00", minimum_minutes=181
    )

    assert response.json()["time"] == "21:00"
    assert _results(response) == []


def test_an_unknown_term_is_404(client: TestClient, term: Term):
    response = client.get(
        "/availability/buildings", params={"term_id": term.term_id + 1}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"term {term.term_id + 1} not found"}


@pytest.mark.parametrize(
    "params, param",
    [
        ({"at": "2025-09-05T10:00", "day_of_week": FRIDAY, "time": "10:00"}, "at"),
        ({"near_latitude": 37.87}, "near_longitude"),
        ({"building": "   "}, "building"),
        ({"minimum_minutes": 0}, "minimum_minutes"),
    ],
)
def test_invalid_searches_are_rejected_like_availability(
    client: TestClient, term: Term, params, param
):
    response = _summary(client, term, **params)

    assert response.status_code == 422, response.text
    assert ["query", param] in [e["loc"] for e in response.json()["detail"]]


def test_there_are_no_paging_parameters(client: TestClient):
    """The summary covers every building, so it has no limit or offset."""
    names = [
        parameter["name"]
        for parameter in client.get("/openapi.json").json()["paths"][
            "/availability/buildings"
        ]["get"]["parameters"]
    ]

    assert "limit" not in names
    assert "offset" not in names
