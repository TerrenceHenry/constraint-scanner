from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.exceptions import TradingValidationError
from constraint_scanner.core.types import RiskDecision
from constraint_scanner.db.models import Opportunity
from constraint_scanner.trading.order_builder import build_order_requests


def test_build_order_requests_scales_to_approved_notional_and_preserves_tif() -> None:
    opportunity = Opportunity(
        id=7,
        group_id=1,
        scope_key="constraint:7",
        persistence_key="opp-7",
        detected_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        first_seen_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        status="open",
        details={
            "pricing": {
                "gross_buy_cost": "100",
                "legs": [
                    {
                        "market_id": 101,
                        "token_id": 1001,
                        "role": "member",
                        "side": "buy",
                        "requested_quantity": "10",
                        "filled_quantity": "10",
                        "weighted_average_price": "0.40",
                        "total_notional": "4",
                        "consumed_depth": [],
                    },
                    {
                        "market_id": 102,
                        "token_id": 1002,
                        "role": "member",
                        "side": "buy",
                        "requested_quantity": "30",
                        "filled_quantity": "30",
                        "weighted_average_price": "0.20",
                        "total_notional": "6",
                        "consumed_depth": [],
                    },
                ],
            }
        },
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("50"),
        metadata={"simulation_run_id": "sim-7"},
    )

    result = build_order_requests(
        opportunity=opportunity,
        risk_decision=decision,
        trading_mode=TradingMode.PAPER,
        tif="IOC",
        submitted_at=datetime(2026, 4, 15, 16, 1, tzinfo=timezone.utc),
    )

    assert result.gross_buy_cost == Decimal("100")
    assert result.approved_notional_usd == Decimal("50")
    assert result.scale_factor == Decimal("0.5")
    assert result.rounded_total_notional_usd == Decimal("5.0000000000000000")
    assert [request.time_in_force for request in result.requests] == ["IOC", "IOC"]
    assert [request.quantity for request in result.requests] == [Decimal("5.00000000"), Decimal("15.00000000")]
    assert result.requests[0].metadata["simulation_run_id"] == "sim-7"
    assert result.requests[0].metadata["scaled_quantity"] == "5.00000000"


def test_build_order_requests_rejects_missing_approved_notional() -> None:
    opportunity = Opportunity(
        id=8,
        group_id=1,
        scope_key="constraint:8",
        persistence_key="opp-8",
        detected_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        first_seen_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        status="open",
        details={
            "pricing": {
                "gross_buy_cost": "10",
                "legs": [
                    {
                        "market_id": 101,
                        "token_id": 1001,
                        "side": "buy",
                        "requested_quantity": "10",
                        "weighted_average_price": "0.50",
                        "total_notional": "5",
                    }
                ],
            }
        },
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=None,
        metadata={"simulation_run_id": "sim-8"},
    )

    with pytest.raises(TradingValidationError, match="max_size_usd"):
        build_order_requests(
            opportunity=opportunity,
            risk_decision=decision,
            trading_mode=TradingMode.PAPER,
            tif="GTC",
            submitted_at=datetime(2026, 4, 15, 16, 1, tzinfo=timezone.utc),
        )


def test_build_order_requests_rejects_zero_approved_notional() -> None:
    opportunity = Opportunity(
        id=9,
        group_id=1,
        scope_key="constraint:9",
        persistence_key="opp-9",
        detected_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        first_seen_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        status="open",
        details={
            "pricing": {
                "gross_buy_cost": "10",
                "legs": [
                    {
                        "market_id": 101,
                        "token_id": 1001,
                        "side": "buy",
                        "requested_quantity": "10",
                        "weighted_average_price": "0.50",
                        "total_notional": "5",
                    }
                ],
            }
        },
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("0"),
        metadata={"simulation_run_id": "sim-9"},
    )

    with pytest.raises(TradingValidationError, match="approved notional"):
        build_order_requests(
            opportunity=opportunity,
            risk_decision=decision,
            trading_mode=TradingMode.PAPER,
            tif="GTC",
            submitted_at=datetime(2026, 4, 15, 16, 1, tzinfo=timezone.utc),
        )
