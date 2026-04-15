from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from constraint_scanner.clients.errors import RetryableClientError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Simple async retry policy with bounded exponential backoff."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    retry_exceptions: tuple[type[BaseException], ...] = (RetryableClientError,),
) -> T:
    """Retry an async operation when it raises a retryable exception."""

    active_policy = policy or RetryPolicy()
    attempt = 0
    delay = active_policy.initial_delay_seconds

    while True:
        attempt += 1
        try:
            return await operation()
        except retry_exceptions:
            if attempt >= active_policy.max_attempts:
                raise
            await asyncio.sleep(delay)
            delay = min(delay * 2, active_policy.max_delay_seconds)
