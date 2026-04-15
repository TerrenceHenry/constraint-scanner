from __future__ import annotations

from constraint_scanner.clients.http import JsonHttpClient
from constraint_scanner.clients.models import PolymarketMarket
from constraint_scanner.clients.normalizers import normalize_gamma_market
from constraint_scanner.clients.retry import RetryPolicy
from constraint_scanner.core.constants import POLYMARKET_GAMMA_BASE_URL


class GammaClient:
    """Read-only Gamma API client for public market metadata."""

    def __init__(
        self,
        *,
        base_url: str = POLYMARKET_GAMMA_BASE_URL,
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

    async def list_markets(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PolymarketMarket]:
        payload = await self._http.get_json(
            "/markets",
            params={
                "active": str(active).lower(),
                "closed": str(closed).lower(),
                "limit": limit,
                "offset": offset,
            },
        )
        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        return [normalize_gamma_market(item) for item in items]

    async def get_market(self, market_id: str | int) -> PolymarketMarket:
        payload = await self._http.get_json(f"/markets/{market_id}")
        return normalize_gamma_market(payload)
