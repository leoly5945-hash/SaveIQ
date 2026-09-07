"""CP6 — turn a pasted retailer product URL into a provider lookup reference.

The public price-checker's entry point is "paste an Amazon.ca link". This module
does the parsing half: URL (or a bare ASIN) -> ``ExtractedProductRef`` with the
retailer, market and product id. Mapping that to a concrete
:class:`~app.providers.base.ProductDataProvider` is the caller's job.

No network by default. Short links (``amzn.to`` / ``a.co``) can optionally be
resolved by following one redirect.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

from pydantic import BaseModel

# ASIN: 10 chars, A–Z and 0–9. ISBN-derived ASINs are 10 digits.
_BARE_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")

# Amazon TLD -> (market, Keepa domain id). Only marketplaces we can plausibly
# serve; others resolve the ASIN but with market left for the caller to reject.
_AMAZON_TLD_MARKET: dict[str, tuple[str, int]] = {
    "ca": ("CA", 6),
    "com": ("US", 1),
    "co.uk": ("GB", 2),
    "de": ("DE", 3),
    "fr": ("FR", 4),
    "co.jp": ("JP", 5),
    "it": ("IT", 8),
    "es": ("ES", 9),
    "in": ("IN", 9),
    "com.mx": ("MX", 11),
}

_AMAZON_HOST_RE = re.compile(
    r"(?:^|\.)amazon\.((?:com\.mx)|(?:co\.uk)|(?:co\.jp)|ca|com|de|fr|it|es|in)$"
)
_AMAZON_SHORTENERS = {"amzn.to", "amzn.eu", "a.co"}

# Path shapes that carry an ASIN, most specific first.
_PATH_ASIN_RES = (
    re.compile(r"/dp/([A-Z0-9]{10})(?:[/?]|$)"),
    re.compile(r"/gp/product/([A-Z0-9]{10})(?:[/?]|$)"),
    re.compile(r"/gp/aw/d/([A-Z0-9]{10})(?:[/?]|$)"),
    re.compile(r"/gp/offer-listing/([A-Z0-9]{10})(?:[/?]|$)"),
    re.compile(r"/product/([A-Z0-9]{10})(?:[/?]|$)"),
    re.compile(r"/-/[a-z]{2}/dp/([A-Z0-9]{10})(?:[/?]|$)"),
)


class ExtractedProductRef(BaseModel):
    retailer: str  # "amazon"
    market: str  # ISO-3166 alpha-2, "" when unknown (bare ASIN)
    product_id: str  # ASIN
    keepa_domain: int | None = None
    source_url: str
    resolved_via_redirect: bool = False


def _amazon_market(host: str) -> tuple[str, int] | None:
    match = _AMAZON_HOST_RE.search(host)
    if not match:
        return None
    return _AMAZON_TLD_MARKET.get(match.group(1))


def _asin_from_amazon_url(parsed: ParseResult) -> str | None:
    path = unquote(parsed.path or "")
    for pattern in _PATH_ASIN_RES:
        m = pattern.search(path)
        if m:
            return m.group(1)
    # Query params some links use.
    query = parse_qs(parsed.query or "")
    for key in ("asin", "ASIN", "pd_rd_i", "psc_asin"):
        values = query.get(key)
        if values and _BARE_ASIN_RE.match(values[0].strip().upper()):
            return values[0].strip().upper()
    # Last resort: a lone 10-char token between path separators.
    for segment in path.split("/"):
        token = segment.strip().upper()
        if _BARE_ASIN_RE.match(token):
            return token
    return None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Surface the redirect as an HTTPError instead of following it."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _follow_one_redirect(url: str, *, timeout_seconds: float = 6.0) -> str | None:
    """Return the Location of a single redirect, or ``None``. HEAD, no body."""

    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "SaveIQ/1.0"})
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            location = response.headers.get("Location")
            return str(location) if location else None
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            loc = exc.headers.get("Location")
            return str(loc) if loc else None
        return None
    except (TimeoutError, OSError, urllib.error.URLError):
        return None


def extract_product_ref(
    raw: str,
    *,
    follow_redirects: bool = False,
) -> ExtractedProductRef | None:
    """Parse ``raw`` (a URL or a bare ASIN) into an :class:`ExtractedProductRef`.

    Returns ``None`` when nothing recognisable is found.
    """

    text = (raw or "").strip()
    if not text:
        return None

    # Bare ASIN.
    if _BARE_ASIN_RE.match(text.upper()):
        return ExtractedProductRef(
            retailer="amazon",
            market="",
            product_id=text.upper(),
            keepa_domain=None,
            source_url=text,
        )

    candidate = text if "//" in text else f"https://{text}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()

    if host in _AMAZON_SHORTENERS:
        if not follow_redirects:
            return None
        location = _follow_one_redirect(candidate)
        if not location:
            return None
        ref = extract_product_ref(location, follow_redirects=False)
        if ref is not None:
            return ref.model_copy(update={"source_url": text, "resolved_via_redirect": True})
        return None

    market_info = _amazon_market(host)
    if market_info is None:
        return None

    asin = _asin_from_amazon_url(parsed)
    if asin is None:
        return None

    market, keepa_domain = market_info
    return ExtractedProductRef(
        retailer="amazon",
        market=market,
        product_id=asin,
        keepa_domain=keepa_domain,
        source_url=text,
    )
