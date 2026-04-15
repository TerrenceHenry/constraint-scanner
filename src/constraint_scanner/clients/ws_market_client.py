from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from constraint_scanner.clients.errors import RetryableClientError, WebSocketClientError
from constraint_scanner.clients.models import MarketStreamEvent
from constraint_scanner.clients.normalizers import normalize_market_stream_event
from constraint_scanner.clients.retry import RetryPolicy, retry_async
from constraint_scanner.core.constants import POLYMARKET_MARKET_WS_URL


WebSocketConnectFn = Callable[..., Awaitable[Any]]


class WsMarketClient:
    """Public read-only websocket client for Polymarket market data."""

    def __init__(
        self,
        *,
        ws_url: str = POLYMARKET_MARKET_WS_URL,
        retry_policy: RetryPolicy | None = None,
        connect_fn: WebSocketConnectFn | None = None,
        message_timeout_seconds: float = 20.0,
        ping_timeout_seconds: float = 5.0,
    ) -> None:
        self._ws_url = ws_url
        self._retry_policy = retry_policy or RetryPolicy()
        self._connect_fn = connect_fn or websockets.connect
        self._message_timeout_seconds = message_timeout_seconds
        self._ping_timeout_seconds = ping_timeout_seconds
        self._websocket: Any | None = None
        self._asset_ids: tuple[str, ...] = ()
        self._active_subscription: tuple[str, ...] = ()
        self._closed = False

    async def connect(self) -> None:
        """Open the websocket connection with retry handling."""

        async def _operation() -> Any:
            try:
                return await self._connect_fn(
                    self._ws_url,
                    ping_interval=None,
                    close_timeout=self._ping_timeout_seconds,
                )
            except (OSError, WebSocketException) as exc:
                raise RetryableClientError("websocket connect failed") from exc

        self._websocket = await retry_async(_operation, policy=self._retry_policy)

    async def subscribe(self, asset_ids: Sequence[str | int]) -> None:
        """Subscribe the current connection to asset IDs."""

        if self._websocket is None:
            await self.connect()

        self._asset_ids = tuple(sorted({str(asset_id) for asset_id in asset_ids}))
        if self._active_subscription == self._asset_ids:
            return

        payload = {
            "assets_ids": list(self._asset_ids),
            "type": "market",
            "custom_feature_enabled": True,
        }
        await self._websocket.send(json.dumps(payload))
        self._active_subscription = self._asset_ids

    async def listen(self) -> AsyncIterator[MarketStreamEvent]:
        """Yield normalized events from the websocket, reconnecting when needed."""

        while not self._closed:
            await self._ensure_connected()
            try:
                raw_message = await asyncio.wait_for(
                    self._websocket.recv(),
                    timeout=self._message_timeout_seconds,
                )
            except asyncio.TimeoutError:
                await self._heartbeat()
                continue
            except ConnectionClosed:
                await self._reset_connection()
                continue

            for payload in self._decode_payload(raw_message):
                yield normalize_market_stream_event(payload)

    async def aclose(self) -> None:
        """Close the websocket and stop reconnect attempts."""

        self._closed = True
        if self._websocket is not None:
            await self._websocket.close()
            self._websocket = None

    async def __aenter__(self) -> "WsMarketClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def _ensure_connected(self) -> None:
        if self._websocket is None:
            await self.connect()
            if self._asset_ids:
                await self.subscribe(self._asset_ids)

    async def _heartbeat(self) -> None:
        if self._websocket is None:
            return

        try:
            pong_waiter = await self._websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=self._ping_timeout_seconds)
        except (asyncio.TimeoutError, ConnectionClosed, WebSocketException) as exc:
            await self._reset_connection()
            if self._closed:
                return
            return

    async def _reset_connection(self) -> None:
        if self._websocket is not None:
            try:
                await self._websocket.close()
            finally:
                self._websocket = None
                self._active_subscription = ()

    def _decode_payload(self, raw_message: Any) -> list[dict[str, Any]]:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        if isinstance(raw_message, str):
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                raise WebSocketClientError("invalid websocket JSON payload") from exc
        elif isinstance(raw_message, dict):
            payload = raw_message
        else:
            raise WebSocketClientError(f"unsupported websocket payload type: {type(raw_message)!r}")

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        raise WebSocketClientError("websocket payload must decode to dict or list")
