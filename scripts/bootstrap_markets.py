from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from constraint_scanner.runtime import build_service_runtime


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap active Polymarket markets into the local database.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of active markets to fetch.")
    parser.add_argument(
        "--snapshot-books",
        action="store_true",
        help="Also fetch and persist initial orderbook snapshots for tradable tokens.",
    )
    args = parser.parse_args()

    runtime = build_service_runtime()
    try:
        limit = args.limit or runtime.settings.ingestion.bootstrap_limit
        bootstrap_result = await runtime.market_feed_service.bootstrap(limit=limit)
        payload: dict[str, object] = {"bootstrap": asdict(bootstrap_result)}
        if args.snapshot_books and bootstrap_result.tradable_token_ids:
            snapshot_result = await runtime.market_feed_service.snapshot_books(list(bootstrap_result.tradable_token_ids))
            payload["snapshot"] = {
                "snapshot_count": snapshot_result.snapshot_count,
                "token_ids": list(snapshot_result.token_ids),
            }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        await runtime.aclose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
