from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"

EntityId = Annotated[str, Field(min_length=1)]
TraceId = Annotated[str, Field(min_length=1)]
CorrelationId = Annotated[str, Field(min_length=1)]
NonEmptyString = Annotated[str, Field(min_length=1)]


class DungeonBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class SchemaVersionedModel(DungeonBaseModel):
    schema_version: str = Field(default=SCHEMA_VERSION)


class TimestampedModel(SchemaVersionedModel):
    created_at: datetime
