from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.enums import SimulationClassification
from constraint_scanner.core.types import BookLevel, BookSnapshot
from constraint_scanner.db.models import Opportunity
from constraint_scanner.simulation.engine import SimulationEngine


def _opportunity(*, opportunity_id: int = 1) -> Opportunity:
    detected_at = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    return Opportunity(
        id=opportunity_id,
        scope_key="constraint:1",
        persistence_key=f"constraint-1:opp-{opportunity_id}",
        detected_at=detected_at,
        first_seen_at=detected_at,
        last_seen_at=detected_at,
        status="open",
        details={
            "template_type": "binary_complement",
            "state_payoff_summary": [
                {
                    "state_id": "s1",
                    "label": "A wins",
                    "gross_payoff_per_basket": "1",
                    "net_payoff_per_basket": "0.05",
                    "net_payoff_total": "0.50",
                }
            ],
            "pricing": {
                "basket_quantity": "10",
                "gross_buy_cost": "9.50",
                "gross_sell_proceeds": "0",
                "net_cost": "9.50",
                "legs": [
                    {
                        "market_id": 1,
                        "token_id": 101,
                        "role": "complement_leg",
                        "side": "buy",
                        "requested_quantity": "10",
                        "filled_quantity": "10",
                        "weighted_average_price": "0.48",
                        "total_notional": "4.80",
                        "fully_filled": True,
                        "consumed_depth": [{"price": "0.48", "available_quantity": "10", "filled_quantity": "10"}],
                    },
                    {
                        "market_id": 2,
                        "token_id": 202,
                        "role": "complement_leg",
                        "side": "buy",
                        "requested_quantity": "10",
                        "filled_quantity": "10",
                        "weighted_average_price": "0.47",
                        "total_notional": "4.70",
                        "fully_filled": True,
                        "consumed_depth": [{"price": "0.47", "available_quantity": "10", "filled_quantity": "10"}],
                    },
                ],
            },
        },
    )


def _book(
    token_id: int,
    *,
    market_id: int,
    bids: tuple[tuple[str, str], ...] = (),
    asks: tuple[tuple[str, str], ...],
    observed_at: datetime,
) -> BookSnapshot:
    return BookSnapshot(
        token_id=token_id,
        market_id=market_id,
        observed_at=observed_at,
        bids=tuple(BookLevel(price=Decimal(price), size=Decimal(size)) for price, size in bids),
        asks=tuple(BookLevel(price=Decimal(price), size=Decimal(size)) for price, size in asks),
        source="test",
    )


def test_simulation_engine_classifies_perfect_fill_as_robust() -> None:
    simulated_at = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    engine = SimulationEngine(
        settings=SimulationSettings(
            slippage_bps=0,
            per_extra_level_slippage_bps=0,
            stale_quote_seconds=30,
            robust_fill_probability_threshold=0.95,
        )
    )

    result = engine.simulate(
        opportunity=_opportunity(),
        books={
            101: _book(101, market_id=1, asks=(("0.48", "10"),), observed_at=simulated_at),
            202: _book(202, market_id=2, asks=(("0.47", "10"),), observed_at=simulated_at),
        },
        simulated_at=simulated_at,
    )

    assert result.classification is SimulationClassification.ROBUST
    assert result.simulation_run_id.startswith("simrun_")
    assert result.fill_probability == Decimal("1")
    assert result.expected_pnl_usd == Decimal("0.50")
    assert result.downside_bound_usd == Decimal("0.50")
    assert result.incident_flags == ()


def test_simulation_engine_flags_shallow_miss_as_fragile() -> None:
    simulated_at = datetime(2026, 4, 15, 12, 1, tzinfo=timezone.utc)
    engine = SimulationEngine(
        settings=SimulationSettings(
            slippage_bps=0,
            per_extra_level_slippage_bps=0,
        )
    )

    result = engine.simulate(
        opportunity=_opportunity(opportunity_id=2),
        books={
            101: _book(
                101,
                market_id=1,
                bids=(("0.40", "4"),),
                asks=(("0.48", "10"),),
                observed_at=simulated_at,
            ),
            202: _book(202, market_id=2, asks=(("0.05", "6"),), observed_at=simulated_at),
        },
        simulated_at=simulated_at,
    )

    assert result.classification is SimulationClassification.FRAGILE
    assert "shallow_miss" in result.incident_flags
    assert "partial_fill" in result.incident_flags
    assert result.details["pricing"]["completed_basket_quantity"] == "6"
    assert result.expected_pnl_usd > result.downside_bound_usd


def test_simulation_engine_flags_stale_quote_as_fragile() -> None:
    simulated_at = datetime(2026, 4, 15, 12, 2, tzinfo=timezone.utc)
    stale_at = simulated_at - timedelta(seconds=120)
    engine = SimulationEngine(
        settings=SimulationSettings(
            stale_quote_seconds=15,
            stale_quote_fill_probability_factor=0.5,
        )
    )

    result = engine.simulate(
        opportunity=_opportunity(opportunity_id=3),
        books={
            101: _book(101, market_id=1, asks=(("0.48", "10"),), observed_at=stale_at),
            202: _book(202, market_id=2, asks=(("0.47", "10"),), observed_at=simulated_at),
        },
        simulated_at=simulated_at,
    )

    assert result.classification is SimulationClassification.FRAGILE
    assert "stale_quote" in result.incident_flags
    assert result.fill_probability == Decimal("0.5")
    assert result.details["pricing"]["legs"][0]["timing"]["live_book_observed_at"] == stale_at.isoformat()
    assert result.details["timing"]["stale_quote_threshold_seconds"] == 15


def test_simulation_engine_flags_leg_asymmetry_when_depth_consumption_is_skewed() -> None:
    simulated_at = datetime(2026, 4, 15, 12, 3, tzinfo=timezone.utc)
    engine = SimulationEngine(
        settings=SimulationSettings(
            slippage_bps=0,
            per_extra_level_slippage_bps=0,
            leg_asymmetry_level_gap_threshold=2,
        )
    )

    result = engine.simulate(
        opportunity=_opportunity(opportunity_id=4),
        books={
            101: _book(101, market_id=1, asks=(("0.47", "4"), ("0.48", "3"), ("0.49", "3")), observed_at=simulated_at),
            202: _book(202, market_id=2, asks=(("0.45", "10"),), observed_at=simulated_at),
        },
        simulated_at=simulated_at,
    )

    assert result.classification is SimulationClassification.FRAGILE
    assert "leg_asymmetry" in result.incident_flags
    assert result.details["fill_model"]["leg_asymmetry_level_gap"] == 2


def test_simulation_engine_classifies_negative_expected_pnl_as_non_executable() -> None:
    simulated_at = datetime(2026, 4, 15, 12, 4, tzinfo=timezone.utc)
    engine = SimulationEngine(
        settings=SimulationSettings(
            slippage_bps=0,
            per_extra_level_slippage_bps=0,
        )
    )

    result = engine.simulate(
        opportunity=_opportunity(opportunity_id=5),
        books={
            101: _book(101, market_id=1, asks=(("0.55", "10"),), observed_at=simulated_at),
            202: _book(202, market_id=2, asks=(("0.50", "10"),), observed_at=simulated_at),
        },
        simulated_at=simulated_at,
    )

    assert result.classification is SimulationClassification.NON_EXECUTABLE
    assert "negative_expected_pnl" in result.incident_flags
    assert result.expected_pnl_usd == Decimal("-0.50")


def test_simulation_engine_marks_future_book_timestamps_as_timing_mismatch() -> None:
    simulated_at = datetime(2026, 4, 15, 12, 5, tzinfo=timezone.utc)
    future_book_at = simulated_at + timedelta(seconds=5)
    engine = SimulationEngine(
        settings=SimulationSettings(
            slippage_bps=0,
            per_extra_level_slippage_bps=0,
        )
    )

    result = engine.simulate(
        opportunity=_opportunity(opportunity_id=6),
        books={
            101: _book(101, market_id=1, asks=(("0.48", "10"),), observed_at=future_book_at),
            202: _book(202, market_id=2, asks=(("0.47", "10"),), observed_at=simulated_at),
        },
        simulated_at=simulated_at,
    )

    first_leg_timing = result.details["pricing"]["legs"][0]["timing"]
    assert result.classification is SimulationClassification.NON_EXECUTABLE
    assert "timing_mismatch" in result.incident_flags
    assert first_leg_timing["quote_age_seconds"] == -5
    assert first_leg_timing["timing_mismatch"] is True
