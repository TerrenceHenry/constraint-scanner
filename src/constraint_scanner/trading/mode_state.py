from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from constraint_scanner.core.clock import utc_now
from constraint_scanner.core.enums import TradingMode


@dataclass(frozen=True, slots=True)
class TradingModeSnapshot:
    """Stable snapshot of the current operator-selected trading mode."""

    mode: TradingMode
    reason: str | None
    updated_at: str | None


class TradingModeState:
    """Thread-safe mutable runtime trading mode state for operator controls."""

    def __init__(self, *, mode: TradingMode = TradingMode.DISABLED, reason: str | None = None) -> None:
        self._lock = RLock()
        self._mode = mode
        self._reason = reason
        self._updated_at = utc_now().isoformat()

    def set_mode(self, mode: TradingMode, *, reason: str | None = None) -> TradingModeSnapshot:
        """Set the runtime trading mode and return the new snapshot."""

        with self._lock:
            self._mode = mode
            self._reason = reason
            self._updated_at = utc_now().isoformat()
            return self.snapshot()

    def snapshot(self) -> TradingModeSnapshot:
        """Return a stable snapshot of the current mode."""

        with self._lock:
            return TradingModeSnapshot(
                mode=self._mode,
                reason=self._reason,
                updated_at=self._updated_at,
            )
