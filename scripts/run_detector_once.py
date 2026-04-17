from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Run one detector pass on the latest persisted book state.")
    parser.add_argument("--constraint-id", dest="constraint_ids", action="append", type=int, help="Restrict to specific logical constraint IDs.")
    parser.add_argument("--detected-at", type=str, default=None, help="Override the detector timestamp in ISO-8601 format.")
    args = parser.parse_args()

    runtime = build_service_runtime()
    try:
        backfill = runtime.backfill_latest_books_from_db()
        result = runtime.detector_service.run(
            detected_at=_parse_datetime(args.detected_at),
            constraint_ids=tuple(args.constraint_ids) if args.constraint_ids else None,
        )
        print(
            json.dumps(
                {
                    "backfill": asdict(backfill),
                    "detector": asdict(result),
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    finally:
        import asyncio

        asyncio.run(runtime.aclose())


if __name__ == "__main__":
    main()
