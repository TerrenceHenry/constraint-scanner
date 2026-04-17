from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from constraint_scanner.api.dependencies import get_db_session
from constraint_scanner.api.serializers import list_latest_simulations
from constraint_scanner.core.enums import SimulationClassification
from constraint_scanner.schemas.simulation import SimulationPageResponse

router = APIRouter(tags=["simulations"])


@router.get("/simulations", response_model=SimulationPageResponse)
def list_simulations(
    session: Session = Depends(get_db_session),
    opportunity_id: int | None = Query(default=None),
    classification: SimulationClassification | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SimulationPageResponse:
    """List latest authoritative simulation summaries."""

    simulations = list_latest_simulations(session, opportunity_id=opportunity_id)
    if classification is not None:
        simulations = [simulation for simulation in simulations if simulation.classification == classification]

    total = len(simulations)
    page_items = simulations[offset : offset + limit]
    return SimulationPageResponse(
        items=page_items,
        total=total,
        limit=limit,
        offset=offset,
    )
