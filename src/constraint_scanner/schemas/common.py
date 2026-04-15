from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """Base API schema with strict extra-field handling."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class TimestampedResponse(SchemaModel):
    """Base response carrying common audit timestamps."""

    created_at: datetime
    updated_at: datetime


class BookLevelPayload(SchemaModel):
    """Transport schema for a single order book level."""

    price: Decimal
    size: Decimal
