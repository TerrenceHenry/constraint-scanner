from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.types import BookLevel, BookSnapshot, OpportunityLeg, OrderSide


@dataclass(frozen=True, slots=True)
class FillSlice:
    """Single consumed depth slice for an executable fill."""

    price: Decimal
    available_quantity: Decimal
    filled_quantity: Decimal


@dataclass(frozen=True, slots=True)
class FillComputation:
    """Auditable weighted fill result."""

    side: OrderSide
    desired_quantity: Decimal
    filled_quantity: Decimal
    weighted_average_price: Decimal | None
    total_notional: Decimal
    consumed_depth: tuple[FillSlice, ...] = ()

    @property
    def unfilled_quantity(self) -> Decimal:
        """Return desired quantity not filled by current book depth."""

        return self.desired_quantity - self.filled_quantity

    @property
    def fully_filled(self) -> bool:
        """Return whether the desired quantity was fully filled."""

        return self.unfilled_quantity == DECIMAL_ZERO


@dataclass(frozen=True, slots=True)
class BasketExecutableSize:
    """Maximum executable basket size limited by the shallowest leg."""

    max_basket_quantity: Decimal
    limiting_token_id: int | None
    per_leg_limits: dict[int, Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BasketCostResult:
    """Net executable basket cost with per-leg audit details."""

    basket_quantity: Decimal
    net_cost: Decimal
    gross_buy_cost: Decimal
    gross_sell_proceeds: Decimal
    fills_by_token: dict[int, FillComputation] = field(default_factory=dict)


def compute_weighted_fill_price(
    levels: tuple[BookLevel, ...] | list[BookLevel],
    desired_quantity: Decimal,
    side: OrderSide,
) -> FillComputation:
    """Compute a weighted fill from executable depth.

    `levels` must be the executable side of the book:
    - buys consume asks from best ask upward
    - sells consume bids from best bid downward
    """

    if desired_quantity <= DECIMAL_ZERO:
        return FillComputation(
            side=side,
            desired_quantity=desired_quantity,
            filled_quantity=DECIMAL_ZERO,
            weighted_average_price=None,
            total_notional=DECIMAL_ZERO,
            consumed_depth=(),
        )

    sorted_levels = _sorted_levels(tuple(levels), side)
    remaining_quantity = desired_quantity
    total_notional = DECIMAL_ZERO
    filled_quantity = DECIMAL_ZERO
    consumed_depth: list[FillSlice] = []

    for level in sorted_levels:
        if remaining_quantity <= DECIMAL_ZERO:
            break
        if level.size <= DECIMAL_ZERO:
            continue

        fill_quantity = min(level.size, remaining_quantity)
        consumed_depth.append(
            FillSlice(
                price=level.price,
                available_quantity=level.size,
                filled_quantity=fill_quantity,
            )
        )
        total_notional += level.price * fill_quantity
        filled_quantity += fill_quantity
        remaining_quantity -= fill_quantity

    weighted_average_price = None
    if filled_quantity > DECIMAL_ZERO:
        weighted_average_price = total_notional / filled_quantity

    return FillComputation(
        side=side,
        desired_quantity=desired_quantity,
        filled_quantity=filled_quantity,
        weighted_average_price=weighted_average_price,
        total_notional=total_notional,
        consumed_depth=tuple(consumed_depth),
    )


def compute_max_executable_size_for_basket(
    books: dict[int, BookSnapshot],
    legs: tuple[OpportunityLeg, ...] | list[OpportunityLeg],
) -> BasketExecutableSize:
    """Compute the max executable basket quantity from explicit book depth."""

    per_leg_limits: dict[int, Decimal] = {}
    limiting_token_id: int | None = None
    max_basket_quantity: Decimal | None = None

    for leg in legs:
        if leg.quantity <= DECIMAL_ZERO:
            per_leg_limits[leg.token_id] = DECIMAL_ZERO
            max_basket_quantity = DECIMAL_ZERO
            limiting_token_id = leg.token_id
            break

        book = books.get(leg.token_id)
        if book is None:
            per_leg_limits[leg.token_id] = DECIMAL_ZERO
            max_basket_quantity = DECIMAL_ZERO
            limiting_token_id = leg.token_id
            break

        executable_levels = _levels_for_leg(book, leg.side)
        available_quantity = sum((level.size for level in executable_levels if level.size > DECIMAL_ZERO), start=DECIMAL_ZERO)
        basket_limit = available_quantity / leg.quantity if available_quantity > DECIMAL_ZERO else DECIMAL_ZERO
        per_leg_limits[leg.token_id] = basket_limit

        if max_basket_quantity is None or basket_limit < max_basket_quantity:
            max_basket_quantity = basket_limit
            limiting_token_id = leg.token_id

    return BasketExecutableSize(
        max_basket_quantity=max_basket_quantity if max_basket_quantity is not None else DECIMAL_ZERO,
        limiting_token_id=limiting_token_id,
        per_leg_limits=per_leg_limits,
    )


def compute_basket_cost(
    books: dict[int, BookSnapshot],
    legs: tuple[OpportunityLeg, ...] | list[OpportunityLeg],
    basket_quantity: Decimal,
) -> BasketCostResult:
    """Compute deterministic basket cost using executable depth only."""

    fills_by_token: dict[int, FillComputation] = {}
    gross_buy_cost = DECIMAL_ZERO
    gross_sell_proceeds = DECIMAL_ZERO

    for leg in legs:
        requested_quantity = leg.quantity * basket_quantity
        book = books.get(leg.token_id)
        if book is None:
            fill = FillComputation(
                side=leg.side,
                desired_quantity=requested_quantity,
                filled_quantity=DECIMAL_ZERO,
                weighted_average_price=None,
                total_notional=DECIMAL_ZERO,
                consumed_depth=(),
            )
        else:
            fill = compute_weighted_fill_price(_levels_for_leg(book, leg.side), requested_quantity, leg.side)
        fills_by_token[leg.token_id] = fill

        if leg.side == "buy":
            gross_buy_cost += fill.total_notional
        else:
            gross_sell_proceeds += fill.total_notional

    return BasketCostResult(
        basket_quantity=basket_quantity,
        net_cost=gross_buy_cost - gross_sell_proceeds,
        gross_buy_cost=gross_buy_cost,
        gross_sell_proceeds=gross_sell_proceeds,
        fills_by_token=fills_by_token,
    )


def compute_net_edge(
    *,
    payout_per_basket: Decimal,
    basket_cost: BasketCostResult,
) -> Decimal:
    """Compute net edge from guaranteed payout minus executable basket cost."""

    return payout_per_basket * basket_cost.basket_quantity - basket_cost.net_cost


def _sorted_levels(levels: tuple[BookLevel, ...], side: OrderSide) -> tuple[BookLevel, ...]:
    if side == "buy":
        return tuple(sorted(levels, key=lambda level: (level.price, -level.size)))
    return tuple(sorted(levels, key=lambda level: (-level.price, -level.size)))


def _levels_for_leg(book: BookSnapshot, side: OrderSide) -> tuple[BookLevel, ...]:
    return book.asks if side == "buy" else book.bids
