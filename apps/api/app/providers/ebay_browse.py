"""eBay Browse API — new, Canada-shipped eBay.ca listings for a product.

Replaces the eBay rows that used to come through Google Shopping, which had no
condition (a used $11 mouse sat next to a new $24 one) and only a Google search
link that could never earn the EPN commission.

What we keep, and why:
- condition New only (``conditionIds:{1000}``), Buy It Now only;
- item located in Canada, priced in CAD, with a known shipping cost — so the
  total we show is the total the shopper pays, with no border duties;
- sellers with >= 98% positive feedback over >= 50 ratings.

Search is by GTIN (UPC/EAN from Keepa) when we have one — the same barcode is
the same product — and by title otherwise, in which case the normal title
matcher decides. With ``affiliateCampaignId`` in ``X-EBAY-C-ENDUSERCTX`` eBay
returns ``itemAffiliateWebUrl``, an EPN-tracked link.

Auth is an application token (client-credentials grant, public ``api_scope``),
cached until shortly before it expires. Results are cached per query for an
hour. Every failure returns ``[]``: eBay is a nice-to-have next to the verdict.
"""

from __future__ import annotations

import base64
import logging
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.base import ProviderOffer

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SCOPE = "https://api.ebay.com/oauth/api_scope"
_MARKETPLACE = "EBAY_CA"
_FILTER = (
    "conditionIds:{1000},buyingOptions:{FIXED_PRICE},"
    "itemLocationCountry:CA,deliveryCountry:CA,priceCurrency:CAD"
)
_MIN_FEEDBACK_PCT = 98.0
_MIN_FEEDBACK_SCORE = 50
_CACHE_SECONDS = 3600
_TIMEOUT_SECONDS = 6.0

logger = logging.getLogger(__name__)


def _describe_failure(exc: Exception) -> str:
    """Status + eBay's error id/message, never a credential."""

    if isinstance(exc, httpx.HTTPStatusError):
        step = "token" if "/oauth2/" in exc.request.url.path else "search"
        detail = ""
        try:
            body = exc.response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                detail = f"{errors[0].get('errorId', '')} {errors[0].get('message', '')}"
            else:
                detail = f"{body.get('error', '')} {body.get('error_description', '')}"
        return f"{step} HTTP {exc.response.status_code} {detail.strip()}".strip()[:160]
    return type(exc).__name__


class EbayBrowseClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        campaign_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._campaign_id = campaign_id
        self._transport = transport
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._cache: dict[tuple[str, str], tuple[float, list[ProviderOffer]]] = {}
        self.last_error: str | None = None
        self.last_search: str | None = None

    def status(self) -> str:
        """``untried``, the last failure, or what the last search returned and kept."""

        if self.last_error:
            return f"error: {self.last_error}"
        return f"ok: {self.last_search}" if self.last_search else "untried"

    async def new_offers(
        self,
        *,
        provider_product_id: str,
        gtin: str | None,
        title: str | None,
        limit: int = 10,
    ) -> list[ProviderOffer]:
        """New eBay.ca offers for the product, cheapest first. Never raises."""

        if gtin:
            key = ("gtin", gtin)
        elif title:
            key = ("q", " ".join(title.split()[:12]))
        else:
            return []
        now = self._clock()
        hit = self._cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT_SECONDS
            ) as client:
                token = await self._app_token(client)
                params: dict[str, str | int] = {
                    "filter": _FILTER,
                    "sort": "price",
                    "limit": max(1, min(limit * 3, 50)),
                }
                params["gtin" if key[0] == "gtin" else "q"] = key[1]
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": _MARKETPLACE,
                }
                if self._campaign_id:
                    headers["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={self._campaign_id}"
                resp = await client.get(_SEARCH_URL, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:  # noqa: BLE001 - never let eBay break a price check
            self.last_error = _describe_failure(exc)
            logger.warning("eBay Browse API unavailable: %s", self.last_error)
            return []
        raw_items = payload.get("itemSummaries") or []
        dropped: Counter[str] = Counter()
        offers = []
        for item in raw_items:
            offer, why = _parse_item(item, provider_product_id, matched_by=key[0])
            if offer is None:
                dropped[why] += 1
            else:
                offers.append(offer)
        offers = offers[:limit]
        self.last_error = None
        drops = ", ".join(f"{n} {why}" for why, n in sorted(dropped.items())) or "none"
        self.last_search = (
            f"by {key[0]}: {len(raw_items)} returned, {len(offers)} kept (dropped: {drops})"
        )
        self._cache[key] = (now + _CACHE_SECONDS, offers)
        return offers

    async def _app_token(self, client: httpx.AsyncClient) -> str:
        if self._token and self._clock() < self._token_expires_at:
            return self._token
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        resp = await client.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": _SCOPE},
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = str(body["access_token"])
        self._token_expires_at = self._clock() + max(60, int(body.get("expires_in", 7200)) - 300)
        return self._token


def _cents(amount: Any) -> int | None:
    try:
        return round(float(amount["value"]) * 100)
    except (KeyError, TypeError, ValueError):
        return None


def _parse_item(
    item: dict[str, Any], provider_product_id: str, *, matched_by: str
) -> tuple[ProviderOffer | None, str]:
    """The offer, or ``None`` and why it was dropped."""

    if item.get("conditionId") not in (None, "1000"):
        return None, "not new"
    price = item.get("price") or {}
    if price.get("currency") != "CAD":
        return None, "not CAD"
    price_cents = _cents(price)
    shipping: list[int] = []
    for option in item.get("shippingOptions") or []:
        cost = option.get("shippingCost") or {}
        cents = _cents(cost) if cost.get("currency", "CAD") == "CAD" else None
        if cents is not None:
            shipping.append(cents)
    if price_cents is None or not shipping:
        return None, "no shipping cost"  # can't state a real total
    seller = item.get("seller") or {}
    try:
        pct = float(seller["feedbackPercentage"])
        score = int(seller["feedbackScore"])
    except (KeyError, TypeError, ValueError):
        return None, "no seller feedback"
    if pct < _MIN_FEEDBACK_PCT or score < _MIN_FEEDBACK_SCORE:
        return None, "weak seller"
    url = item.get("itemAffiliateWebUrl") or item.get("itemWebUrl")
    if not url:
        return None, "no url"
    offer = ProviderOffer(
        provider="ebay",
        provider_product_id=provider_product_id,
        merchant="eBay",
        price_cents=price_cents,
        shipping_cents=min(shipping),
        currency="CAD",
        availability="in_stock",
        condition="new",
        url=url,
        observed_at=datetime.now(tz=UTC),
        metadata={
            "title": item.get("title"),
            "matched_by": matched_by,
            "seller_feedback_pct": pct,
            "seller_feedback_score": score,
            "affiliate": bool(item.get("itemAffiliateWebUrl")),
        },
    )
    return offer, ""


_client: EbayBrowseClient | None = None
_client_key: tuple[str, str, str | None] | None = None


def get_ebay_client(settings: Any) -> EbayBrowseClient | None:
    """Process-wide client (keeps the token + result cache), or ``None`` unconfigured."""

    global _client, _client_key
    if not settings.ebay_client_id or not settings.ebay_client_secret:
        return None
    key = (settings.ebay_client_id, settings.ebay_client_secret, settings.ebay_partner_campaign_id)
    if _client is None or _client_key != key:
        _client = EbayBrowseClient(
            settings.ebay_client_id,
            settings.ebay_client_secret,
            campaign_id=settings.ebay_partner_campaign_id,
        )
        _client_key = key
    return _client
