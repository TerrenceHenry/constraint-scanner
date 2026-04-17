from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from constraint_scanner.runtime import build_service_runtime


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap markets, snapshot books, and optionally consume live feed events.")
    parser.add_argument("--bootstrap-limit", type=int, default=None, help="Maximum number of markets to bootstrap.")
    parser.add_argument("--event-limit", type=int, default=None, help="Stop after consuming this many websocket events.")
    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Bootstrap and snapshot books but do not enter the websocket consume loop.",
    )
    args = parser.parse_args()

    runtime = build_service_runtime()
    try:
        bootstrap_limit = args.bootstrap_limit or runtime.settings.ingestion.bootstrap_limit
        bootstrap_result = await runtime.market_feed_service.bootstrap(limit=bootstrap_limit)
        snapshot_result = await runtime.market_feed_service.snapshot_books(list(bootstrap_result.tradable_token_ids))
        payload: dict[str, object] = {
            "bootstrap": asdict(bootstrap_result),
            "snapshot": {
                "snapshot_count": snapshot_result.snapshot_count,
                "token_ids": list(snapshot_result.token_ids),
            },
        }
        if not args.snapshot_only and bootstrap_result.tradable_token_ids:
            consume_result = await runtime.market_feed_service.consume_live(
                asset_ids=list(bootstrap_result.tradable_token_ids),
                event_limit=args.event_limit,
            )
            payload["consume_live"] = asdict(consume_result)
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    finally:
        await runtime.aclose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
