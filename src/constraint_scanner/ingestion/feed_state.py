from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from constraint_scanner.core.clock import ensure_utc, utc_now


@dataclass(frozen=True, slots=True)
class FeedStatus:
    """Snapshot of feed freshness."""

    healthy: bool
    stale_token_ids: tuple[int, ...]
    latest_update_at: datetime | None


class FeedState:
    """Track latest feed activity and report stale/healthy status."""

    def __init__(self, *, stale_after_seconds: int = 30) -> None:
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._last_seen_by_token: dict[int, datetime] = {}

    def mark_seen(self, token_id: int, observed_at: datetime) -> None:
        """Record the latest observed timestamp for a token."""

        normalized = ensure_utc(observed_at)
        current = self._last_seen_by_token.get(token_id)
        if current is None or normalized >= current:
            self._last_seen_by_token[token_id] = normalized

    def latest_update_at(self) -> datetime | None:
        """Return the newest observed timestamp across tracked tokens."""

        if not self._last_seen_by_token:
            return None
        return max(self._last_seen_by_token.values())

    def stale_token_ids(self, *, now: datetime | None = None) -> tuple[int, ...]:
        """Return tracked tokens that are older than the stale threshold."""

        if not self._last_seen_by_token:
            return ()
        active_now = ensure_utc(now) if now is not None else utc_now()
        threshold = active_now - self._stale_after
        return tuple(sorted(token_id for token_id, seen_at in self._last_seen_by_token.items() if seen_at < threshold))

    def status(self, *, now: datetime | None = None) -> FeedStatus:
        """Return current health status."""

        stale = self.stale_token_ids(now=now)
        return FeedStatus(
            healthy=not stale,
            stale_token_ids=stale,
            latest_update_at=self.latest_update_at(),
        )
