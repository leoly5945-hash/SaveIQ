"""DataForSEO Google Shopping provider — multi-merchant price comparison.

Given a product *title* (we get it from Keepa when the shopper pastes an Amazon
link), DataForSEO's Google Shopping endpoint returns the same product's offers
across other retailers (Walmart CA, Best Buy CA, Newegg, …). No price history —
this provider answers ``search`` / ``get_offers`` / ``get_price`` only.

DataForSEO's Google Shopping is **task-based**: there is no live endpoint. You
``task_post`` a keyword (charged), wait, then ``task_get`` the result. The
synchronous Protocol methods (``get_offers`` etc.) submit a task and poll it for
a short budget — fine for admin/debug use. The price-check path does **not** use
them; it drives ``submit_offers_task`` / ``fetch_offers_task`` through the
:mod:`app.services.decision.comparison_cache` so the shopper's request never
blocks on a DataForSEO task.
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
_SHOPPING_TASK_POST_PATH = "/v3/merchant/google/products/task_post"
_SHOPPING_TASK_GET_PATH = "/v3/merchant/google/products/task_get/advanced"

# task-level status codes that mean "not done yet, poll again later".
_TASK_PENDING_CODES = frozenset({40601, 40602, 40100})
# how long / how hard the synchronous helpers poll a freshly posted task.
_SYNC_POLL_ATTEMPTS = 6
_SYNC_POLL_DELAY_SECONDS = 2.0

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

    def get_json(
        self,
        url: str,
        *,
        auth_header: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """GET with Basic auth and return the decoded JSON object."""


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


def _decode_body(raw: bytes, encoding: str | None) -> Mapping[str, Any]:
    try:
        decoded = json.loads(_decompress(raw, encoding).decode("utf-8"))
    except (OSError, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("DataForSEO returned an undecodable body") from exc
    if not isinstance(decoded, Mapping):
        raise ProviderError("DataForSEO returned a non-object response")
    return decoded


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
        return self._send(request, timeout_seconds)

    def get_json(
        self,
        url: str,
        *,
        auth_header: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": auth_header,
                "Accept-Encoding": "gzip",
            },
        )
        return self._send(request, timeout_seconds)

    @staticmethod
    def _send(request: urllib.request.Request, timeout_seconds: float) -> Mapping[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                encoding = response.headers.get("Content-Encoding")
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"DataForSEO request failed (HTTP {exc.code})") from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise ProviderError("DataForSEO request failed (transport error)") from exc
        return _decode_body(raw, encoding)


def _as_price_cents(value: Any) -> int | None:
    try:
        cents = round(float(value) * 100)
    except (TypeError, ValueError):
        return None
    return cents if cents > 0 else None


def _shipping_cents(item: Mapping[str, Any]) -> int:
    """Shipping from either the live shape (``price_shipping``) or task_get's
    ``delivery_info.delivery_price``."""

    direct = _as_price_cents(item.get("price_shipping"))
    if direct is not None:
        return direct
    delivery = item.get("delivery_info")
    if isinstance(delivery, Mapping):
        price = delivery.get("delivery_price")
        if isinstance(price, Mapping):
            return _as_price_cents(price.get("price")) or 0
    return 0


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
        offers = await self.get_offers(query)
        out: list[ProviderProduct] = []
        for offer in offers[: max(limit, 0)]:
            title = (offer.metadata or {}).get("title")
            if not title:
                continue
            out.append(
                ProviderProduct(
                    provider=self.name,
                    provider_product_id=str((offer.metadata or {}).get("product_id") or query),
                    title=str(title),
                    market=self.market,
                    currency=self.currency,
                    product_url=offer.url,
                    metadata={
                        "seller": offer.merchant,
                        "price_cents": offer.price_cents,
                        "source": "google_shopping",
                    },
                )
            )
        return out

    async def get_offers(self, provider_product_id: str) -> list[ProviderOffer]:
        """Submit a task for the keyword and poll it for a short budget.

        Used by the admin/debug surface only. The price-check path uses
        ``submit_offers_task`` / ``fetch_offers_task`` via the comparison cache so
        it never blocks on a task.
        """

        keyword = provider_product_id.strip()
        if not keyword:
            return []
        task_id = await self.submit_offers_task(keyword)
        for attempt in range(_SYNC_POLL_ATTEMPTS):
            if attempt:
                await asyncio.sleep(_SYNC_POLL_DELAY_SECONDS)
            offers = await self.fetch_offers_task(task_id, provider_product_id=provider_product_id)
            if offers is not None:
                return offers
        return []

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

    # -- task flow (used by the comparison cache) -----------------------------

    async def submit_offers_task(self, keyword: str) -> str:
        """POST a Google Shopping task for ``keyword`` and return its task id."""

        keyword = keyword.strip()
        if not keyword:
            raise ProviderError("DataForSEO task needs a non-empty keyword")
        payload = [
            {
                "keyword": keyword,
                "location_code": self._location_code,
                "language_code": self._language_code,
                "priority": 2,
            }
        ]
        response = await asyncio.to_thread(
            self._transport.post_json,
            f"{DATAFORSEO_API_BASE}{_SHOPPING_TASK_POST_PATH}",
            auth_header=self._auth_header(),
            payload=payload,
            timeout_seconds=self._timeout_seconds,
        )
        task = self._first_task(response)
        task_code = task.get("status_code")
        if task_code not in (20000, 20100):
            raise ProviderError(f"DataForSEO task_post error: {task.get('status_message')}")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ProviderError("DataForSEO task_post returned no task id")
        logger.info(
            "dataforseo task_post",
            extra={"keyword": keyword, "task_id": task_id, "cost": response.get("cost")},
        )
        return task_id

    async def fetch_offers_task(
        self, task_id: str, *, provider_product_id: str | None = None
    ) -> list[ProviderOffer] | None:
        """GET a posted task. ``None`` while it is still queued; a list once done."""

        response = await asyncio.to_thread(
            self._transport.get_json,
            f"{DATAFORSEO_API_BASE}{_SHOPPING_TASK_GET_PATH}/{task_id}",
            auth_header=self._auth_header(),
            timeout_seconds=self._timeout_seconds,
        )
        task = self._first_task(response)
        task_code = task.get("status_code")
        if task_code in _TASK_PENDING_CODES:
            return None
        if task_code != 20000:
            raise ProviderError(f"DataForSEO task_get error: {task.get('status_message')}")
        results = task.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], Mapping):
            return []
        items = results[0].get("items")
        rows = [i for i in items if isinstance(i, Mapping)] if isinstance(items, list) else []
        return self._parse_items(rows, provider_product_id or task_id)

    # -- helpers ------------------------------------------------------------

    def _auth_header(self) -> str:
        if not (self._login and self._password):
            raise ProviderError("DataForSEO provider is not configured")
        token = base64.b64encode(f"{self._login}:{self._password}".encode()).decode("ascii")
        return f"Basic {token}"

    @staticmethod
    def _first_task(response: Mapping[str, Any]) -> Mapping[str, Any]:
        status = response.get("status_code")
        if status != 20000:
            raise ProviderError(f"DataForSEO error {status}: {response.get('status_message')}")
        tasks = response.get("tasks")
        if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], Mapping):
            raise ProviderError("DataForSEO returned no task")
        return tasks[0]

    def _parse_items(
        self, items: Sequence[Mapping[str, Any]], provider_product_id: str
    ) -> list[ProviderOffer]:
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
                    shipping_cents=_shipping_cents(item),
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


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
