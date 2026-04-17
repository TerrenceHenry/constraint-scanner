from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from constraint_scanner.api.dependencies import get_db_session
from constraint_scanner.api.serializers import serialize_market
from constraint_scanner.db.models import Market
from constraint_scanner.schemas.market import MarketPageResponse

router = APIRouter(tags=["markets"])


@router.get("/markets", response_model=MarketPageResponse)
def list_markets(
    session: Session = Depends(get_db_session),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MarketPageResponse:
    """List markets with tokens using one authoritative market representation."""

    stmt = select(Market).options(selectinload(Market.tokens)).order_by(Market.id.asc())
    count_stmt = select(func.count()).select_from(Market)

    if status is not None:
        stmt = stmt.where(Market.status == status)
        count_stmt = count_stmt.where(Market.status == status)

    total = session.scalar(count_stmt) or 0
    markets = list(session.scalars(stmt.limit(limit).offset(offset)))
    return MarketPageResponse(
        items=[serialize_market(market) for market in markets],
        total=int(total),
        limit=limit,
        offset=offset,
    )
