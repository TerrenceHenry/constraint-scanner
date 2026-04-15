from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from constraint_scanner.constraints.types import TemplateContext, TemplateMarketRef
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.core.types import BookLevel, BookSnapshot
from constraint_scanner.detection.intra_market import IntraMarketDetector


def _context() -> TemplateContext:
    return TemplateContext(
        template_type=TemplateType.BINARY_COMPLEMENT,
        group_id=1,
        group_key="group-1",
        members=(
            TemplateMarketRef(market_id=1, token_id=101, question="Will Alice win?", outcome_name="Yes"),
            TemplateMarketRef(market_id=2, token_id=202, question="Will Alice lose?", outcome_name="Yes"),
        ),
        assumptions={"reason": "complement"},
    )


def _book(token_id: int, ask_price: str, ask_size: str) -> BookSnapshot:
    return BookSnapshot(
        token_id=token_id,
        market_id=None,
        observed_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
        bids=(),
        asks=(BookLevel(price=Decimal(ask_price), size=Decimal(ask_size)),),
        source="test",
    )


def test_intra_market_detector_finds_binary_buy_basket_arbitrage() -> None:
    detector = IntraMarketDetector()
    outcome = detector.detect(
        context=_context(),
        books={
            101: _book(101, "0.48", "10"),
            202: _book(202, "0.47", "8"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is not None
    assert outcome.rejection_reason is None
    assert outcome.finding.candidate.expected_value_usd == Decimal("0.40")
    assert outcome.finding.detail_json["pricing"]["basket_quantity"] == "8"
    assert outcome.finding.detail_json["pricing"]["net_cost"] == "7.60"
    assert outcome.finding.detail_json["pricing"]["legs"][0]["requested_quantity"] == "8"
    assert outcome.finding.detail_json["pricing"]["legs"][0]["filled_quantity"] == "8"
    assert "consumed_depth" not in outcome.finding.detail_json["pricing"]
    assert outcome.finding.detail_json["ranking"]["formula"] == "max_executable_notional * net_edge_pct * confidence_score"
    assert "fill_probability_estimate" not in outcome.finding.detail_json["ranking"]


def test_intra_market_detector_rejects_when_buy_basket_cost_is_not_profitable() -> None:
    detector = IntraMarketDetector()
    outcome = detector.detect(
        context=_context(),
        books={
            101: _book(101, "0.55", "10"),
            202: _book(202, "0.50", "10"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is None
    assert outcome.rejection_reason == "basket cost is not below guaranteed payout"


def test_intra_market_detector_rejects_exact_one_without_exhaustiveness() -> None:
    detector = IntraMarketDetector()
    context = TemplateContext(
        template_type=TemplateType.EXACT_ONE_OF_N,
        group_id=1,
        group_key="group-2",
        members=(
            TemplateMarketRef(market_id=1, token_id=101, question="Will Alice win?", outcome_name="Yes"),
            TemplateMarketRef(market_id=2, token_id=202, question="Will Bob win?", outcome_name="Yes"),
        ),
    )

    outcome = detector.detect(
        context=context,
        books={
            101: _book(101, "0.20", "10"),
            202: _book(202, "0.20", "10"),
        },
        confidence_score=Decimal("0.90"),
        detected_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
    )

    assert outcome.finding is None
    assert outcome.rejection_reason == "exact_one_of_n requires explicit guaranteed exhaustiveness"
