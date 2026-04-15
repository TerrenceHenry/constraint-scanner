from __future__ import annotations


class ConstraintScannerError(Exception):
    """Base exception for project-specific failures."""


class ConfigurationError(ConstraintScannerError):
    """Raised when configuration is invalid or incomplete."""


class SchemaValidationError(ConstraintScannerError):
    """Raised when a domain payload fails explicit validation."""


class RiskRejectedError(ConstraintScannerError):
    """Raised when a request is rejected by a risk gate."""


class TradingError(ConstraintScannerError):
    """Base exception for trading scaffolding failures."""


class TradingValidationError(TradingError):
    """Raised when a trade intent cannot be built from persisted data."""


class TradingModeDisabledError(TradingError):
    """Raised when trading is disabled and routing was attempted."""


class TradingModeNotSupportedError(TradingError):
    """Raised when a trading mode exists but is not implemented yet."""
