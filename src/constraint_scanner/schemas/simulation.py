from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from constraint_scanner.core.enums import SimulationClassification
from constraint_scanner.schemas.common import SchemaModel


class SimulationResponse(SchemaModel):
    """API response for a simulation run result."""

    candidate_id: str
    classification: SimulationClassification
    simulated_at: datetime
    estimated_fill_rate: Decimal
    estimated_slippage_bps: Decimal
    estimated_pnl_usd: Decimal
    notes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
