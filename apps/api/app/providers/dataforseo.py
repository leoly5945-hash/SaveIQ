"""DataForSEO Google Shopping provider — multi-merchant price comparison.

Given a product *title* (we get it from Keepa when the shopper pastes an Amazon
link), DataForSEO's Google Shopping endpoint returns the same product's offers
across other retailers (Walmart CA, Best Buy CA, Newegg, …). No price history —
this provider answers ``search`` / ``get_offers`` / ``get_price`` only.

DataForSEO is query-based, not id-based: ``get_offers(provider_product_id)``
treats the id as the search term.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import urllib.error
import urllib.request
import zlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from app.providers.base import (
    ProviderCapability,
    ProviderError,
    ProviderOffer,
    ProviderPrice,
    ProviderProduct,
)

logger = logging.getLogger(__name__)

DATAFORSEO_API_BASE = "https://api.dataforseo.com"
_SHOPPING_LIVE_PATH = "/v3/merchant/google/products/live/advanced"

# DataForSEO location_code -> (market, currency).
_LOCATION_LOCALE: dict[int, tuple[str, str]] = {
    2124: ("CA", "CAD"),
    2840: ("US", "USD"),
    2826: ("GB", "GBP"),
    2276: ("DE", "EUR"),
    2250: ("FR", "EUR"),
    2380: ("IT", "EUR"),
    2724: ("ES", "EUR"),
}


class DataForSEOTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        auth_header: str,
        payload: Sequence[Mapping[str, Any]],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST JSON with Basic auth and return the decoded JSON object."""


def _decompress(raw: bytes, content_encoding: str | None) -> bytes:
    enc = (content_encoding or "").lower().strip()
    if enc == "gzip" or raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    if enc == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


class UrllibDataForSEOTransport:
    def post_json(
        self,
        url: str,
        *,
        auth_header: str,
        payload: Sequence[Mapping[str, Any]],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(list(payload)).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                encoding = response.headers.get("Content-Encoding")
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"DataForSEO request failed (HTTP {exc.code})") from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise ProviderError("DataForSEO request failed (transport error)") from exc
        try:
            decoded = json.loads(_decompress(raw, encoding).decode("utf-8"))
        except (OSError, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("DataForSEO returned an undecodable body") from exc
        if not isinstance(decoded, Mapping):
            raise ProviderError("DataForSEO returned a non-object response")
        return decoded


def _as_price_cents(value: Any) -> int | None:
    try:
        cents = round(float(value) * 100)
    except (TypeError, ValueError):
        return None
    return cents if cents > 0 else None


class DataForSEOProvider:
    name = "dataforseo"
    capabilities = frozenset(
        {
            ProviderCapability.search,
            ProviderCapability.get_offers,
            ProviderCapability.get_price,
        }
    )

    def __init__(
        self,
        *,
        login: str | None,
        password: str | None,
        location_code: int = 2124,
        language_code: str = "en",
        timeout_seconds: float = 25.0,
        transport: DataForSEOTransport | None = None,
        now: datetime | None = None,
    ) -> None:
        self._login = login
        self._password = password
        self._location_code = location_code
        self._language_code = language_code
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrllibDataForSEOTransport()
        self._now = now
        self.market, self.currency = _LOCATION_LOCALE.get(location_code, ("CA", "CAD"))

    # -- protocol --------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._login and self._password)

    async def search_products(self, query: str, *, limit: int = 10) -> list[ProviderProduct]:
        items = await self._shopping_items(query)
        out: list[ProviderProduct] = []
        for item in items[: max(limit, 0)]:
            title = _clean_str(item.get("title"))
            if not title:
                continue
            out.append(
                ProviderProduct(
                    provider=self.name,
                    provider_product_id=str(item.get("product_id") or query),
                    title=title,
                    brand=_clean_str(item.get("brand")),
                    market=self.market,
                    currency=self.currency,
                    product_url=_clean_str(item.get("url")) or _clean_str(item.get("direct_url")),
                    metadata={
                        "seller": _clean_str(item.get("seller")),
                        "price_cents": _as_price_cents(item.get("price")),
                        "source": "google_shopping",
                    },
                )
            )
        return out

    async def get_offers(self, provider_product_id: str) -> list[ProviderOffer]:
        items = await self._shopping_items(provider_product_id)
        observed = self._now or datetime.now(tz=UTC)
        offers: list[ProviderOffer] = []
        for item in items:
            price_cents = _as_price_cents(item.get("price"))
            seller = _clean_str(item.get("seller"))
            if price_cents is None or not seller:
                continue
            offers.append(
                ProviderOffer(
                    provider=self.name,
                    provider_product_id=provider_product_id,
                    merchant=seller,
                    price_cents=price_cents,
                    shipping_cents=_as_price_cents(item.get("price_shipping")) or 0,
                    currency=_clean_str(item.get("currency")) or self.currency,
                    availability="in_stock",
                    condition="new",
                    url=_clean_str(item.get("url")) or _clean_str(item.get("direct_url")),
                    observed_at=observed,
                    metadata={
                        "title": _clean_str(item.get("title")),
                        "rating": item.get("rating"),
                        "product_id": item.get("product_id"),
                    },
                )
            )
        return offers

    async def get_price(self, provider_product_id: str) -> ProviderPrice | None:
        offers = await self.get_offers(provider_product_id)
        priced = [o for o in offers if o.total_cents is not None]
        if not priced:
            return None
        cheapest = min(priced, key=lambda o: o.total_cents or 0)
        return ProviderPrice(
            provider=self.name,
            provider_product_id=provider_product_id,
            price_cents=cheapest.price_cents,
            currency=cheapest.currency,
            availability="in_stock",
            observed_at=cheapest.observed_at,
            source=f"google_shopping:{cheapest.merchant}",
            confidence=0.6,
            metadata={"merchant": cheapest.merchant, "offer_count": len(priced)},
        )

    async def get_product(self, provider_product_id: str) -> ProviderProduct | None:
        results = await self.search_products(provider_product_id, limit=1)
        return results[0] if results else None

    async def get_price_history(self, provider_product_id: str, *, days: int = 180) -> None:
        return None  # DataForSEO has no history

    # -- HTTP ---------------------------------------------------------------

    async def _shopping_items(self, keyword: str) -> list[Mapping[str, Any]]:
        keyword = keyword.strip()
        if not keyword:
            return []
        if not (self._login and self._password):
            raise ProviderError("DataForSEO provider is not configured")

        token = base64.b64encode(f"{self._login}:{self._password}".encode()).decode("ascii")
        payload = [
            {
                "keyword": keyword,
                "location_code": self._location_code,
                "language_code": self._language_code,
            }
        ]
        response = await asyncio.to_thread(
            self._transport.post_json,
            f"{DATAFORSEO_API_BASE}{_SHOPPING_LIVE_PATH}",
            auth_header=f"Basic {token}",
            payload=payload,
            timeout_seconds=self._timeout_seconds,
        )
        status = response.get("status_code")
        if status != 20000:
            raise ProviderError(f"DataForSEO error {status}: {response.get('status_message')}")

        tasks = response.get("tasks")
        if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], Mapping):
            return []
        task = tasks[0]
        if task.get("status_code") != 20000:
            raise ProviderError(f"DataForSEO task error: {task.get('status_message')}")
        cost = response.get("cost")
        logger.info("dataforseo call", extra={"keyword": keyword, "cost": cost})

        results = task.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], Mapping):
            return []
        items = results[0].get("items")
        return [i for i in items if isinstance(i, Mapping)] if isinstance(items, list) else []


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
