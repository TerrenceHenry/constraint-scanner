from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from constraint_scanner.core.enums import OpportunityState, SimulationClassification, StrategyType, TemplateType, TradingMode
from constraint_scanner.schemas.control import TradingControlPayload
from constraint_scanner.schemas.market import MarketResponse, TokenResponse
from constraint_scanner.schemas.opportunity import OpportunityResponse
from constraint_scanner.schemas.orderbook import OrderbookResponse
from constraint_scanner.schemas.simulation import SimulationResponse


def test_market_response_validates_nested_tokens() -> None:
    now = datetime.now(timezone.utc)
    market = MarketResponse(
        id=1,
        venue="polymarket",
        external_id="market-1",
        slug="market-1",
        question="Will this validate?",
        status="active",
        created_at=now,
        updated_at=now,
        tokens=[
            TokenResponse(
                id=10,
                market_id=1,
                external_id="token-yes",
                symbol="YES",
                outcome_name="YES",
                outcome_index=0,
                created_at=now,
                updated_at=now,
            )
        ],
    )

    assert market.tokens[0].outcome_name == "YES"


def test_orderbook_response_validates_decimal_levels() -> None:
    orderbook = OrderbookResponse(
        token_id=1,
        market_id=2,
        observed_at=datetime.now(timezone.utc),
        bids=[{"price": "0.45", "size": "100"}],
        asks=[{"price": Decimal("0.47"), "size": Decimal("120")}],
        midpoint_diagnostic="0.46",
        source="replay",
    )

    assert orderbook.bids[0].price == Decimal("0.45")
    assert orderbook.midpoint_diagnostic == Decimal("0.46")


def test_opportunity_and_simulation_schema_validate_enums() -> None:
    now = datetime.now(timezone.utc)
    opportunity = OpportunityResponse(
        candidate_id="opp-1",
        strategy_type=StrategyType.ARBITRAGE,
        template_type=TemplateType.BINARY_COMPLEMENT,
        state=OpportunityState.DETECTED,
        detected_at=now,
        expected_edge_bps="12.5",
        expected_value_usd="4.25",
        legs=[{"market_id": 1, "token_id": 2, "side": "buy", "price": "0.45", "quantity": "10"}],
    )
    simulation = SimulationResponse(
        candidate_id="opp-1",
        classification=SimulationClassification.PASS,
        simulated_at=now,
        estimated_fill_rate="0.9",
        estimated_slippage_bps="2.5",
        estimated_pnl_usd="3.75",
    )

    assert opportunity.strategy_type is StrategyType.ARBITRAGE
    assert simulation.classification is SimulationClassification.PASS


def test_trading_control_payload_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        TradingControlPayload(mode="unsafe", reason="bad")

    payload = TradingControlPayload(mode=TradingMode.PAPER)
    assert payload.mode is TradingMode.PAPER
