from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from constraint_scanner.core.clock import utc_now


@dataclass(frozen=True, slots=True)
class KillSwitchSnapshot:
    """Stable snapshot of the central kill switch state."""

    active: bool
    reason: str | None
    updated_at: str | None


class KillSwitch:
    """Simple thread-safe kill switch for local service usage."""

    def __init__(self, *, active: bool = False, reason: str | None = None) -> None:
        self._lock = RLock()
        self._active = active
        self._reason = reason
        self._updated_at = utc_now().isoformat()

    def activate(self, *, reason: str = "manual_kill_switch") -> KillSwitchSnapshot:
        """Activate the kill switch immediately."""

        with self._lock:
            self._active = True
            self._reason = reason
            self._updated_at = utc_now().isoformat()
            return self.snapshot()

    def clear(self) -> KillSwitchSnapshot:
        """Clear the kill switch."""

        with self._lock:
            self._active = False
            self._reason = None
            self._updated_at = utc_now().isoformat()
            return self.snapshot()

    def snapshot(self) -> KillSwitchSnapshot:
        """Return a stable snapshot of the current state."""

        with self._lock:
            return KillSwitchSnapshot(
                active=self._active,
                reason=self._reason,
                updated_at=self._updated_at,
            )
