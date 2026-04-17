"""Trading subsystem scaffold."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "OrderBuildResult",
    "OrderRouter",
    "OrderRoutingResult",
    "OrderTrackingResult",
    "PaperOrderTracker",
    "RuntimeControlState",
    "TrackedOrderRecord",
    "TraderService",
    "TraderServiceResult",
    "TradingModeSnapshot",
    "TradingModeState",
    "UnwindIntent",
    "UnwindPlanner",
    "build_order_requests",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "OrderBuildResult": ("constraint_scanner.trading.order_builder", "OrderBuildResult"),
    "build_order_requests": ("constraint_scanner.trading.order_builder", "build_order_requests"),
    "OrderRouter": ("constraint_scanner.trading.order_router", "OrderRouter"),
    "OrderRoutingResult": ("constraint_scanner.trading.order_router", "OrderRoutingResult"),
    "OrderTrackingResult": ("constraint_scanner.trading.order_tracker", "OrderTrackingResult"),
    "PaperOrderTracker": ("constraint_scanner.trading.order_tracker", "PaperOrderTracker"),
    "TrackedOrderRecord": ("constraint_scanner.trading.order_tracker", "TrackedOrderRecord"),
    "TraderService": ("constraint_scanner.trading.trader_service", "TraderService"),
    "TraderServiceResult": ("constraint_scanner.trading.trader_service", "TraderServiceResult"),
    "TradingModeSnapshot": ("constraint_scanner.trading.mode_state", "TradingModeSnapshot"),
    "TradingModeState": ("constraint_scanner.trading.mode_state", "TradingModeState"),
    "UnwindIntent": ("constraint_scanner.trading.unwind", "UnwindIntent"),
    "UnwindPlanner": ("constraint_scanner.trading.unwind", "UnwindPlanner"),
    "RuntimeControlState": ("constraint_scanner.control_runtime", "RuntimeControlState"),
}


def __getattr__(name: str) -> Any:
    """Lazily resolve trading exports to avoid package import cycles."""

    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
