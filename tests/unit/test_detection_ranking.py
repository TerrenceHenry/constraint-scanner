from __future__ import annotations

from decimal import Decimal

from constraint_scanner.detection.ranking import compute_ranking_score


def test_compute_ranking_score_uses_transparent_formula() -> None:
    score = compute_ranking_score(
        max_executable_notional=Decimal("100"),
        net_edge_pct=Decimal("0.05"),
        confidence_score=Decimal("0.75"),
    )

    assert score == Decimal("3.75")
