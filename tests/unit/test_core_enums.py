from __future__ import annotations

from constraint_scanner.core.enums import (
    OpportunityState,
    SimulationClassification,
    StrategyType,
    TemplateType,
    TradingMode,
)


def test_strategy_enum_values_are_stable() -> None:
    assert StrategyType.ARBITRAGE.value == "arbitrage"
    assert StrategyType.HEDGE.value == "hedge"
    assert StrategyType.REBALANCE.value == "rebalance"


def test_template_enum_values_are_stable() -> None:
    assert TemplateType.BINARY_COMPLEMENT.value == "binary_complement"
    assert TemplateType.EXACT_ONE_OF_N.value == "exact_one_of_n"
    assert TemplateType.ONE_VS_FIELD.value == "one_vs_field"
    assert TemplateType.SUBSET_SUPERSET.value == "subset_superset"
    assert TemplateType.MUTUAL_EXCLUSION.value == "mutual_exclusion"
    assert TemplateType.AT_LEAST_ONE.value == "at_least_one"


def test_status_and_mode_enums_are_stable() -> None:
    assert OpportunityState.DETECTED.value == "detected"
    assert OpportunityState.EXECUTED.value == "executed"
    assert SimulationClassification.NON_EXECUTABLE.value == "non_executable"
    assert SimulationClassification.FRAGILE.value == "fragile"
    assert SimulationClassification.ROBUST.value == "robust"
    assert TradingMode.PAPER.value == "paper"
    assert TradingMode.DISABLED.value == "disabled"
