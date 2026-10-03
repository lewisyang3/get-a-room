from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """An error that isn't about a specific parameter, such as a missing term."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "term 9 not found"}]}
    )

    detail: str = Field(description="What went wrong.")


class ValidationErrorDetail(BaseModel):
    """One problem with the request."""

    type: str = Field(description="A machine-readable error type.")
    loc: list[str | int] = Field(
        description='Where the problem is, e.g. `["query", "time"]`.'
    )
    msg: str = Field(description="What's wrong, for people.")
    input: Any = Field(None, description="The value that was rejected, if any.")
    ctx: dict[str, Any] | None = Field(
        None, description="Details for some errors, e.g. the limit exceeded."
    )


class ValidationErrorResponse(BaseModel):
    """A 422: one or more parameters are invalid."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "detail": [
                        {
                            "type": "value_error",
                            "loc": ["query", "time"],
                            "msg": "time is required with day_of_week",
                            "input": None,
                        }
                    ]
                }
            ]
        }
    )

    detail: list[ValidationErrorDetail] = Field(
        description="Every problem found with the request."
    )
