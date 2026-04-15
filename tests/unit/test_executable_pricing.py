from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from constraint_scanner.core.types import BookLevel, BookSnapshot, OpportunityLeg
from constraint_scanner.simulation.executable_pricing import (
    compute_basket_cost,
    compute_max_executable_size_for_basket,
    compute_net_edge,
    compute_weighted_fill_price,
)


def _book(
    token_id: int,
    *,
    bids: tuple[tuple[str, str], ...] = (),
    asks: tuple[tuple[str, str], ...] = (),
) -> BookSnapshot:
    return BookSnapshot(
        token_id=token_id,
        market_id=None,
        observed_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        bids=tuple(BookLevel(price=Decimal(price), size=Decimal(size)) for price, size in bids),
        asks=tuple(BookLevel(price=Decimal(price), size=Decimal(size)) for price, size in asks),
        source="test",
    )


def test_compute_weighted_fill_price_consumes_partial_depth_for_buy() -> None:
    fill = compute_weighted_fill_price(
        [
            BookLevel(price=Decimal("0.46"), size=Decimal("10")),
            BookLevel(price=Decimal("0.47"), size=Decimal("5")),
            BookLevel(price=Decimal("0.48"), size=Decimal("20")),
        ],
        Decimal("12"),
        "buy",
    )

    assert fill.filled_quantity == Decimal("12")
    assert fill.total_notional == Decimal("5.54")
    assert fill.weighted_average_price == Decimal("5.54") / Decimal("12")
    assert [slice_.filled_quantity for slice_ in fill.consumed_depth] == [Decimal("10"), Decimal("2")]


def test_compute_weighted_fill_price_sorts_sell_levels_best_bid_downward() -> None:
    fill = compute_weighted_fill_price(
        [
            BookLevel(price=Decimal("0.44"), size=Decimal("4")),
            BookLevel(price=Decimal("0.46"), size=Decimal("3")),
            BookLevel(price=Decimal("0.45"), size=Decimal("5")),
        ],
        Decimal("6"),
        "sell",
    )

    assert fill.filled_quantity == Decimal("6")
    assert [slice_.price for slice_ in fill.consumed_depth] == [Decimal("0.46"), Decimal("0.45")]
    assert fill.total_notional == Decimal("2.73")


def test_compute_weighted_fill_price_handles_zero_liquidity() -> None:
    fill = compute_weighted_fill_price((), Decimal("10"), "buy")

    assert fill.filled_quantity == Decimal("0")
    assert fill.weighted_average_price is None
    assert fill.total_notional == Decimal("0")
    assert fill.fully_filled is False


def test_compute_max_executable_size_for_basket_is_limited_by_shallowest_leg() -> None:
    books = {
        1: _book(1, asks=(("0.45", "30"), ("0.46", "20"))),
        2: _book(2, asks=(("0.20", "10"), ("0.21", "10"))),
    }
    legs = (
        OpportunityLeg(market_id=1, token_id=1, side="buy", price=Decimal("0"), quantity=Decimal("2")),
        OpportunityLeg(market_id=2, token_id=2, side="buy", price=Decimal("0"), quantity=Decimal("3")),
    )

    result = compute_max_executable_size_for_basket(books, legs)

    assert result.per_leg_limits[1] == Decimal("25")
    assert result.per_leg_limits[2] == Decimal("6.666666666666666666666666667")
    assert result.max_basket_quantity == result.per_leg_limits[2]
    assert result.limiting_token_id == 2


def test_compute_basket_cost_and_net_edge_handle_asymmetric_buy_sell_books() -> None:
    books = {
        1: _book(1, asks=(("0.45", "20"), ("0.46", "10"))),
        2: _book(2, bids=(("0.60", "5"), ("0.59", "10"))),
    }
    legs = (
        OpportunityLeg(market_id=1, token_id=1, side="buy", price=Decimal("0"), quantity=Decimal("10")),
        OpportunityLeg(market_id=2, token_id=2, side="sell", price=Decimal("0"), quantity=Decimal("4")),
    )

    basket_cost = compute_basket_cost(books, legs, Decimal("1"))
    net_edge = compute_net_edge(payout_per_basket=Decimal("1"), basket_cost=basket_cost)

    assert basket_cost.gross_buy_cost == Decimal("4.50")
    assert basket_cost.gross_sell_proceeds == Decimal("2.40")
    assert basket_cost.net_cost == Decimal("2.10")
    assert basket_cost.fills_by_token[1].fully_filled is True
    assert basket_cost.fills_by_token[2].fully_filled is True
    assert net_edge == Decimal("-1.10")


def test_compute_basket_cost_records_partial_fill_when_depth_is_insufficient() -> None:
    books = {1: _book(1, asks=(("0.50", "3"),))}
    legs = (OpportunityLeg(market_id=1, token_id=1, side="buy", price=Decimal("0"), quantity=Decimal("5")),)

    basket_cost = compute_basket_cost(books, legs, Decimal("1"))

    assert basket_cost.fills_by_token[1].filled_quantity == Decimal("3")
    assert basket_cost.fills_by_token[1].unfilled_quantity == Decimal("2")
    assert basket_cost.net_cost == Decimal("1.50")
