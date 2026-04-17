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
    simulation_run_id: str
    classification: SimulationClassification
    simulated_at: datetime
    fill_probability: Decimal
    expected_pnl_usd: Decimal
    downside_bound_usd: Decimal
    estimated_slippage_bps: Decimal
    incident_flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class LatestSimulationResponse(SchemaModel):
    """Authoritative latest simulation summary for one opportunity."""

    id: int
    opportunity_id: int
    simulation_run_id: str
    summary_record: bool
    executed_at: datetime
    classification: SimulationClassification
    fill_probability: Decimal | None = None
    expected_pnl_usd: Decimal | None = None
    downside_bound_usd: Decimal | None = None
    estimated_slippage_bps: Decimal | None = None
    incident_flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class SimulationPageResponse(SchemaModel):
    """Paginated latest authoritative simulation listing."""

    items: list[LatestSimulationResponse]
    total: int
    limit: int
    offset: int
