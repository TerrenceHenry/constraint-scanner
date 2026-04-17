# Constraint Scanner v1

Constraint Scanner v1 is a FastAPI + SQLAlchemy service for ingesting
prediction-market order books, grouping related markets, instantiating explicit
logical templates, detecting executable arbitrage, stress-testing the results,
and paper-routing only risk-approved opportunities.

Current v1 boundaries:

- executable pricing is orderbook-depth based; midpoint remains diagnostic only
- detection is template-based only
- paper trading is the only implemented routing path
- runtime controls are in-memory only for now
- subset/superset, mutual exclusion, and at-least-one templates are still safe
  placeholders

## Setup

1. Copy the environment template.

```powershell
Copy-Item .env.example .env
```

2. Start PostgreSQL.

```powershell
docker compose up -d postgres
```

3. Create a local Python environment and install the project.

```powershell
uv python install 3.11
uv venv --python 3.11 .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

If Python 3.11+ is already installed system-wide:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## DB Migration

Apply the current schema:

```powershell
uv run alembic upgrade head
```

## Bootstrap

Bootstrap active Polymarket markets into the local catalog:

```powershell
uv run python scripts/bootstrap_markets.py
```

Bootstrap and immediately persist initial orderbook snapshots:

```powershell
uv run python scripts/bootstrap_markets.py --snapshot-books
```

Seed example manual logical constraints from compatible existing markets:

```powershell
uv run python scripts/seed_manual_constraints.py
```

This currently seeds deterministic examples when it can find:

- a binary win/lose complement pair
- a native multi-outcome market

If those examples are not present yet, the script reports skipped items instead
of guessing.

## Run Feed Service

Bootstrap tradable markets, snapshot the books, and then enter the public
websocket consume loop:

```powershell
uv run python scripts/run_feed_service.py
```

Run only bootstrap + snapshot without staying on the websocket:

```powershell
uv run python scripts/run_feed_service.py --snapshot-only
```

Limit the bootstrap or consume pass while debugging:

```powershell
uv run python scripts/run_feed_service.py --bootstrap-limit 50 --event-limit 100
```

## Replay

Replay a recorded JSONL feed sequence into the same ingestion path used by live
websocket handling:

```powershell
uv run python scripts/replay_feed.py --input-file tests/replay/binary_complement_sequence.jsonl
```

Replay and continue into detection + simulation:

```powershell
uv run python scripts/replay_feed.py --input-file tests/replay/binary_complement_sequence.jsonl --detect --simulate
```

Replay and paper-route risk-approved opportunities:

```powershell
uv run python scripts/replay_feed.py --input-file tests/replay/binary_complement_sequence.jsonl --paper-route
```

Replay archived raw feed messages directly from the database:

```powershell
uv run python scripts/replay_feed.py --from-db --limit 500 --detect
```

Replay notes:

- replay does not re-archive replayed raw messages by default
- detector and simulator runs backfill the latest persisted books into the
  in-memory cache first
- JSONL replay records use a stable envelope with `source`, `channel`,
  `message_type`, `received_at`, `sequence_number`, and `payload`

## Run Detector

Run one detector pass on the latest persisted orderbook state:

```powershell
uv run python scripts/run_detector_once.py
```

Restrict to a specific logical constraint:

```powershell
uv run python scripts/run_detector_once.py --constraint-id 12
```

The detector script backfills the canonical in-memory book cache from the
database before evaluating constraints, so it can be run as a standalone
operator command.

## Simulate

Run one simulation pass on open opportunities:

```powershell
uv run python scripts/run_simulator_once.py
```

Restrict to specific opportunities:

```powershell
uv run python scripts/run_simulator_once.py --opportunity-id 5 --opportunity-id 8
```

## Run API

Start the operator API:

```powershell
uv run python scripts/run_api.py
```

Or run uvicorn directly:

```powershell
uvicorn constraint_scanner.main:app --reload
```

The API, CLI scripts, and replay path now all build the same shared runtime:

- shared in-memory control state
- shared latest-book cache shape
- shared detector, simulator, risk, and trader services

## Run Tests

Run the full suite:

```powershell
uv run --link-mode=copy --extra dev pytest -q
```

Run only the replay / end-to-end coverage:

```powershell
uv run --link-mode=copy --extra dev pytest tests/integration/test_end_to_end_replay.py -q
```

## Operational Notes

- `POST /controls/kill-switch` and `POST /controls/trading-mode` mutate the same
  authoritative runtime state the trader uses.
- `/opportunities` is open-only by default; request closed history explicitly
  with `?status=closed`.
- `/simulations` returns latest authoritative simulation summaries only.
- Paper orders and fills are persisted in `live_orders` / `live_fills`, but they
  remain top-level unmistakably paper:
  `venue_order_id = NULL`, `paper_fill_*`, and synthetic payload markers.

## TODO

- Placeholder templates remain unimplemented:
  `subset_superset`, `mutual_exclusion`, `at_least_one`
- Control state is runtime-only and resets on restart
- There is still no authenticated live trading path in v1
