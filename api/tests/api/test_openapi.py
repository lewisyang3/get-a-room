"""The OpenAPI spec documents every endpoint, parameter, field, and error.

These read the generated spec only, so they don't need a database.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.availability import AvailabilityPage
from app.api.schemas.buildings import BuildingList
from app.api.schemas.errors import ErrorResponse, ValidationErrorResponse
from app.api.schemas.health import HealthResponse
from app.main import app

OWN_SCHEMAS = [
    AvailabilityPage,
    BuildingList,
    ErrorResponse,
    ValidationErrorResponse,
    HealthResponse,
]


@pytest.fixture(scope="module")
def spec() -> dict:
    return TestClient(app).get("/openapi.json").json()


def _operations(spec: dict) -> list[tuple[str, dict]]:
    return [
        (f"{method.upper()} {path}", operation)
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
    ]


def test_every_operation_has_a_summary_and_description(spec: dict):
    for name, operation in _operations(spec):
        assert operation.get("summary"), name
        assert operation.get("description"), name


def test_every_parameter_has_a_description(spec: dict):
    for name, operation in _operations(spec):
        for parameter in operation.get("parameters", []):
            assert parameter.get("description"), f"{name} {parameter['name']}"


def test_every_field_of_our_schemas_has_a_description(spec: dict):
    schemas = spec["components"]["schemas"]
    our_names = {
        "AvailabilityResponse",
        "BuildingResponse",
        "ValidationErrorDetail",
    } | {model.__name__ for model in OWN_SCHEMAS}
    for schema_name in our_names:
        for field, definition in schemas[schema_name]["properties"].items():
            assert definition.get("description"), f"{schema_name}.{field}"


@pytest.mark.parametrize("model", OWN_SCHEMAS)
def test_schema_examples_match_their_models(model):
    """Catches an example left behind when a schema changes."""
    examples = model.model_json_schema()["examples"]

    assert examples
    for example in examples:
        model.model_validate(example)


def test_availability_documents_its_responses(spec: dict):
    responses = spec["paths"]["/availability"]["get"]["responses"]

    def schema_ref(code: str) -> str:
        return responses[code]["content"]["application/json"]["schema"]["$ref"]

    assert schema_ref("200").endswith("/AvailabilityPage")
    assert schema_ref("404").endswith("/ErrorResponse")
    assert schema_ref("422").endswith("/ValidationErrorResponse")


def test_buildings_documents_its_response(spec: dict):
    responses = spec["paths"]["/buildings"]["get"]["responses"]
    schema = responses["200"]["content"]["application/json"]["schema"]

    assert schema["$ref"].endswith("/BuildingList")


def test_every_schema_reference_resolves(spec: dict):
    """A $ref to a schema that isn't generated renders as an error in /docs."""
    defined = set(spec["components"]["schemas"])

    def refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                yield node["$ref"].rsplit("/", 1)[-1]
            for value in node.values():
                yield from refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from refs(value)

    assert set(refs(spec)) <= defined


def test_docs_are_served():
    client = TestClient(app)

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
