from __future__ import annotations

import re
from dataclasses import dataclass

from constraint_scanner.catalog.normalizer import NormalizedMarketText

_PARTIES = {
    "democrat": "democratic",
    "democrats": "democratic",
    "democratic": "democratic",
    "republican": "republican",
    "republicans": "republican",
    "labour": "labour",
    "labor": "labour",
    "conservative": "conservative",
}
_COUNTRY_ALIASES = {
    "us": "united states",
    "u.s.": "united states",
    "usa": "united states",
    "united states": "united states",
    "america": "united states",
    "uk": "united kingdom",
    "u.k.": "united kingdom",
    "britain": "united kingdom",
    "united kingdom": "united kingdom",
    "canada": "canada",
    "france": "france",
    "germany": "germany",
    "mexico": "mexico",
    "india": "india",
    "china": "china",
    "russia": "russia",
    "ukraine": "ukraine",
    "israel": "israel",
}
_OFFICES = {
    "president": "president",
    "presidency": "president",
    "prime minister": "prime_minister",
    "governor": "governor",
    "mayor": "mayor",
    "senate": "senate",
    "house": "house",
    "supreme court": "supreme_court",
}
_TITLECASE_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_NAME_PREFIX_STOPWORDS = {"Will", "Can", "Could", "Should", "Would", "Did", "Does", "Do", "Is", "Are", "Who"}


@dataclass(frozen=True, slots=True)
class ExtractedEntities:
    """Deterministic, low-complexity extracted entities."""

    people: tuple[str, ...]
    parties: tuple[str, ...]
    countries: tuple[str, ...]
    offices: tuple[str, ...]
    dates: tuple[str, ...]
    numbers: tuple[str, ...]


def extract_entities(text: str, normalized: NormalizedMarketText) -> ExtractedEntities:
    """Extract simple entities from market text without probabilistic NLP."""

    lowered = f"{normalized.title_normalized} {normalized.description_normalized}".strip()
    people = tuple(
        dict.fromkeys(
            match
            for match in _TITLECASE_NAME_RE.findall(text)
            if match.split(" ", 1)[0] not in _NAME_PREFIX_STOPWORDS
        )
    )
    parties = tuple(dict.fromkeys(value for token, value in _PARTIES.items() if f" {token} " in f" {lowered} "))
    countries = tuple(
        dict.fromkeys(value for token, value in _COUNTRY_ALIASES.items() if f" {token} " in f" {lowered} ")
    )
    offices = tuple(dict.fromkeys(value for token, value in _OFFICES.items() if token in lowered))
    dates = tuple(dict.fromkeys((*normalized.date_tokens, *normalized.years)))
    numbers = tuple(dict.fromkeys(_NUMBER_RE.findall(lowered)))

    return ExtractedEntities(
        people=people,
        parties=parties,
        countries=countries,
        offices=offices,
        dates=dates,
        numbers=numbers,
    )
