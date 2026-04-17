from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from constraint_scanner.clients.models import MarketStreamEvent
from constraint_scanner.clients.normalizers import normalize_market_stream_event
from constraint_scanner.core.clock import ensure_utc, utc_now
from constraint_scanner.db.models import RawFeedMessage
from constraint_scanner.runtime import PaperTradingRunResult, ServiceRuntime


@dataclass(frozen=True, slots=True)
class ReplayFeedRecord:
    """Deterministic replay envelope for one archived raw feed message."""

    source: str
    channel: str
    received_at: datetime
    payload: dict[str, Any]
    message_type: str | None = None
    sequence_number: int | None = None

    def to_event(self) -> MarketStreamEvent:
        """Normalize this replay record into a websocket market event."""

        normalized = normalize_market_stream_event(self.payload)
        return MarketStreamEvent(
            event_type=self.message_type or normalized.event_type,
            asset_id=normalized.asset_id,
            received_at=self.received_at,
            book=normalized.book,
            best_bid=normalized.best_bid,
            best_ask=normalized.best_ask,
            raw_payload=self.payload,
        )


@dataclass(frozen=True, slots=True)
class ReplayFeedResult:
    """Summary of a replay pass and any downstream pipeline work."""

    replayed_events: int
    detector_result: object | None = None
    simulator_result: object | None = None
    trader_result: PaperTradingRunResult | None = None


def load_replay_records_from_jsonl(path: str | Path) -> tuple[ReplayFeedRecord, ...]:
    """Load a deterministic replay sequence from newline-delimited JSON."""

    records: list[ReplayFeedRecord] = []
    replay_path = Path(path)
    for line in replay_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(
            ReplayFeedRecord(
                source=str(payload.get("source", "polymarket")),
                channel=str(payload.get("channel", "market")),
                message_type=str(payload["message_type"]) if payload.get("message_type") is not None else None,
                sequence_number=int(payload["sequence_number"]) if payload.get("sequence_number") is not None else None,
                received_at=_parse_datetime(payload.get("received_at")),
                payload=dict(payload["payload"]),
            )
        )
    return tuple(records)


class ReplayFeedRunner:
    """Replay archived feed messages into the canonical ingestion pipeline."""

    def __init__(self, runtime: ServiceRuntime) -> None:
        self._runtime = runtime

    def replay_records(
        self,
        records: tuple[ReplayFeedRecord, ...] | list[ReplayFeedRecord],
        *,
        run_detector: bool = False,
        run_simulator: bool = False,
        run_trader: bool = False,
        opportunity_ids: tuple[int, ...] | None = None,
        replayed_at: datetime | None = None,
    ) -> ReplayFeedResult:
        """Replay records in deterministic order and optionally continue downstream."""

        ordered_records = sorted(
            records,
            key=lambda item: (
                ensure_utc(item.received_at),
                item.sequence_number if item.sequence_number is not None else 0,
                json.dumps(item.payload, sort_keys=True),
            ),
        )
        replayed_events = 0
        for record in ordered_records:
            if record.channel != "market":
                continue
            self._runtime.market_feed_service.consumer.handle_event(record.to_event(), archive=False)
            replayed_events += 1

        if replayed_at is not None:
            effective_time = ensure_utc(replayed_at)
        elif ordered_records:
            effective_time = ensure_utc(ordered_records[-1].received_at)
        else:
            effective_time = utc_now()
        detector_result = None
        simulator_result = None
        trader_result = None

        if run_detector:
            detector_result = self._runtime.detector_service.run(detected_at=effective_time)
        if run_simulator:
            simulator_result = self._runtime.simulator_service.run(
                simulated_at=effective_time,
                opportunity_ids=opportunity_ids,
            )
        if run_trader:
            trader_result = self._runtime.run_trader_once(
                opportunity_ids=opportunity_ids,
                submitted_at=effective_time,
            )

        return ReplayFeedResult(
            replayed_events=replayed_events,
            detector_result=detector_result,
            simulator_result=simulator_result,
            trader_result=trader_result,
        )

    def replay_jsonl(
        self,
        path: str | Path,
        **kwargs: Any,
    ) -> ReplayFeedResult:
        """Replay a JSONL file of archived raw feed messages."""

        return self.replay_records(load_replay_records_from_jsonl(path), **kwargs)

    def replay_archived_messages(
        self,
        *,
        source: str = "polymarket",
        channel: str = "market",
        limit: int | None = None,
        **kwargs: Any,
    ) -> ReplayFeedResult:
        """Replay archived raw messages directly from the database."""

        with self._runtime.session_factory() as session:
            stmt = (
                select(RawFeedMessage)
                .where(
                    RawFeedMessage.source == source,
                    RawFeedMessage.channel == channel,
                )
                .order_by(
                    RawFeedMessage.received_at.asc(),
                    RawFeedMessage.sequence_number.asc(),
                    RawFeedMessage.id.asc(),
                )
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = list(session.scalars(stmt))

        records = tuple(
            ReplayFeedRecord(
                source=row.source,
                channel=row.channel,
                message_type=row.message_type,
                sequence_number=row.sequence_number,
                received_at=ensure_utc(row.received_at),
                payload=dict(row.payload),
            )
            for row in rows
        )
        return self.replay_records(records, **kwargs)


def _parse_datetime(value: object) -> datetime:
    if value is None:
        return utc_now()
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
