from __future__ import annotations

from constraint_scanner.core.ids import make_prefixed_id, make_stable_id


def test_make_stable_id_is_deterministic() -> None:
    first = make_stable_id("market", 42, "YES")
    second = make_stable_id("market", 42, "YES")
    third = make_stable_id("market", 42, "NO")

    assert first == second
    assert first != third


def test_make_prefixed_id_keeps_prefix() -> None:
    value = make_prefixed_id("opp", "group-1", "template-a")

    assert value.startswith("opp_")
