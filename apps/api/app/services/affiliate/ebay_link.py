"""Turn a bare eBay product URL into an affiliate-tagged buy link.

Cross-merchant comparison offers (DataForSEO Google Shopping) sometimes surface
an untagged ``ebay.ca`` listing. A purchase through that link earns nothing.
This appends eBay Partner Network's tracking parameters so the UI can point
the comparison "View" link at one that actually pays.

``_MKRID_CA``/``_SITEID_CA`` are eBay's fixed rotation id and site id for the
eBay.ca storefront — the same for every EPN publisher promoting that site.
``campaign_id`` is what actually identifies *this* account. Both were read off
a real link generated in the EPN dashboard (2026-09), not guessed from memory —
eBay's link format is undocumented enough that a guessed value would silently
produce a link that looks tagged but earns nothing.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_EBAY_HOST_RE = re.compile(r"(?:^|\.)ebay\.[a-z.]+$", re.IGNORECASE)

_MKRID_CA = "706-53473-19255-0"
_SITEID_CA = "2"


def ebay_affiliate_url(
    product_url: str | None,
    campaign_id: str | None,
    *,
    customid: str | None = None,
) -> str | None:
    """Return ``product_url`` with EPN tracking params applied, or ``None``.

    ``None`` when there is nothing to tag (no URL, no campaign id) or the host
    is not an eBay storefront — callers fall back to the untagged URL.
    """

    if not product_url or not campaign_id:
        return None
    parts = urlsplit(product_url)
    if not _EBAY_HOST_RE.search(parts.hostname or ""):
        return None
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "mkcid": "1",
            "mkrid": _MKRID_CA,
            "siteid": _SITEID_CA,
            "campid": campaign_id,
            "toolid": "10001",
            "mkevt": "1",
        }
    )
    if customid:
        query["customid"] = customid
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
