from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_whitespace(value: str) -> str:
    """Collapse runs of whitespace into a single space."""

    return _WHITESPACE_RE.sub(" ", value).strip()


def slugify(value: str) -> str:
    """Convert text into a simple deterministic slug."""

    normalized = normalize_whitespace(value).lower()
    slug = _NON_SLUG_RE.sub("-", normalized).strip("-")
    return slug or "n-a"


def join_non_empty(parts: list[str], separator: str = " ") -> str:
    """Join non-empty strings with a stable separator."""

    return separator.join(part for part in parts if part)
