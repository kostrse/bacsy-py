"""Error bodies returned by the API."""

from __future__ import annotations

from pydantic import Field, JsonValue

from bacsy.models.base import BaseApiModel, EpochMillis
from bacsy.models.enums import ApiErrorType


class ApiFieldError(BaseApiModel):
    """One entry of `ApiErrorBody.errors`, usually a failed field validation."""

    field: str | None = None
    type: str | None = None
    payload: JsonValue | None = None


class ApiErrorBody(BaseApiModel):
    """The JSON body every REST endpoint returns on failure. All fields are optional."""

    type: ApiErrorType | None = None
    errors: list[ApiFieldError] = Field(default_factory=list)
    display_options: dict[str, JsonValue] | None = None
    timestamp: EpochMillis | None = None
    trace_id: str | None = None
