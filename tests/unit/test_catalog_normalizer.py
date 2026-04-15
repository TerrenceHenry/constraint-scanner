from __future__ import annotations

from constraint_scanner.catalog.normalizer import normalize_market_text


def test_normalizer_handles_case_whitespace_and_punctuation_conservatively() -> None:
    normalized = normalize_market_text("  Will   the U.S. President (2028) win?  ", "Nov. 2028 election")

    assert normalized.title_normalized == "will the us president 2028 win"
    assert normalized.description_normalized == "2028-11 election"
    assert normalized.lexical_tokens == ("will", "us", "president", "2028", "win")
    assert normalized.years == ("2028",)


def test_normalizer_preserves_distinguishing_date_tokens() -> None:
    normalized = normalize_market_text("Will France elect a president in March 2027?")

    assert "2027" in normalized.years
    assert "2027-03" in normalized.date_tokens
