from __future__ import annotations

from constraint_scanner.clients.models import MarketStreamEvent, PolymarketBook
from constraint_scanner.core.types import BookSnapshot
from constraint_scanner.db.models import Token
from constraint_scanner.db.repositories.markets import MarketsRepository

POSTGRES_INTEGER_MIN = -(2**31)
POSTGRES_INTEGER_MAX = (2**31) - 1


def _is_internal_token_id_candidate(value: int) -> bool:
    return POSTGRES_INTEGER_MIN <= value <= POSTGRES_INTEGER_MAX


def resolve_token_reference(repository: MarketsRepository, token_reference: str | int) -> Token | None:
    """Resolve a token from either an internal ID or an external asset ID."""

    if isinstance(token_reference, int) and _is_internal_token_id_candidate(token_reference):
        token = repository.get_token(token_reference)
        if token is not None:
            return token

    text_reference = str(token_reference)
    try:
        internal_candidate = int(text_reference, 0)
    except ValueError:
        internal_candidate = None

    if internal_candidate is not None and _is_internal_token_id_candidate(internal_candidate):
        token = repository.get_token(internal_candidate)
        if token is not None:
            return token

    token = repository.get_token_by_asset_id(text_reference)
    if token is not None:
        return token

    return repository.get_token_by_external_id(text_reference)


def resolve_book_to_internal_token(
    repository: MarketsRepository,
    book: PolymarketBook,
) -> PolymarketBook | None:
    """Return a book normalized to the canonical internal DB token ID."""

    token = resolve_token_reference(repository, book.snapshot.token_id)
    if token is None:
        return None

    return PolymarketBook(
        snapshot=BookSnapshot(
            token_id=token.id,
            market_id=token.market_id,
            observed_at=book.snapshot.observed_at,
            bids=book.snapshot.bids,
            asks=book.snapshot.asks,
            source=book.snapshot.source,
            sequence_number=book.snapshot.sequence_number,
        ),
        market=book.market,
        book_hash=book.book_hash,
        tick_size=book.tick_size,
        min_order_size=book.min_order_size,
        last_trade_price=book.last_trade_price,
        raw_payload=book.raw_payload,
    )


def resolve_event_to_internal_token(
    repository: MarketsRepository,
    event: MarketStreamEvent,
) -> tuple[MarketStreamEvent, int | None]:
    """Return an event whose book payload is keyed by the canonical internal token ID."""

    token = resolve_token_reference(repository, event.asset_id) if event.asset_id is not None else None
    resolved_token_id = token.id if token is not None else None

    if event.book is None:
        return event, resolved_token_id

    resolved_book = resolve_book_to_internal_token(repository, event.book)
    if resolved_book is None:
        unresolved_event = MarketStreamEvent(
            event_type=event.event_type,
            asset_id=event.asset_id,
            received_at=event.received_at,
            book=None,
            best_bid=event.best_bid,
            best_ask=event.best_ask,
            raw_payload=event.raw_payload,
        )
        return unresolved_event, resolved_token_id

    resolved_event = MarketStreamEvent(
        event_type=event.event_type,
        asset_id=str(resolved_book.snapshot.token_id),
        received_at=event.received_at,
        book=resolved_book,
        best_bid=event.best_bid,
        best_ask=event.best_ask,
        raw_payload=event.raw_payload,
    )
    return resolved_event, resolved_book.snapshot.token_id
