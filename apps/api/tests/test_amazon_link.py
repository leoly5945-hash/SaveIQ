"""Affiliate tagging of the price-check buy link."""

from __future__ import annotations

import pytest

from app.services.affiliate.amazon_link import amazon_affiliate_url


def test_tags_a_bare_amazon_url() -> None:
    assert (
        amazon_affiliate_url("https://www.amazon.ca/dp/B09VPHVT9Z", "saveiq-20", subtag="check")
        == "https://www.amazon.ca/dp/B09VPHVT9Z?tag=saveiq-20&ascsubtag=check"
    )


def test_keeps_existing_query_and_overrides_tag() -> None:
    out = amazon_affiliate_url(
        "https://www.amazon.ca/dp/B09VPHVT9Z?tag=someone-else&th=1", "saveiq-20"
    )
    assert out == "https://www.amazon.ca/dp/B09VPHVT9Z?tag=saveiq-20&th=1"


def test_subtag_is_optional() -> None:
    assert amazon_affiliate_url("https://amazon.co.uk/dp/X", "t") == (
        "https://amazon.co.uk/dp/X?tag=t"
    )


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "https://www.bestbuy.ca/en-ca/product/123",
        "https://notamazon.example/dp/X",
    ],
)
def test_returns_none_when_nothing_to_tag(url: str | None) -> None:
    assert amazon_affiliate_url(url, "saveiq-20") is None


def test_returns_none_without_a_tag() -> None:
    assert amazon_affiliate_url("https://www.amazon.ca/dp/X", "") is None
    assert amazon_affiliate_url("https://www.amazon.ca/dp/X", None) is None
