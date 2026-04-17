from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from constraint_scanner.core.enums import OpportunityState, StrategyType, TemplateType
from constraint_scanner.schemas.common import SchemaModel, TimestampedResponse
from constraint_scanner.schemas.simulation import LatestSimulationResponse


class OpportunityLegResponse(SchemaModel):
    """API response for one leg of an opportunity."""

    market_id: int
    token_id: int
    side: str
    price: Decimal
    quantity: Decimal
    note: str | None = None


class OpportunityResponse(SchemaModel):
    """API response for a detected opportunity candidate."""

    candidate_id: str
    strategy_type: StrategyType
    template_type: TemplateType
    state: OpportunityState
    detected_at: datetime
    expected_edge_bps: Decimal
    expected_value_usd: Decimal
    legs: list[OpportunityLegResponse]
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpportunityListItemResponse(TimestampedResponse):
    """Authoritative operator-facing opportunity summary."""

    id: int
    group_id: int | None = None
    constraint_id: int | None = None
    market_id: int | None = None
    token_id: int | None = None
    scope_key: str
    persistence_key: str
    status: str
    detected_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None = None
    score: Decimal | None = None
    edge_bps: Decimal | None = None
    expected_value_usd: Decimal | None = None
    template_type: str | None = None
    confidence_score: Decimal | None = None
    latest_simulation: LatestSimulationResponse | None = None


class OpportunityDetailResponse(OpportunityListItemResponse):
    """Operator-facing opportunity detail view."""

    details: dict[str, Any] = Field(default_factory=dict)


class OpportunityPageResponse(SchemaModel):
    """Paginated opportunity listing."""

    items: list[OpportunityListItemResponse]
    total: int
    limit: int
    offset: int
