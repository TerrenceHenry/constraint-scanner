from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.runtime import build_service_runtime


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return ensure_utc(datetime.fromisoformat(text))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one simulation pass on open opportunities.")
    parser.add_argument("--opportunity-id", dest="opportunity_ids", action="append", type=int, help="Restrict to specific opportunity IDs.")
    parser.add_argument("--simulated-at", type=str, default=None, help="Override the simulator timestamp in ISO-8601 format.")
    args = parser.parse_args()

    runtime = build_service_runtime()
    try:
        backfill = runtime.backfill_latest_books_from_db()
        result = runtime.simulator_service.run(
            simulated_at=_parse_datetime(args.simulated_at),
            opportunity_ids=tuple(args.opportunity_ids) if args.opportunity_ids else None,
        )
        print(
            json.dumps(
                {
                    "backfill": asdict(backfill),
                    "simulator": asdict(result),
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    finally:
        asyncio.run(runtime.aclose())


if __name__ == "__main__":
    main()
