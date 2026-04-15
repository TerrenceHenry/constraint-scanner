from __future__ import annotations

from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import JSONB

JSON_PAYLOAD = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")
