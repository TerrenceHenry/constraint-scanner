from __future__ import annotations

from decimal import Decimal

from constraint_scanner.catalog.entity_extractor import extract_entities
from constraint_scanner.catalog.grouping import CatalogMarketRecord, group_markets
from constraint_scanner.catalog.market_classifier import classify_market
from constraint_scanner.catalog.normalizer import normalize_market_text


def _record(market_id: int, question: str, *, outcomes: tuple[str, ...] = ("Yes", "No")) -> CatalogMarketRecord:
    normalized = normalize_market_text(question)
    entities = extract_entities(question, normalized)
    classification = classify_market(normalized=normalized, entities=entities, outcome_names=outcomes)
    return CatalogMarketRecord(
        market_id=market_id,
        question=question,
        description="",
        status="active",
        normalized=normalized,
        entities=entities,
        classification=classification,
        outcome_names=outcomes,
    )


def test_exact_grouping_is_deterministic_and_high_confidence() -> None:
    proposals = group_markets(
        [
            _record(1, "Will Trump win the US presidential election in 2028?"),
            _record(2, "Will Harris win the US presidential election in 2028?"),
        ]
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.stage == "exact"
    assert proposal.market_ids == (1, 2)
    assert proposal.confidence == Decimal("1.00")
    assert proposal.review_required is False


def test_lexical_grouping_produces_componentized_reviewable_scores() -> None:
    proposals = group_markets(
        [
            _record(1, "Will a Democrat win the US governor race in 2026?"),
            _record(2, "Will the Democratic candidate win the U.S. governor election in 2026?"),
        ]
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.stage == "exact" or proposal.stage == "lexical"
    assert "country_alignment" in proposal.confidence_components
    assert proposal.confidence >= Decimal("0.72")


def test_grouping_avoids_false_positive_for_different_countries() -> None:
    proposals = group_markets(
        [
            _record(1, "Will the US presidential election in 2028 be won by a Democrat?"),
            _record(2, "Will the France presidential election in 2028 be won by the left?"),
        ]
    )

    assert proposals == []


def test_grouping_avoids_false_positive_for_different_offices() -> None:
    proposals = group_markets(
        [
            _record(1, "Will Republicans win the US Senate in 2026?"),
            _record(2, "Will Republicans win the US presidency in 2026?"),
        ]
    )

    assert proposals == []
