from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from websockets.exceptions import ConnectionClosedOK

from constraint_scanner.clients.clob_client import ClobClient
from constraint_scanner.clients.gamma_client import GammaClient
from constraint_scanner.clients.ws_market_client import WsMarketClient


def test_gamma_client_normalizes_market_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/markets"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "123",
                    "slug": "demo-market",
                    "question": "  Will this normalize? ",
                    "description": "Demo",
                    "active": True,
                    "closed": False,
                    "outcomes": "[\"Yes\", \"No\"]",
                    "outcomePrices": "[\"0.25\", \"0.75\"]",
                    "clobTokenIds": "[\"111\", \"222\"]",
                    "tags": [{"label": "Politics"}],
                }
            ],
        )

    async def run_test() -> None:
        client = GammaClient(transport=httpx.MockTransport(handler))
        try:
            markets = await client.list_markets()
        finally:
            await client.aclose()

        assert len(markets) == 1
        assert markets[0].question == "Will this normalize?"
        assert markets[0].outcome_prices == (Decimal("0.25"), Decimal("0.75"))
        assert markets[0].token_ids == ("111", "222")
        assert markets[0].tags == ("Politics",)

    asyncio.run(run_test())


def test_clob_client_retries_and_normalizes_book_payload() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if request.url.path == "/book" and calls["count"] == 1:
            return httpx.Response(503, json={"error": "temporary"})
        if request.url.path == "/book":
            return httpx.Response(
                200,
                json={
                    "asset_id": "65818619657568813474341868652308942079804919287380422192892211131408793125422",
                    "bids": [{"price": "0.44", "size": "100"}],
                    "asks": [{"price": "0.46", "size": "120"}],
                    "hash": "0xbook",
                    "tick_size": "0.01",
                    "min_order_size": "5",
                    "timestamp": "2026-04-14T10:00:00Z",
                },
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    async def run_test() -> None:
        client = ClobClient(transport=httpx.MockTransport(handler))
        try:
            book = await client.get_book("65818619657568813474341868652308942079804919287380422192892211131408793125422")
        finally:
            await client.aclose()

        assert calls["count"] == 2
        assert book.snapshot.bids[0].price == Decimal("0.44")
        assert book.snapshot.asks[0].price == Decimal("0.46")
        assert book.tick_size == Decimal("0.01")
        assert book.snapshot.observed_at == datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc)

    asyncio.run(run_test())


def test_clob_client_midpoint_and_spread_are_diagnostic_decimals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/spread":
            return httpx.Response(200, json={"spread": "0.02"})
        if request.url.path == "/midpoint":
            return httpx.Response(200, json={"mid": "0.45"})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    async def run_test() -> None:
        client = ClobClient(transport=httpx.MockTransport(handler))
        try:
            spread = await client.get_spread("111")
            midpoint = await client.get_midpoint("111")
        finally:
            await client.aclose()

        assert spread == Decimal("0.02")
        assert midpoint == Decimal("0.45")

    asyncio.run(run_test())


def test_clob_client_get_books_normalizes_batch_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/books"
        return httpx.Response(
            200,
            json={
                "books": [
                    {
                        "asset_id": "111",
                        "bids": [{"price": "0.10", "size": "10"}],
                        "asks": [{"price": "0.12", "size": "8"}],
                    },
                    {
                        "asset_id": "222",
                        "bids": [{"price": "0.20", "size": "12"}],
                        "asks": [{"price": "0.25", "size": "7"}],
                    },
                ]
            },
        )

    async def run_test() -> None:
        client = ClobClient(transport=httpx.MockTransport(handler))
        try:
            books = await client.get_books(["111", "222"])
        finally:
            await client.aclose()

        assert [book.snapshot.token_id for book in books] == [111, 222]
        assert books[1].snapshot.asks[0].price == Decimal("0.25")

    asyncio.run(run_test())


class FakeWebSocket:
    def __init__(self, messages: list[object]) -> None:
        self._messages = list(messages)
        self.sent_messages: list[dict[str, object]] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent_messages.append(json.loads(message))

    async def recv(self) -> object:
        next_message = self._messages.pop(0)
        if isinstance(next_message, BaseException):
            raise next_message
        return next_message

    async def ping(self):
        future = asyncio.get_running_loop().create_future()
        future.set_result(None)
        return future

    async def close(self) -> None:
        self.closed = True


def test_ws_market_client_subscribes_reconnects_and_yields_parsed_events() -> None:
    first_socket = FakeWebSocket([ConnectionClosedOK(None, None)])
    second_socket = FakeWebSocket(
        [
            json.dumps(
                {
                    "event_type": "book",
                    "asset_id": "111",
                    "bids": [{"price": "0.40", "size": "50"}],
                    "asks": [{"price": "0.42", "size": "60"}],
                    "timestamp": "2026-04-14T10:01:00Z",
                }
            )
        ]
    )
    sockets = [first_socket, second_socket]

    async def fake_connect(*args, **kwargs):
        return sockets.pop(0)

    async def run_test() -> None:
        client = WsMarketClient(connect_fn=fake_connect)
        await client.subscribe(["111"])
        listener = client.listen()
        try:
            event = await anext(listener)
        finally:
            await listener.aclose()
            await client.aclose()

        assert first_socket.sent_messages[0]["assets_ids"] == ["111"]
        assert second_socket.sent_messages[0]["assets_ids"] == ["111"]
        assert event.event_type == "book"
        assert event.asset_id == "111"
        assert event.book is not None
        assert event.book.snapshot.asks[0].price == Decimal("0.42")

    asyncio.run(run_test())


def test_ws_market_client_deduplicates_identical_subscriptions() -> None:
    socket = FakeWebSocket([])

    async def fake_connect(*args, **kwargs):
        return socket

    async def run_test() -> None:
        client = WsMarketClient(connect_fn=fake_connect)
        try:
            await client.subscribe(["111", "222", "111"])
            await client.subscribe(["222", "111"])
        finally:
            await client.aclose()

        assert len(socket.sent_messages) == 1
        assert socket.sent_messages[0]["assets_ids"] == ["111", "222"]

    asyncio.run(run_test())
