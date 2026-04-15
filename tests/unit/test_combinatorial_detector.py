from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from constraint_scanner.constraints.types import TemplateContext, TemplateMarketRef
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.core.types import BookLevel, BookSnapshot
from constraint_scanner.detection.combinatorial import CombinatorialDetector


def _book(token_id: int, ask_price: str, ask_size: str) -> BookSnapshot:
    return BookSnapshot(
        token_id=token_id,
        market_id=None,
        observed_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
        bids=(),
        asks=(BookLevel(price=Decimal(ask_price), size=Decimal(ask_size)),),
        source="test",
    )


def test_combinatorial_detector_finds_binary_complement_opportunity() -> None:
    detector = CombinatorialDetector()
    context = TemplateContext(
        template_type=TemplateType.BINARY_COMPLEMENT,
        group_id=1,
        group_key="binary-group",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 202, "Will Alice lose?", "Yes"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "binary_complement"}},
    )

    outcome = detector.detect(
        context=context,
        books={
            101: _book(101, "0.48", "10"),
            202: _book(202, "0.47", "10"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is not None
    assert outcome.finding.candidate.expected_value_usd == Decimal("0.50")
    assert outcome.finding.detail_json["template_type"] == "binary_complement"
    assert outcome.finding.detail_json["state_payoff_summary"][0]["gross_payoff_per_basket"] == "1"


def test_combinatorial_detector_finds_exact_one_of_n_opportunity() -> None:
    detector = CombinatorialDetector()
    context = TemplateContext(
        template_type=TemplateType.EXACT_ONE_OF_N,
        group_id=2,
        group_key="exact-group",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 102, "Will Bob win?", "Yes"),
            TemplateMarketRef(3, 103, "Will Carol win?", "Yes"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "native_market_defined"}},
    )

    outcome = detector.detect(
        context=context,
        books={
            101: _book(101, "0.30", "10"),
            102: _book(102, "0.31", "10"),
            103: _book(103, "0.32", "10"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is not None
    assert outcome.finding.detail_json["members"][2]["token_id"] == 103
    assert outcome.finding.detail_json["pricing"]["legs"][1]["weighted_average_price"] == "0.31"


def test_combinatorial_detector_finds_one_vs_field_opportunity() -> None:
    detector = CombinatorialDetector()
    context = TemplateContext(
        template_type=TemplateType.ONE_VS_FIELD,
        group_id=3,
        group_key="ovf-group",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes", role="one"),
            TemplateMarketRef(2, 102, "Will the field win?", "Yes", role="field"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "manual_constraint_override"}},
    )

    outcome = detector.detect(
        context=context,
        books={
            101: _book(101, "0.42", "10"),
            102: _book(102, "0.49", "10"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is not None
    assert outcome.finding.candidate.expected_edge_bps == Decimal("989.0109890109890109890109890")
    assert outcome.finding.detail_json["members"][1]["role"] == "field"


def test_combinatorial_detector_rejects_when_constraint_exceeds_max_legs() -> None:
    detector = CombinatorialDetector(max_legs=2)
    context = TemplateContext(
        template_type=TemplateType.EXACT_ONE_OF_N,
        group_id=4,
        group_key="too-many-legs",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 102, "Will Bob win?", "Yes"),
            TemplateMarketRef(3, 103, "Will Carol win?", "Yes"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "native_market_defined"}},
    )

    outcome = detector.detect(
        context=context,
        books={},
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is None
    assert outcome.rejection_reason == "constraint has 3 legs which exceeds max_legs=2"


def test_combinatorial_detector_rejects_low_confidence() -> None:
    detector = CombinatorialDetector(confidence_threshold=Decimal("0.95"))
    context = TemplateContext(
        template_type=TemplateType.BINARY_COMPLEMENT,
        group_id=5,
        group_key="low-confidence",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 202, "Will Alice lose?", "Yes"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "binary_complement"}},
    )

    outcome = detector.detect(
        context=context,
        books={
            101: _book(101, "0.48", "10"),
            202: _book(202, "0.47", "10"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is None
    assert outcome.rejection_reason == "confidence 0.90 is below threshold 0.95"
