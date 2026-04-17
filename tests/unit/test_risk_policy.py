from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from constraint_scanner.core.enums import SimulationClassification, TradingMode
from constraint_scanner.core.types import ExposureState
from constraint_scanner.db.models import Opportunity, SimulatedExecution
from constraint_scanner.risk.exposure import build_exposure_state
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.risk.policy import RiskPolicy, RiskPolicySettings

BASE_TIME = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
FRESH_EVALUATED_AT = BASE_TIME + timedelta(seconds=15)


def _opportunity(
    *,
    opportunity_id: int = 1,
    edge_bps: str = "50",
    confidence_score: str = "0.90",
    gross_buy_cost: str = "100",
    net_cost: str = "100",
    leg_count: int = 2,
    last_seen_at: datetime | None = None,
    status: str = "open",
) -> Opportunity:
    detected_at = BASE_TIME
    active_last_seen_at = last_seen_at or detected_at
    pricing_legs = [
        {
            "market_id": opportunity_id * 10 + index,
            "token_id": opportunity_id * 100 + index,
            "side": "buy",
            "total_notional": str(Decimal(gross_buy_cost) / Decimal(leg_count)),
        }
        for index in range(1, leg_count + 1)
    ]
    return Opportunity(
        id=opportunity_id,
        group_id=opportunity_id,
        scope_key=f"constraint:{opportunity_id}",
        persistence_key=f"opp-{opportunity_id}",
        detected_at=detected_at,
        first_seen_at=detected_at,
        last_seen_at=active_last_seen_at,
        status=status,
        edge_bps=Decimal(edge_bps),
        details={
            "pricing": {
                "gross_buy_cost": gross_buy_cost,
                "net_cost": net_cost,
                "legs": pricing_legs,
            },
            "ranking": {
                "confidence_score": confidence_score,
            },
        },
    )


def _simulation(
    *,
    opportunity_id: int = 1,
    run_id: str = "simrun-1",
    classification: SimulationClassification = SimulationClassification.ROBUST,
    incident_flags: tuple[str, ...] = (),
    expected_pnl_usd: str = "12.50",
    downside_bound_usd: str = "3.25",
) -> SimulatedExecution:
    return SimulatedExecution(
        opportunity_id=opportunity_id,
        simulation_run_id=run_id,
        summary_record=True,
        executed_at=BASE_TIME,
        side=None,
        price=None,
        quantity=None,
        pnl_impact_usd=Decimal("1.00"),
        payload={
            "record_type": "simulation_summary",
            "simulation_run_id": run_id,
            "classification": classification.value,
            "incident_flags": list(incident_flags),
            "result_json": {
                "pnl": {
                    "expected_pnl_usd": expected_pnl_usd,
                    "downside_bound_usd": downside_bound_usd,
                }
            },
        },
    )


def _exposure(*, unresolved: str = "0") -> ExposureState:
    return ExposureState(
        unresolved_notional_usd=Decimal(unresolved),
        open_basket_count=0,
        gross_exposure_usd=Decimal(unresolved),
        net_exposure_usd=Decimal(unresolved),
        open_order_count=0,
    )


def test_risk_policy_rejects_trading_disabled() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate(
        opportunity=_opportunity(),
        simulation=_simulation(),
        current_exposure=_exposure(),
        trading_mode=TradingMode.DISABLED,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.approved is False
    assert decision.reason_code == "trading_disabled"


def test_risk_policy_rejects_edge_below_minimum() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(min_edge_bps=Decimal("75")),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate(
        opportunity=_opportunity(edge_bps="50"),
        simulation=_simulation(),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "edge_below_minimum"


def test_risk_policy_rejects_confidence_below_minimum() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(min_confidence_score=Decimal("0.95")),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate(
        opportunity=_opportunity(confidence_score="0.90"),
        simulation=_simulation(),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "confidence_below_minimum"


def test_risk_policy_rejects_simulation_not_robust() -> None:
    policy = RiskPolicy(kill_switch=KillSwitch(active=False))

    decision = policy.evaluate(
        opportunity=_opportunity(),
        simulation=_simulation(classification=SimulationClassification.FRAGILE),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "simulation_not_robust"


def test_risk_policy_rejects_opportunity_stale() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(opportunity_stale_seconds=30),
        kill_switch=KillSwitch(active=False),
    )
    evaluated_at = BASE_TIME + timedelta(minutes=2)

    decision = policy.evaluate(
        opportunity=_opportunity(last_seen_at=evaluated_at - timedelta(seconds=45)),
        simulation=_simulation(),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=evaluated_at,
    )

    assert decision.reason_code == "opportunity_stale"


def test_risk_policy_rejects_max_legs_exceeded() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(max_legs=1),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate(
        opportunity=_opportunity(leg_count=2),
        simulation=_simulation(),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "max_legs_exceeded"


def test_risk_policy_rejects_unresolved_exposure_too_high() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(max_unresolved_notional_usd=Decimal("1000")),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate(
        opportunity=_opportunity(gross_buy_cost="150"),
        simulation=_simulation(),
        current_exposure=_exposure(unresolved="900"),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "unresolved_exposure_too_high"


def test_risk_policy_rejects_kill_switch_override() -> None:
    policy = RiskPolicy(kill_switch=KillSwitch(active=True, reason="manual"))

    decision = policy.evaluate(
        opportunity=_opportunity(),
        simulation=_simulation(),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "kill_switch_active"


def test_risk_policy_rejects_stale_quote_flag_conservatively() -> None:
    policy = RiskPolicy(kill_switch=KillSwitch(active=False))

    decision = policy.evaluate(
        opportunity=_opportunity(),
        simulation=_simulation(incident_flags=("stale_quote",)),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "simulation_stale_quote"


def test_risk_policy_rejects_timing_mismatch_flag_conservatively() -> None:
    policy = RiskPolicy(kill_switch=KillSwitch(active=False))

    decision = policy.evaluate(
        opportunity=_opportunity(),
        simulation=_simulation(
            classification=SimulationClassification.NON_EXECUTABLE,
            incident_flags=("timing_mismatch",),
        ),
        current_exposure=_exposure(),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.reason_code == "simulation_timing_mismatch"


def test_risk_policy_approves_robust_case() -> None:
    policy = RiskPolicy(
        settings=RiskPolicySettings(
            min_edge_bps=Decimal("10"),
            min_confidence_score=Decimal("0.80"),
            max_legs=4,
            max_unresolved_notional_usd=Decimal("1000"),
            opportunity_stale_seconds=60,
        ),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate(
        opportunity=_opportunity(edge_bps="50", confidence_score="0.90", gross_buy_cost="100"),
        simulation=_simulation(),
        current_exposure=_exposure(unresolved="200"),
        trading_mode=TradingMode.PAPER,
        evaluated_at=FRESH_EVALUATED_AT,
    )

    assert decision.approved is True
    assert decision.reason_code == "approved"
    assert decision.max_size_usd == Decimal("100")
    assert decision.metadata["approval_summary"] == {
        "edge_bps": "50",
        "confidence_score": "0.90",
        "leg_count": 2,
        "simulation_classification": "robust",
        "expected_pnl_usd": "12.50",
        "downside_bound_usd": "3.25",
        "gross_buy_cost": "100",
        "unresolved_notional_after_approval": "300",
    }


def test_build_exposure_state_tracks_unresolved_and_breakdowns() -> None:
    open_one = _opportunity(opportunity_id=11, gross_buy_cost="100", leg_count=2)
    open_two = _opportunity(opportunity_id=12, gross_buy_cost="50", leg_count=1)
    closed = _opportunity(opportunity_id=13, gross_buy_cost="70", status="closed")

    exposure = build_exposure_state([open_one, open_two, closed], open_order_count=3)

    assert exposure.unresolved_notional_usd == Decimal("150")
    assert exposure.open_basket_count == 2
    assert exposure.open_order_count == 3
    assert exposure.group_exposure_usd[11] == Decimal("100")
    assert exposure.group_exposure_usd[12] == Decimal("50")
    assert exposure.market_exposure_usd[111] == Decimal("50")
    assert exposure.market_exposure_usd[121] == Decimal("50")
    assert exposure.reporting_basis["unresolved_notional_usd"] == "sum(open opportunity pricing.gross_buy_cost)"
    assert "pricing.legs[*].total_notional" in exposure.reporting_basis["market_exposure_usd"]
