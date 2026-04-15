from __future__ import annotations

import re
from dataclasses import dataclass

from constraint_scanner.core.text_utils import normalize_whitespace

_PUNCTUATION_RE = re.compile(r"[,:;!?\"“”'`]+")
_DOT_RE = re.compile(r"\.(?!\d)")
_BRACKET_RE = re.compile(r"[\(\)\[\]\{\}]")
_SEPARATOR_RE = re.compile(r"[/\\|]+")
_DASH_RE = re.compile(r"[–—]+")
_MONTH_REPLACEMENTS = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sep": "09",
    "sept": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}
_MONTH_NAME_RE = re.compile(r"\b(" + "|".join(sorted(_MONTH_REPLACEMENTS, key=len, reverse=True)) + r")\.?\b")
_MONTH_YEAR_RE = re.compile(r"\b(0[1-9]|1[0-2])\s+(19\d{2}|20\d{2}|21\d{2})\b")
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
_DATE_TOKEN_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})(?:[-/](0[1-9]|1[0-2]))?\b")
_STOPWORDS = {
    "a",
    "an",
    "by",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
}


@dataclass(frozen=True, slots=True)
class NormalizedMarketText:
    """Normalized market text with conservative lexical helpers."""

    title_original: str
    description_original: str
    title_normalized: str
    description_normalized: str
    title_tokens: tuple[str, ...]
    lexical_tokens: tuple[str, ...]
    years: tuple[str, ...]
    date_tokens: tuple[str, ...]

    @property
    def lexical_key(self) -> str:
        """Stable lexical key for conservative grouping heuristics."""

        return " ".join(self.lexical_tokens)


def normalize_market_text(title: str, description: str | None = None) -> NormalizedMarketText:
    """Normalize market title and description conservatively for grouping."""

    clean_title = _normalize_text(title)
    clean_description = _normalize_text(description or "")
    title_tokens = tuple(token for token in clean_title.split(" ") if token)
    lexical_tokens = tuple(token for token in title_tokens if token not in _STOPWORDS)
    years = tuple(dict.fromkeys(_YEAR_RE.findall(clean_title)))
    date_tokens = tuple(dict.fromkeys(match[0] + (f"-{match[1]}" if match[1] else "") for match in _DATE_TOKEN_RE.findall(clean_title)))

    return NormalizedMarketText(
        title_original=title,
        description_original=description or "",
        title_normalized=clean_title,
        description_normalized=clean_description,
        title_tokens=title_tokens,
        lexical_tokens=lexical_tokens,
        years=years,
        date_tokens=date_tokens,
    )


def _normalize_text(value: str) -> str:
    lowered = normalize_whitespace(value).lower()
    lowered = _MONTH_NAME_RE.sub(lambda match: _MONTH_REPLACEMENTS[match.group(1)], lowered)
    lowered = _DOT_RE.sub("", lowered)
    lowered = _MONTH_YEAR_RE.sub(lambda match: f"{match.group(2)}-{match.group(1)}", lowered)
    lowered = _PUNCTUATION_RE.sub("", lowered)
    lowered = _BRACKET_RE.sub(" ", lowered)
    lowered = _SEPARATOR_RE.sub(" ", lowered)
    lowered = _DASH_RE.sub(" ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return normalize_whitespace(lowered)
