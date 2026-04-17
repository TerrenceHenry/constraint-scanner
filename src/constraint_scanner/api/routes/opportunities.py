from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constraint_scanner.api.dependencies import get_db_session
from constraint_scanner.api.serializers import (
    build_latest_simulation_map,
    serialize_opportunity_detail,
    serialize_opportunity_summary,
    serialize_latest_simulation_optional,
)
from constraint_scanner.db.models import Opportunity
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.schemas.opportunity import OpportunityDetailResponse, OpportunityPageResponse

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities", response_model=OpportunityPageResponse)
def list_opportunities(
    session: Session = Depends(get_db_session),
    status: str | None = Query(default="open"),
    constraint_id: int | None = Query(default=None),
    group_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OpportunityPageResponse:
    """List persisted opportunities with their latest authoritative simulation summary."""

    stmt = select(Opportunity).order_by(Opportunity.detected_at.desc(), Opportunity.id.desc())
    count_stmt = select(func.count()).select_from(Opportunity)

    if status is not None:
        stmt = stmt.where(Opportunity.status == status)
        count_stmt = count_stmt.where(Opportunity.status == status)
    if constraint_id is not None:
        stmt = stmt.where(Opportunity.constraint_id == constraint_id)
        count_stmt = count_stmt.where(Opportunity.constraint_id == constraint_id)
    if group_id is not None:
        stmt = stmt.where(Opportunity.group_id == group_id)
        count_stmt = count_stmt.where(Opportunity.group_id == group_id)

    total = session.scalar(count_stmt) or 0
    opportunities = list(session.scalars(stmt.limit(limit).offset(offset)))
    latest_map = build_latest_simulation_map(session, [opportunity.id for opportunity in opportunities])

    return OpportunityPageResponse(
        items=[
            serialize_opportunity_summary(
                opportunity,
                latest_simulation=latest_map.get(opportunity.id),
            )
            for opportunity in opportunities
        ],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDetailResponse)
def get_opportunity_detail(
    opportunity_id: int,
    session: Session = Depends(get_db_session),
) -> OpportunityDetailResponse:
    """Return one opportunity with the latest authoritative simulation summary."""

    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    latest_simulation = SimulationsRepository(session).get_latest_summary_for_opportunity(opportunity.id)
    return serialize_opportunity_detail(
        opportunity,
        latest_simulation=serialize_latest_simulation_optional(latest_simulation),
    )
