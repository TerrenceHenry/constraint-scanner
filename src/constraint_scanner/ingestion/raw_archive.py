from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import sessionmaker

from constraint_scanner.db.repositories.raw_feed_messages import RawFeedMessagesRepository


class RawArchive:
    """Archive raw incoming feed messages for replay and debugging."""

    def __init__(self, session_factory: sessionmaker, *, enabled: bool = True) -> None:
        self._session_factory = session_factory
        self._enabled = enabled

    def archive(
        self,
        *,
        source: str,
        channel: str,
        message_type: str | None,
        received_at: datetime,
        payload: dict[str, Any],
        token_id: int | None = None,
        market_id: int | None = None,
        sequence_number: int | None = None,
    ) -> None:
        """Persist a raw feed message when archiving is enabled."""

        if not self._enabled:
            return

        with self._session_factory() as session:
            repository = RawFeedMessagesRepository(session)
            repository.create_message(
                source=source,
                channel=channel,
                message_type=message_type,
                received_at=received_at,
                payload=payload,
                token_id=token_id,
                market_id=market_id,
                sequence_number=sequence_number,
            )
            session.commit()
