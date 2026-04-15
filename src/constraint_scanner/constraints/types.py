from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from constraint_scanner.core.enums import TemplateType


@dataclass(frozen=True, slots=True)
class TemplateMarketRef:
    """Auditable market/token reference consumed by a template."""

    market_id: int
    token_id: int
    question: str
    outcome_name: str
    role: str = "member"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TemplateContext:
    """Explicit template context with assumptions and ordered members."""

    template_type: TemplateType
    group_id: int | None
    group_key: str
    members: tuple[TemplateMarketRef, ...]
    assumptions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TemplateValidation:
    """Validation output for a template context."""

    valid: bool
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConstraintState:
    """Single mutually exclusive state used for deterministic evaluation."""

    state_id: str
    label: str
    payouts_by_token: dict[int, Decimal]


@dataclass(frozen=True, slots=True)
class StatePayoff:
    """Per-state payoff output after applying input pricing."""

    state_id: str
    label: str
    gross_payoff: Decimal
    net_payoff: Decimal


@dataclass(frozen=True, slots=True)
class TemplateEvaluation:
    """Auditable template evaluation result for a pricing snapshot."""

    template_type: TemplateType
    total_cost: Decimal
    state_payoffs: tuple[StatePayoff, ...]
    min_net_payoff: Decimal
    max_net_payoff: Decimal
    assumptions: dict[str, Any] = field(default_factory=dict)


def exhaustiveness_assumptions(context: TemplateContext) -> dict[str, Any]:
    """Return normalized exhaustiveness assumptions for a template context."""

    value = context.assumptions.get("exhaustiveness", {})
    return dict(value) if isinstance(value, dict) else {}


def has_guaranteed_exhaustiveness(context: TemplateContext) -> bool:
    """Return whether the context carries an explicit exhaustiveness guarantee."""

    assumptions = exhaustiveness_assumptions(context)
    return assumptions.get("guaranteed") is True and bool(assumptions.get("basis"))
