"""Rule-based natural-language shopping query parsing."""

from __future__ import annotations

import pytest

from app.services.discovery.query import parse_shopping_query


@pytest.mark.parametrize(
    ("raw", "terms", "pmin", "pmax"),
    [
        ("power bank under $100", "power bank", None, 10000),
        ("4k tv below 800", "4k tv", None, 80000),
        ("noise cancelling headphones under 300 CAD", "noise cancelling headphones", None, 30000),
        ("gaming laptop between $1200 and 1800", "gaming laptop", 120000, 180000),
        ("robot vacuum over $400", "robot vacuum", 40000, None),
        ("i want a good espresso machine", "espresso machine", None, None),
        ("mechanical keyboard around 150", "mechanical keyboard", None, 15000),
        ("show me a monitor under 2k", "monitor", None, 200000),
        ("cheap standing desk 400 budget", "standing desk", None, 40000),
    ],
)
def test_parses_terms_and_budget(raw: str, terms: str, pmin: int | None, pmax: int | None) -> None:
    q = parse_shopping_query(raw)
    assert q.search_terms == terms
    assert q.price_min_cents == pmin
    assert q.price_max_cents == pmax
    assert q.parser_mode == "rules"


def test_a_bare_4k_is_not_read_as_a_price() -> None:
    q = parse_shopping_query("4k monitor")
    assert q.search_terms == "4k monitor"
    assert q.price_max_cents is None


def test_empty_query_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_shopping_query("   ")


def test_terms_never_empty_even_if_all_filler() -> None:
    q = parse_shopping_query("cheap thing under 50")
    assert q.search_terms == "thing"
    assert q.price_max_cents == 5000
