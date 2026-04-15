from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import RiskSettings
from constraint_scanner.core.clock import ensure_utc, utc_now
from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.enums import SimulationClassification, TradingMode
from constraint_scanner.core.types import ExposureState, RiskDecision
from constraint_scanner.db.models import Opportunity, SimulatedExecution
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.risk.approvals import approve, reject
from constraint_scanner.risk.exposure import opportunity_unresolved_notional_usd
from constraint_scanner.risk.kill_switch import KillSwitch


@dataclass(frozen=True, slots=True)
class RiskPolicySettings:
    """Typed runtime settings for deterministic risk gating."""

    min_edge_bps: Decimal = DECIMAL_ZERO
    min_confidence_score: Decimal = Decimal("0.80")
    max_legs: int = 8
    max_unresolved_notional_usd: Decimal = Decimal("1000")
    opportunity_stale_seconds: int = 30

    @classmethod
    def from_settings(cls, settings: RiskSettings) -> "RiskPolicySettings":
        """Convert app risk settings into Decimal-safe policy settings."""

        return cls(
            min_edge_bps=Decimal(str(settings.min_edge_bps)),
            min_confidence_score=Decimal(str(settings.min_confidence_score)),
            max_legs=settings.max_legs,
            max_unresolved_notional_usd=Decimal(str(settings.max_unresolved_notional_usd)),
            opportunity_stale_seconds=settings.opportunity_stale_seconds,
        )

    def as_detail_json(self) -> dict[str, str | int]:
        """Return stable threshold values for audit metadata."""

        return {
            "min_edge_bps": str(self.min_edge_bps),
            "min_confidence_score": str(self.min_confidence_score),
            "max_legs": self.max_legs,
            "max_unresolved_notional_usd": str(self.max_unresolved_notional_usd),
            "opportunity_stale_seconds": self.opportunity_stale_seconds,
        }


@dataclass(frozen=True, slots=True)
class SimulationGateView:
    """Minimal authoritative simulation view consumed by the risk policy."""

    simulation_run_id: str
    classification: SimulationClassification
    incident_flags: tuple[str, ...]
    result_json: dict[str, Any]


class RiskPolicy:
    """Deterministic risk gate over detector and simulator outputs."""

    def __init__(
        self,
        *,
        settings: RiskPolicySettings | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        app_settings = get_settings()
        self._settings = settings or RiskPolicySettings.from_settings(app_settings.risk)
        self._kill_switch = kill_switch or KillSwitch(active=app_settings.risk.kill_switch, reason="config_default")

    @property
    def settings(self) -> RiskPolicySettings:
        """Expose active policy thresholds."""

        return self._settings

    def evaluate_with_repository(
        self,
        *,
        opportunity: Opportunity,
        simulations_repository: SimulationsRepository,
        current_exposure: ExposureState,
        trading_mode: TradingMode,
        evaluated_at: datetime | None = None,
    ) -> RiskDecision:
        """Evaluate risk using the latest authoritative simulation summary row."""

        simulation_row = simulations_repository.get_latest_summary_for_opportunity(opportunity.id)
        return self.evaluate(
            opportunity=opportunity,
            simulation=simulation_row,
            current_exposure=current_exposure,
            trading_mode=trading_mode,
            evaluated_at=evaluated_at,
        )

    def evaluate(
        self,
        *,
        opportunity: Opportunity,
        simulation: SimulatedExecution | None,
        current_exposure: ExposureState,
        trading_mode: TradingMode,
        evaluated_at: datetime | None = None,
    ) -> RiskDecision:
        """Evaluate whether an opportunity is allowed to proceed."""

        active_evaluated_at = ensure_utc(evaluated_at or utc_now())
        kill_switch_snapshot = self._kill_switch.snapshot()
        metadata_base = {
            "opportunity_id": opportunity.id,
            "trading_mode": trading_mode.value,
            "evaluated_at": active_evaluated_at.isoformat(),
            "thresholds": self._settings.as_detail_json(),
            "kill_switch": {
                "active": kill_switch_snapshot.active,
                "reason": kill_switch_snapshot.reason,
                "updated_at": kill_switch_snapshot.updated_at,
            },
        }

        if kill_switch_snapshot.active:
            return reject(
                reason_code="kill_switch_active",
                reason="kill switch is active",
                metadata=metadata_base,
            )
        if trading_mode is TradingMode.DISABLED:
            return reject(
                reason_code="trading_disabled",
                reason="trading mode is disabled",
                metadata=metadata_base,
            )

        simulation_view = self._build_simulation_view(simulation)
        if simulation_view is None:
            return reject(
                reason_code="simulation_missing",
                reason="no authoritative simulation summary is available",
                metadata=metadata_base,
            )

        metadata_with_simulation = dict(metadata_base)
        metadata_with_simulation["simulation_run_id"] = simulation_view.simulation_run_id
        metadata_with_simulation["simulation_classification"] = simulation_view.classification.value
        metadata_with_simulation["simulation_incident_flags"] = list(simulation_view.incident_flags)

        if "timing_mismatch" in simulation_view.incident_flags:
            return reject(
                reason_code="simulation_timing_mismatch",
                reason="authoritative simulation flagged a timing mismatch",
                metadata=metadata_with_simulation,
            )
        if "stale_quote" in simulation_view.incident_flags:
            return reject(
                reason_code="simulation_stale_quote",
                reason="authoritative simulation flagged stale quotes",
                metadata=metadata_with_simulation,
            )
        if simulation_view.classification is not SimulationClassification.ROBUST:
            return reject(
                reason_code="simulation_not_robust",
                reason=f"authoritative simulation classification is {simulation_view.classification.value}",
                metadata=metadata_with_simulation,
            )

        last_seen_at = ensure_utc(opportunity.last_seen_at)
        opportunity_age_seconds = int((active_evaluated_at - last_seen_at).total_seconds())
        if opportunity_age_seconds > self._settings.opportunity_stale_seconds:
            metadata_with_simulation["opportunity_age_seconds"] = opportunity_age_seconds
            return reject(
                reason_code="opportunity_stale",
                reason="opportunity is older than the allowed stale threshold",
                metadata=metadata_with_simulation,
            )

        edge_bps = self._edge_bps(opportunity)
        if edge_bps < self._settings.min_edge_bps:
            metadata_with_simulation["edge_bps"] = str(edge_bps)
            return reject(
                reason_code="edge_below_minimum",
                reason="opportunity edge is below the configured minimum",
                metadata=metadata_with_simulation,
            )

        confidence_score = self._confidence_score(opportunity)
        if confidence_score < self._settings.min_confidence_score:
            metadata_with_simulation["confidence_score"] = str(confidence_score)
            return reject(
                reason_code="confidence_below_minimum",
                reason="opportunity confidence is below the configured minimum",
                metadata=metadata_with_simulation,
            )

        leg_count = self._leg_count(opportunity)
        if leg_count > self._settings.max_legs:
            metadata_with_simulation["leg_count"] = leg_count
            return reject(
                reason_code="max_legs_exceeded",
                reason="opportunity exceeds the configured max legs",
                metadata=metadata_with_simulation,
            )

        unresolved_notional = opportunity_unresolved_notional_usd(opportunity)
        projected_unresolved = current_exposure.unresolved_notional_usd + unresolved_notional
        metadata_with_simulation["current_unresolved_notional_usd"] = str(current_exposure.unresolved_notional_usd)
        metadata_with_simulation["projected_unresolved_notional_usd"] = str(projected_unresolved)
        if projected_unresolved > self._settings.max_unresolved_notional_usd:
            return reject(
                reason_code="unresolved_exposure_too_high",
                reason="projected unresolved exposure exceeds the configured limit",
                metadata=metadata_with_simulation,
            )

        remaining_capacity = max(self._settings.max_unresolved_notional_usd - current_exposure.unresolved_notional_usd, DECIMAL_ZERO)
        approved_size = min(remaining_capacity, unresolved_notional)
        metadata_with_simulation["approved_unresolved_notional_usd"] = str(unresolved_notional)
        metadata_with_simulation["approval_summary"] = {
            "edge_bps": str(edge_bps),
            "confidence_score": str(confidence_score),
            "leg_count": leg_count,
            "simulation_classification": simulation_view.classification.value,
            "expected_pnl_usd": self._simulation_pnl_value(simulation_view.result_json, "expected_pnl_usd"),
            "downside_bound_usd": self._simulation_pnl_value(simulation_view.result_json, "downside_bound_usd"),
            "gross_buy_cost": str(self._gross_buy_cost(opportunity)),
            "unresolved_notional_after_approval": str(projected_unresolved),
        }
        return approve(
            reason="risk policy approved",
            max_size_usd=approved_size,
            metadata=metadata_with_simulation,
        )

    def _build_simulation_view(self, simulation: SimulatedExecution | None) -> SimulationGateView | None:
        if simulation is None:
            return None

        payload = simulation.payload or {}
        classification_value = payload.get("classification")
        if not isinstance(classification_value, str):
            return None

        incident_flags = payload.get("incident_flags")
        result_json = payload.get("result_json")
        if not isinstance(incident_flags, list) or not isinstance(result_json, dict):
            return None

        return SimulationGateView(
            simulation_run_id=str(payload.get("simulation_run_id", simulation.simulation_run_id)),
            classification=SimulationClassification(classification_value),
            incident_flags=tuple(str(flag) for flag in incident_flags),
            result_json=result_json,
        )

    def _edge_bps(self, opportunity: Opportunity) -> Decimal:
        if opportunity.edge_bps is not None:
            return opportunity.edge_bps
        details = opportunity.details or {}
        pricing = details.get("pricing")
        if isinstance(pricing, dict) and pricing.get("net_edge_pct") is not None:
            return Decimal(str(pricing["net_edge_pct"])) * Decimal("10000")
        return DECIMAL_ZERO

    def _confidence_score(self, opportunity: Opportunity) -> Decimal:
        details = opportunity.details or {}
        ranking = details.get("ranking")
        if isinstance(ranking, dict) and ranking.get("confidence_score") is not None:
            return Decimal(str(ranking["confidence_score"]))
        return DECIMAL_ZERO

    def _gross_buy_cost(self, opportunity: Opportunity) -> Decimal:
        details = opportunity.details or {}
        pricing = details.get("pricing")
        if isinstance(pricing, dict) and pricing.get("gross_buy_cost") is not None:
            return Decimal(str(pricing["gross_buy_cost"]))
        return DECIMAL_ZERO

    def _leg_count(self, opportunity: Opportunity) -> int:
        details = opportunity.details or {}
        pricing = details.get("pricing")
        if isinstance(pricing, dict):
            legs = pricing.get("legs")
            if isinstance(legs, list):
                return len(legs)
        members = details.get("members")
        if isinstance(members, list):
            return len(members)
        return 0

    def _simulation_pnl_value(self, result_json: dict[str, Any], field_name: str) -> str | None:
        pnl = result_json.get("pnl")
        if not isinstance(pnl, dict):
            return None
        value = pnl.get(field_name)
        if value is None:
            return None
        return str(value)
