from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from constraint_scanner.core.enums import OpportunityState, StrategyType, TemplateType
from constraint_scanner.schemas.common import SchemaModel


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
