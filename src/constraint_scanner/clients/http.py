from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from constraint_scanner.clients.errors import HttpClientError, RetryableClientError
from constraint_scanner.clients.retry import RetryPolicy, retry_async


def _classify_http_error(response: httpx.Response) -> Exception:
    message = f"HTTP {response.status_code} from {response.request.method} {response.request.url}"
    if response.status_code in {408, 425, 429} or response.status_code >= 500:
        return RetryableClientError(message)
    return HttpClientError(message, status_code=response.status_code)


class JsonHttpClient:
    """Small async HTTP helper with JSON decoding and retry support."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        retry_policy: RetryPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, transport=transport)
        self._retry_policy = retry_policy or RetryPolicy()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._request_json("GET", path, params=params)

    async def post_json(
        self,
        path: str,
        *,
        json_body: Any,
    ) -> Any:
        return await self._request_json("POST", path, json=json_body)

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        async def _operation() -> Any:
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.TimeoutException as exc:
                raise RetryableClientError(f"Timeout during {method} {path}") from exc
            except httpx.TransportError as exc:
                raise RetryableClientError(f"Transport failure during {method} {path}") from exc

            if response.status_code >= 400:
                raise _classify_http_error(response)

            try:
                return response.json()
            except ValueError as exc:
                raise HttpClientError(f"Invalid JSON from {method} {path}") from exc

        return await retry_async(_operation, policy=self._retry_policy)
