from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.replay.replay_feed import ReplayFeedRunner
from constraint_scanner.runtime import build_service_runtime


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return ensure_utc(datetime.fromisoformat(text))


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Replay archived raw feed messages into the canonical ingestion pipeline.")
    parser.add_argument("--input-file", type=str, default=None, help="Replay records from a JSONL file.")
    parser.add_argument("--from-db", action="store_true", help="Replay archived raw feed messages from the database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit DB-sourced replay rows.")
    parser.add_argument("--detect", action="store_true", help="Run the detector after replay completes.")
    parser.add_argument("--simulate", action="store_true", help="Run the simulator after replay completes.")
    parser.add_argument("--paper-route", action="store_true", help="Run risk gating and paper routing after replay.")
    parser.add_argument("--replayed-at", type=str, default=None, help="Override the replay completion timestamp in ISO-8601 format.")
    args = parser.parse_args()

    if bool(args.input_file) == bool(args.from_db):
        parser.error("Choose exactly one replay source: --input-file or --from-db.")

    runtime = build_service_runtime()
    if args.paper_route:
        runtime.runtime_controls.trading_mode_state.set_mode(TradingMode.PAPER, reason="replay_cli")

    try:
        runner = ReplayFeedRunner(runtime)
        replay_kwargs = {
            "run_detector": args.detect or args.simulate or args.paper_route,
            "run_simulator": args.simulate or args.paper_route,
            "run_trader": args.paper_route,
            "replayed_at": _parse_datetime(args.replayed_at),
        }
        if args.input_file:
            result = runner.replay_jsonl(args.input_file, **replay_kwargs)
        else:
            result = runner.replay_archived_messages(limit=args.limit, **replay_kwargs)
        print(json.dumps(asdict(result), indent=2, sort_keys=True, default=str))
    finally:
        await runtime.aclose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
