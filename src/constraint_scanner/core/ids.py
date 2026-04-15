from __future__ import annotations

from uuid import UUID, uuid5

from constraint_scanner.core.constants import ID_NAMESPACE


def make_stable_id(*parts: object, namespace: UUID = ID_NAMESPACE) -> str:
    """Create a deterministic UUID5 string from ordered parts."""

    normalized = "::".join(str(part).strip() for part in parts)
    return str(uuid5(namespace, normalized))


def make_prefixed_id(prefix: str, *parts: object, namespace: UUID = ID_NAMESPACE) -> str:
    """Create a readable deterministic identifier with a fixed prefix."""

    return f"{prefix}_{make_stable_id(*parts, namespace=namespace)}"
