from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.core.ids import make_prefixed_id
from constraint_scanner.core.types import OpportunityLeg


def build_persistence_key(template_type: TemplateType, legs: tuple[OpportunityLeg, ...] | list[OpportunityLeg]) -> str:
    """Build a deterministic persistence key from normalized legs and template."""

    normalized_legs = tuple(
        sorted(
            (
                (
                    leg.market_id,
                    leg.token_id,
                    leg.side,
                    str(leg.quantity.normalize()),
                )
                for leg in legs
            )
        )
    )
    return make_prefixed_id("opp", template_type.value, *normalized_legs)


@dataclass(frozen=True, slots=True)
class OpportunityLifecycle:
    """Explicit lifecycle timestamps and counters for a recurring opportunity."""

    persistence_key: str
    first_seen_at: datetime
    last_seen_at: datetime
    seen_count: int
    persistence_ms: int
    closed_at: datetime | None = None

    def as_detail_json(self) -> dict[str, Any]:
        """Return a deterministic JSON-serializable lifecycle payload."""

        return {
            "persistence_key": self.persistence_key,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at is not None else None,
            "persistence_ms": self.persistence_ms,
            "seen_count": self.seen_count,
        }


def merge_persistence_state(
    *,
    existing_details: dict[str, Any] | None,
    existing_first_seen_at: datetime | None,
    persistence_key: str,
    detected_at: datetime,
) -> OpportunityLifecycle:
    """Merge persistence state for a recurring opportunity."""

    normalized_now = ensure_utc(detected_at)
    existing_payload = existing_details or {}
    existing = existing_payload.get("lifecycle")
    if not isinstance(existing, dict):
        existing = existing_payload.get("persistence", {})
    first_seen = ensure_utc(existing_first_seen_at) if existing_first_seen_at is not None else normalized_now
    seen_count = int(existing.get("seen_count", 0)) + 1
    persistence_ms = int((normalized_now - first_seen).total_seconds() * 1000)

    return OpportunityLifecycle(
        persistence_key=persistence_key,
        first_seen_at=first_seen,
        last_seen_at=normalized_now,
        seen_count=seen_count,
        persistence_ms=persistence_ms,
    )
