"""Tests for CP6 URL -> product reference extraction."""

from __future__ import annotations

import pytest

from app.services import product_url
from app.services.product_url import extract_product_ref

ASIN = "B09VPHVT9Z"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.amazon.ca/dp/{ASIN}",
        f"https://www.amazon.ca/dp/{ASIN}/ref=sr_1_1?keywords=anker&qid=1",
        f"https://www.amazon.ca/Anker-737-Power-Bank/dp/{ASIN}/ref=x",
        f"https://www.amazon.ca/gp/product/{ASIN}?th=1&psc=1",
        f"https://www.amazon.ca/gp/aw/d/{ASIN}",
        f"https://amazon.ca/dp/{ASIN}",
        f"www.amazon.ca/dp/{ASIN}",
        f"https://www.amazon.ca/-/en/dp/{ASIN}",
        f"https://www.amazon.ca/some/path?asin={ASIN}&more=1",
    ],
)
def test_extracts_ca_asin(url: str) -> None:
    ref = extract_product_ref(url)
    assert ref is not None
    assert ref.retailer == "amazon"
    assert ref.market == "CA"
    assert ref.product_id == ASIN
    assert ref.keepa_domain == 6


def test_bare_asin() -> None:
    ref = extract_product_ref(f"  {ASIN.lower()} ")
    assert ref is not None
    assert ref.product_id == ASIN
    assert ref.market == ""
    assert ref.keepa_domain is None


def test_us_marketplace_is_recognised_but_not_ca() -> None:
    ref = extract_product_ref(f"https://www.amazon.com/dp/{ASIN}")
    assert ref is not None
    assert ref.market == "US"
    assert ref.keepa_domain == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://www.walmart.ca/en/ip/thing/123",
        "https://www.amazon.ca/",
        "https://www.amazon.ca/s?k=power+bank",
        "not a url at all",
        "",
        "https://example.com/dp/B09VPHVT9Z",  # right path shape, wrong host
    ],
)
def test_returns_none_for_unrecognised(url: str) -> None:
    assert extract_product_ref(url) is None


def test_shortlink_without_follow_is_none() -> None:
    assert extract_product_ref("https://amzn.to/3abcXYZ") is None


def test_shortlink_follows_one_redirect(monkeypatch) -> None:
    monkeypatch.setattr(
        product_url,
        "_follow_one_redirect",
        lambda url, **kw: f"https://www.amazon.ca/dp/{ASIN}?tag=x",
    )
    ref = extract_product_ref("https://amzn.to/3abcXYZ", follow_redirects=True)
    assert ref is not None
    assert ref.product_id == ASIN
    assert ref.market == "CA"
    assert ref.resolved_via_redirect is True
    assert ref.source_url == "https://amzn.to/3abcXYZ"


def test_shortlink_redirect_to_junk_is_none(monkeypatch) -> None:
    monkeypatch.setattr(
        product_url, "_follow_one_redirect", lambda url, **kw: "https://www.amazon.ca/s?k=x"
    )
    assert extract_product_ref("https://a.co/d/abc", follow_redirects=True) is None
