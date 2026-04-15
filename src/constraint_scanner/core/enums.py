from __future__ import annotations

from enum import Enum


class StrategyType(str, Enum):
    """High-level strategy family for a detected opportunity."""

    ARBITRAGE = "arbitrage"
    HEDGE = "hedge"
    REBALANCE = "rebalance"


class TemplateType(str, Enum):
    """Template-based combinatorial detector types."""

    BINARY_COMPLEMENT = "binary_complement"
    EXACT_ONE_OF_N = "exact_one_of_n"
    ONE_VS_FIELD = "one_vs_field"
    SUBSET_SUPERSET = "subset_superset"
    MUTUAL_EXCLUSION = "mutual_exclusion"
    AT_LEAST_ONE = "at_least_one"


class OpportunityState(str, Enum):
    """Lifecycle state of an opportunity candidate."""

    DETECTED = "detected"
    QUALIFIED = "qualified"
    SIMULATED = "simulated"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class SimulationClassification(str, Enum):
    """Result classification for execution simulation."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    SKIP = "skip"


class TradingMode(str, Enum):
    """Trading control mode. Live trading stays disabled by default."""

    DISABLED = "disabled"
    PAPER = "paper"
    LIVE = "live"
