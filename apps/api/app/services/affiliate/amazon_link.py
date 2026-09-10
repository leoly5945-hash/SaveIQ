"""Turn a bare Amazon product URL into an affiliate-tagged buy link.

The price-check flow gets ``product_url`` straight from the provider (Keepa),
which is an untagged ``https://www.amazon.<tld>/dp/<ASIN>``. A purchase through
that link earns nothing. This helper appends our Amazon Associates ``tag`` (and
an ``ascsubtag`` SubID for channel reconciliation) so the UI can point the "buy"
CTA at a link that actually pays.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_AMAZON_HOST_RE = re.compile(r"(?:^|\.)amazon\.[a-z.]+$", re.IGNORECASE)


def amazon_affiliate_url(
    product_url: str | None,
    tag: str | None,
    *,
    subtag: str | None = None,
) -> str | None:
    """Return ``product_url`` with ``tag``/``ascsubtag`` applied, or ``None``.

    ``None`` when there is nothing to tag (no URL, no tag) or the host is not an
    Amazon storefront — callers fall back to the untagged ``product_url``.
    """

    if not product_url or not tag:
        return None
    parts = urlsplit(product_url)
    if not _AMAZON_HOST_RE.search(parts.hostname or ""):
        return None
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["tag"] = tag
    if subtag:
        query["ascsubtag"] = subtag
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
