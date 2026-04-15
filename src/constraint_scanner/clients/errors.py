from __future__ import annotations


class ClientError(Exception):
    """Base error for integration client failures."""


class RetryableClientError(ClientError):
    """Raised when a request may be retried safely."""


class HttpClientError(ClientError):
    """Raised for non-retryable HTTP failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WebSocketClientError(ClientError):
    """Raised for websocket protocol or connection failures."""
