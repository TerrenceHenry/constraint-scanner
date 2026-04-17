from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import Market, Opportunity, SimulatedExecution, Token
from constraint_scanner.schemas.market import MarketResponse, TokenResponse
from constraint_scanner.schemas.opportunity import OpportunityDetailResponse, OpportunityListItemResponse
from constraint_scanner.schemas.simulation import LatestSimulationResponse


def serialize_token(token: Token) -> TokenResponse:
    """Serialize one token row into the API transport model."""

    return TokenResponse(
        id=token.id,
        market_id=token.market_id,
        external_id=token.external_id,
        symbol=token.symbol,
        outcome_name=token.outcome_name,
        outcome_index=token.outcome_index,
        created_at=token.created_at,
        updated_at=token.updated_at,
    )


def serialize_market(market: Market) -> MarketResponse:
    """Serialize one market row into the API transport model."""

    tokens = sorted(market.tokens, key=lambda token: (token.outcome_index, token.id))
    return MarketResponse(
        id=market.id,
        venue=market.venue,
        external_id=market.external_id,
        slug=market.slug,
        question=market.question,
        description=market.description,
        status=market.status,
        outcome_type=market.outcome_type,
        event_start_at=market.event_start_at,
        event_end_at=market.event_end_at,
        created_at=market.created_at,
        updated_at=market.updated_at,
        tokens=[serialize_token(token) for token in tokens],
    )


def serialize_latest_simulation(simulation: SimulatedExecution) -> LatestSimulationResponse:
    """Serialize one authoritative summary simulation row."""

    payload = simulation.payload or {}
    result_json = payload.get("result_json")
    result_json = result_json if isinstance(result_json, dict) else {}
    pnl = result_json.get("pnl")
    pnl = pnl if isinstance(pnl, dict) else {}

    return LatestSimulationResponse(
        id=simulation.id,
        opportunity_id=simulation.opportunity_id,
        simulation_run_id=simulation.simulation_run_id,
        summary_record=simulation.summary_record,
        executed_at=simulation.executed_at,
        classification=str(payload.get("classification", "non_executable")),
        fill_probability=_optional_decimal(payload.get("fill_probability")),
        expected_pnl_usd=_optional_decimal(payload.get("expected_pnl_usd") or pnl.get("expected_pnl_usd")),
        downside_bound_usd=_optional_decimal(payload.get("downside_bound_usd") or pnl.get("downside_bound_usd")),
        estimated_slippage_bps=_optional_decimal(
            payload.get("estimated_slippage_bps") or pnl.get("estimated_slippage_bps")
        ),
        incident_flags=_string_list(payload.get("incident_flags")),
        notes=_string_list(payload.get("notes")),
        details=result_json,
    )


def serialize_latest_simulation_optional(simulation: SimulatedExecution | None) -> LatestSimulationResponse | None:
    """Serialize one summary row when present."""

    if simulation is None:
        return None
    return serialize_latest_simulation(simulation)


def build_latest_simulation_map(session: Session, opportunity_ids: list[int]) -> dict[int, LatestSimulationResponse]:
    """Return latest authoritative simulation summaries keyed by opportunity id."""

    if not opportunity_ids:
        return {}

    stmt = (
        select(SimulatedExecution)
        .where(
            SimulatedExecution.summary_record.is_(True),
            SimulatedExecution.opportunity_id.in_(tuple(opportunity_ids)),
        )
        .order_by(SimulatedExecution.opportunity_id.asc(), desc(SimulatedExecution.executed_at), desc(SimulatedExecution.id))
    )

    latest_by_opportunity: dict[int, LatestSimulationResponse] = {}
    for simulation in session.scalars(stmt):
        if simulation.opportunity_id in latest_by_opportunity:
            continue
        latest_by_opportunity[simulation.opportunity_id] = serialize_latest_simulation(simulation)
    return latest_by_opportunity


def list_latest_simulations(
    session: Session,
    *,
    opportunity_id: int | None = None,
) -> list[LatestSimulationResponse]:
    """List latest authoritative summaries, one per opportunity."""

    stmt = (
        select(SimulatedExecution)
        .where(SimulatedExecution.summary_record.is_(True))
        .order_by(desc(SimulatedExecution.executed_at), desc(SimulatedExecution.id))
    )
    if opportunity_id is not None:
        stmt = stmt.where(SimulatedExecution.opportunity_id == opportunity_id)

    seen: set[int] = set()
    results: list[LatestSimulationResponse] = []
    for simulation in session.scalars(stmt):
        if simulation.opportunity_id in seen:
            continue
        seen.add(simulation.opportunity_id)
        results.append(serialize_latest_simulation(simulation))
    return results


def serialize_opportunity_summary(
    opportunity: Opportunity,
    *,
    latest_simulation: LatestSimulationResponse | None,
) -> OpportunityListItemResponse:
    """Serialize one opportunity row for list responses."""

    details = opportunity.details or {}
    ranking = details.get("ranking")
    ranking = ranking if isinstance(ranking, dict) else {}

    return OpportunityListItemResponse(
        id=opportunity.id,
        group_id=opportunity.group_id,
        constraint_id=opportunity.constraint_id,
        market_id=opportunity.market_id,
        token_id=opportunity.token_id,
        scope_key=opportunity.scope_key,
        persistence_key=opportunity.persistence_key,
        status=opportunity.status,
        detected_at=opportunity.detected_at,
        first_seen_at=opportunity.first_seen_at,
        last_seen_at=opportunity.last_seen_at,
        closed_at=opportunity.closed_at,
        score=opportunity.score,
        edge_bps=opportunity.edge_bps,
        expected_value_usd=opportunity.expected_value_usd,
        template_type=_optional_string(details.get("template_type")),
        confidence_score=_optional_decimal(ranking.get("confidence_score")),
        latest_simulation=latest_simulation,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
    )


def serialize_opportunity_detail(
    opportunity: Opportunity,
    *,
    latest_simulation: LatestSimulationResponse | None,
) -> OpportunityDetailResponse:
    """Serialize one opportunity row for detail responses."""

    summary = serialize_opportunity_summary(opportunity, latest_simulation=latest_simulation)
    return OpportunityDetailResponse(
        **summary.model_dump(),
        details=opportunity.details or {},
    )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
