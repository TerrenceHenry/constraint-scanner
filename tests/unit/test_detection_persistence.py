from __future__ import annotations

from datetime import datetime, timezone

from constraint_scanner.detection.persistence import merge_persistence_state


def test_merge_persistence_state_tracks_window() -> None:
    first = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
    second = datetime(2026, 4, 15, 18, 0, 5, tzinfo=timezone.utc)

    first_state = merge_persistence_state(
        existing_details=None,
        existing_first_seen_at=None,
        persistence_key="opp_1",
        detected_at=first,
    )
    second_state = merge_persistence_state(
        existing_details={"lifecycle": first_state.as_detail_json()},
        existing_first_seen_at=first_state.first_seen_at,
        persistence_key="opp_1",
        detected_at=second,
    )

    assert first_state.seen_count == 1
    assert second_state.first_seen_at == first
    assert second_state.last_seen_at == second
    assert second_state.persistence_ms == 5000
    assert second_state.seen_count == 2
