from __future__ import annotations

from decimal import Decimal

from constraint_scanner.clients.http import JsonHttpClient
from constraint_scanner.clients.models import PolymarketBook
from constraint_scanner.clients.normalizers import normalize_clob_book
from constraint_scanner.clients.retry import RetryPolicy
from constraint_scanner.core.constants import POLYMARKET_CLOB_BASE_URL


class ClobClient:
    """Read-only public client for Polymarket CLOB endpoints."""

    def __init__(
        self,
        *,
        base_url: str = POLYMARKET_CLOB_BASE_URL,
        retry_policy: RetryPolicy | None = None,
        transport=None,
    ) -> None:
        self._http = JsonHttpClient(
            base_url=base_url,
            retry_policy=retry_policy,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_book(self, token_id: str | int) -> PolymarketBook:
        payload = await self._http.get_json("/book", params={"token_id": str(token_id)})
        return normalize_clob_book(payload)

    async def get_books(self, token_ids: list[str | int]) -> list[PolymarketBook]:
        payload = await self._http.post_json(
            "/books",
            json_body=[{"token_id": str(token_id)} for token_id in token_ids],
        )
        items = payload.get("books", payload) if isinstance(payload, dict) else payload
        return [normalize_clob_book(item) for item in items]

    async def get_spread(self, token_id: str | int) -> Decimal | None:
        payload = await self._http.get_json("/spread", params={"token_id": str(token_id)})
        value = payload.get("spread")
        return Decimal(str(value)) if value not in (None, "") else None

    async def get_midpoint(self, token_id: str | int) -> Decimal | None:
        payload = await self._http.get_json("/midpoint", params={"token_id": str(token_id)})
        value = payload.get("midpoint", payload.get("mid", payload.get("mid_price")))
        return Decimal(str(value)) if value not in (None, "") else None
