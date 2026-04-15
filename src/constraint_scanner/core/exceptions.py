from __future__ import annotations


class ConstraintScannerError(Exception):
    """Base exception for project-specific failures."""


class ConfigurationError(ConstraintScannerError):
    """Raised when configuration is invalid or incomplete."""


class SchemaValidationError(ConstraintScannerError):
    """Raised when a domain payload fails explicit validation."""


class RiskRejectedError(ConstraintScannerError):
    """Raised when a request is rejected by a risk gate."""
