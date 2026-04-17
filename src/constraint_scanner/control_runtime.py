from __future__ import annotations

from dataclasses import dataclass

from constraint_scanner.config.models import Settings
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.trading.mode_state import TradingModeState


@dataclass(slots=True)
class RuntimeControlState:
    """Authoritative in-memory runtime control state for operator actions."""

    kill_switch: KillSwitch
    trading_mode_state: TradingModeState

    @classmethod
    def from_settings(cls, settings: Settings) -> RuntimeControlState:
        """Build the default runtime control state from static settings."""

        return cls(
            kill_switch=KillSwitch(
                active=settings.risk.kill_switch,
                reason="config_default" if settings.risk.kill_switch else None,
            ),
            trading_mode_state=TradingModeState(
                mode=settings.trading.resolved_mode(),
                reason="config_default",
            ),
        )
