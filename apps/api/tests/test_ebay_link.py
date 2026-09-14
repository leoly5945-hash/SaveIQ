"""Affiliate tagging of eBay comparison offers."""

from __future__ import annotations

import pytest

from app.services.affiliate.ebay_link import ebay_affiliate_url


def test_tags_a_bare_ebay_url() -> None:
    out = ebay_affiliate_url("https://www.ebay.ca/itm/168644297649", "5339209072")
    assert out == (
        "https://www.ebay.ca/itm/168644297649"
        "?mkcid=1&mkrid=706-53473-19255-0&siteid=2&campid=5339209072&toolid=10001&mkevt=1"
    )


def test_keeps_existing_query_and_adds_a_subid() -> None:
    out = ebay_affiliate_url(
        "https://www.ebay.ca/itm/168644297649?_skw=macbook+pro",
        "5339209072",
        customid="check",
    )
    assert "_skw=macbook+pro" in out
    assert "campid=5339209072" in out
    assert "customid=check" in out


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "https://www.bestbuy.ca/en-ca/product/123",
        "https://notebay.example/itm/X",
    ],
)
def test_returns_none_when_nothing_to_tag(url: str | None) -> None:
    assert ebay_affiliate_url(url, "5339209072") is None


def test_returns_none_without_a_campaign_id() -> None:
    assert ebay_affiliate_url("https://www.ebay.ca/itm/X", "") is None
    assert ebay_affiliate_url("https://www.ebay.ca/itm/X", None) is None
