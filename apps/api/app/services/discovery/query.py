"""Turn a natural-language shopping request into a structured query.

Layer 3, entry step. ``mode="rules"`` is a deterministic parser that handles the
common, unambiguous shapes — "power bank under $100", "4k tv below 800",
"gaming laptop between $1200 and 1800". It does **not** try to be clever about
loose phrasing ("something around 2k-ish"); that long tail is exactly what the
LLM parser (via :mod:`app.services.router`, once a provider key is configured) is
for. When the parser is unsure it just returns the cleaned text as the search
terms and no budget — a safe degrade.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# A money amount, optionally with a "k" thousands suffix. The suffix only counts
# inside a directional phrase below — a bare "4k" in the middle of a query is a
# product spec, not a price.
_AMOUNT = r"\$?\s?(\d[\d,]*(?:\.\d{1,2})?)(k)?\b"
_MAX_RE = re.compile(
    rf"(?:under|below|less than|no more than|max|up to|around|about|<)\s*{_AMOUNT}", re.I
)
_MIN_RE = re.compile(rf"(?:over|above|more than|at least|min|starting at|>)\s*{_AMOUNT}", re.I)
_BETWEEN_RE = re.compile(rf"(?:between|from)\s*{_AMOUNT}\s*(?:and|to|[-–])\s*{_AMOUNT}", re.I)
_TRAILING_BUDGET_RE = re.compile(rf"{_AMOUNT}\s*(?:budget|or less|or under)?\s*$", re.I)

_STOP_WORDS = frozenset(
    {
        "i",
        "want",
        "need",
        "a",
        "an",
        "the",
        "some",
        "please",
        "me",
        "my",
        "looking",
        "for",
        "show",
        "find",
        "help",
        "get",
        "buy",
        "best",
        "cheap",
        "cheapest",
        "good",
        "great",
        "nice",
        "recommend",
        "suggest",
        "any",
        "right",
        "now",
        "today",
        "these",
        "days",
        "that",
        "is",
        "are",
    }
)
_BUDGET_TOKENS = frozenset(
    {
        "under",
        "below",
        "less",
        "than",
        "no",
        "more",
        "max",
        "up",
        "to",
        "around",
        "about",
        "over",
        "above",
        "at",
        "least",
        "starting",
        "between",
        "from",
        "and",
        "budget",
        "or",
        "dollars",
        "dollar",
        "cad",
        "usd",
        "bucks",
        "grand",
        "ish",
    }
)


class ShoppingQuery(BaseModel):
    raw: str
    search_terms: str = Field(min_length=1)
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    parser_mode: str = "rules"


def _to_cents(number: str, k_suffix: str | None) -> int:
    value = float(number.replace(",", ""))
    if k_suffix:
        value *= 1000
    return round(value * 100)


# A pure money number (optional $, no letter suffix) — safe to drop from terms.
# "4k" / "1080p" / "5g" keep their trailing letter and survive the negative
# lookahead.
_BARE_NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d{1,2})?(?![a-z\d])", re.I)


def _clean_terms(text: str) -> str:
    text = _BARE_NUMBER_RE.sub(" ", text.lower())
    text = re.sub(r"[^\w\s+\-/&']", " ", text)
    kept = [tok for tok in text.split() if tok not in _STOP_WORDS and tok not in _BUDGET_TOKENS]
    return " ".join(kept).strip()


def parse_shopping_query(raw: str, *, mode: str = "rules") -> ShoppingQuery:
    text = raw.strip()
    if not text:
        raise ValueError("empty query")

    price_min = price_max = None
    remainder = text
    between = _BETWEEN_RE.search(text)
    if between:
        a = _to_cents(between.group(1), between.group(2))
        b = _to_cents(between.group(3), between.group(4))
        price_min, price_max = min(a, b), max(a, b)
        remainder = text[: between.start()] + " " + text[between.end() :]
    else:
        m_max = _MAX_RE.search(text)
        if m_max:
            price_max = _to_cents(m_max.group(1), m_max.group(2))
            remainder = remainder.replace(m_max.group(0), " ", 1)
        m_min = _MIN_RE.search(text)
        if m_min:
            price_min = _to_cents(m_min.group(1), m_min.group(2))
            remainder = remainder.replace(m_min.group(0), " ", 1)
        if price_min is None and price_max is None:
            trailing = _TRAILING_BUDGET_RE.search(text)
            if trailing:
                price_max = _to_cents(trailing.group(1), trailing.group(2))
                remainder = text[: trailing.start()]

    terms = _clean_terms(remainder)
    if not terms:
        terms = _clean_terms(text) or _BARE_NUMBER_RE.sub(" ", text).strip() or text

    return ShoppingQuery(
        raw=text,
        search_terms=terms,
        price_min_cents=price_min,
        price_max_cents=price_max,
        parser_mode="rules",  # mode kept for a future "llm" path
    )
