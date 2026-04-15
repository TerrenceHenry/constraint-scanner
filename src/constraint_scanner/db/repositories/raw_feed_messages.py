from __future__ import annotations

from sqlalchemy.orm import Session

from constraint_scanner.db.models import RawFeedMessage


class RawFeedMessagesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_message(self, **values: object) -> RawFeedMessage:
        message = RawFeedMessage(**values)
        self.session.add(message)
        self.session.flush()
        return message
