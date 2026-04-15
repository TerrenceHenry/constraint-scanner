from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.enums import (
    OpportunityState,
    SimulationClassification,
    StrategyType,
    TemplateType,
    TradingMode,
)

OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class BookLevel:
    """Single executable order book level."""

    price: Decimal
    size: Decimal


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """Point-in-time book snapshot for a single token.

    Midpoint values derived from this structure are diagnostic only and should
    never be treated as executable pricing.
    """

    token_id: int
    market_id: int | None
    observed_at: datetime
    bids: tuple[BookLevel, ...] = field(default_factory=tuple)
    asks: tuple[BookLevel, ...] = field(default_factory=tuple)
    source: str = "unknown"
    sequence_number: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))


@dataclass(frozen=True, slots=True)
class OpportunityLeg:
    """Single executable leg inside a candidate opportunity."""

    market_id: int
    token_id: int
    side: OrderSide
    price: Decimal
    quantity: Decimal
    note: str | None = None


@dataclass(frozen=True, slots=True)
class OpportunityCandidate:
    """Template-based candidate opportunity before execution."""

    candidate_id: str
    strategy_type: StrategyType
    template_type: TemplateType
    state: OpportunityState
    detected_at: datetime
    legs: tuple[OpportunityLeg, ...]
    expected_edge_bps: Decimal
    expected_value_usd: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "detected_at", ensure_utc(self.detected_at))


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Deterministic record of a paper execution simulation."""

    candidate_id: str
    classification: SimulationClassification
    simulated_at: datetime
    estimated_fill_rate: Decimal
    estimated_slippage_bps: Decimal
    estimated_pnl_usd: Decimal
    notes: tuple[str, ...] = field(default_factory=tuple)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulated_at", ensure_utc(self.simulated_at))


@dataclass(frozen=True, slots=True)
class ExposureState:
    """Current paper or live exposure snapshot used for risk decisions."""

    gross_exposure_usd: Decimal
    net_exposure_usd: Decimal
    open_order_count: int
    market_exposure_usd: dict[int, Decimal] = field(default_factory=dict)
    token_exposure_usd: dict[int, Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Output of a simple, auditable risk gate."""

    approved: bool
    reason_code: str
    reason: str
    max_size_usd: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Executable order request prepared for paper or live adapters."""

    client_order_id: str
    market_id: int
    token_id: int
    side: OrderSide
    price: Decimal
    quantity: Decimal
    trading_mode: TradingMode = TradingMode.PAPER
    time_in_force: str = "GTC"
    metadata: dict[str, Any] = field(default_factory=dict)
