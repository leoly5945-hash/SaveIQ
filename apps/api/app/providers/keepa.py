"""Keepa product data provider (CP4).

Keepa (https://keepa.com) sells Amazon catalogue + price-history data as a
pay-as-you-go API. One ``/product`` call returns the current Amazon / marketplace
/ buy-box price, the live third-party offers, and a multi-year price history — so
this adapter can answer every :class:`ProductDataProvider` question, including
``price_history``, on the day it is switched on (no accumulation wait).

Scope: Amazon only, one marketplace per instance (``domain``; ``6`` = Amazon.ca).
Multi-merchant comparison comes from a second provider (e.g. a Google Shopping
vendor) behind the same protocol.

Prices from Keepa are integer cents of the domain currency; ``-1`` means "no data
at that point". Timestamps are "Keepa minutes" — minutes since 2011-01-01 UTC.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.providers.base import (
    ProviderCapability,
    ProviderError,
    ProviderOffer,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderPricePoint,
    ProviderProduct,
    ProviderProductNotFound,
)

logger = logging.getLogger(__name__)

KEEPA_API_BASE = "https://api.keepa.com"

# Minutes between the Unix epoch and Keepa's 2011-01-01 epoch.
_KEEPA_EPOCH_OFFSET_MINUTES = 21_564_000

# Amazon locale per Keepa domain id.
_DOMAIN_LOCALE: dict[int, tuple[str, str, str]] = {
    # domain: (market, currency, storefront host)
    1: ("US", "USD", "www.amazon.com"),
    2: ("GB", "GBP", "www.amazon.co.uk"),
    3: ("DE", "EUR", "www.amazon.de"),
    4: ("FR", "EUR", "www.amazon.fr"),
    5: ("JP", "JPY", "www.amazon.co.jp"),
    6: ("CA", "CAD", "www.amazon.ca"),
    8: ("IT", "EUR", "www.amazon.it"),
    9: ("ES", "EUR", "www.amazon.es"),
    10: ("IN", "INR", "www.amazon.in"),
    11: ("MX", "MXN", "www.amazon.com.mx"),
}

# Keepa `csv` / `stats` array indices we read.
_CSV_AMAZON = 0
_CSV_NEW = 1
_CSV_USED = 2
_CSV_LIST_PRICE = 4
_CSV_BUY_BOX = 18
# Indices whose csv rows are [time, price, shipping] triplets rather than pairs.
_TRIPLET_INDICES = frozenset({_CSV_BUY_BOX})

# stats.current index -> (source label, price-series "kind") in selection order.
_PRICE_PRIORITY: tuple[tuple[int, str, str], ...] = (
    (_CSV_BUY_BOX, "keepa:buy_box", "buy_box"),
    (_CSV_AMAZON, "keepa:amazon", "amazon"),
    (_CSV_NEW, "keepa:new", "new"),
)

_CONDITION_BY_CODE: dict[int, str] = {
    0: "unknown",
    1: "new",
    2: "used",
    3: "used",
    4: "used",
    5: "used",
    6: "refurbished",
    7: "collectible",
    8: "collectible",
    9: "collectible",
    10: "collectible",
    11: "new",
}


class KeepaHttpTransport(Protocol):
    """Minimal GET-JSON transport so tests can supply canned responses."""

    def get_json(self, url: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        """Fetch ``url`` and return the decoded JSON object."""


def _decompress_body(raw: bytes, content_encoding: str | None) -> bytes:
    """Keepa always gzip-compresses responses; some proxies re-encode. Be lenient."""

    encoding = (content_encoding or "").lower().strip()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


class UrllibKeepaHttpTransport:
    def get_json(self, url: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                content_encoding = response.headers.get("Content-Encoding")
        except urllib.error.HTTPError as exc:  # 4xx / 5xx
            detail = _safe_http_error_detail(exc)
            raise ProviderError(f"Keepa request failed (HTTP {exc.code}): {detail}") from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise ProviderError("Keepa request failed (transport error)") from exc
        try:
            raw_body = _decompress_body(raw, content_encoding).decode("utf-8")
        except (OSError, zlib.error, UnicodeDecodeError) as exc:
            raise ProviderError("Keepa returned an undecodable body") from exc
        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ProviderError("Keepa returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ProviderError("Keepa returned a non-object response")
        return decoded


def _safe_http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
        body = _decompress_body(raw, exc.headers.get("Content-Encoding")).decode("utf-8")
    except Exception:  # noqa: BLE001 - diagnostics only
        return exc.reason or "unknown error"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body[:200] or (exc.reason or "unknown error")
    if isinstance(parsed, Mapping):
        error = parsed.get("error")
        if isinstance(error, Mapping) and error.get("message"):
            return str(error["message"])
    return body[:200]


def _keepa_minutes_to_datetime(minutes: int) -> datetime | None:
    unix_seconds = (minutes + _KEEPA_EPOCH_OFFSET_MINUTES) * 60
    try:
        return datetime.fromtimestamp(unix_seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decode_series(row: Sequence[Any] | None, *, triplet: bool) -> list[tuple[datetime, int]]:
    """Decode one Keepa csv row into ``(observed_at, price_cents)`` pairs.

    Keepa csv rows are flat ``[time, price, time, price, ...]`` (or
    ``[time, price, shipping, ...]`` triplets). A ``-1`` price means "no data" and
    is dropped; any malformed slot is skipped rather than raising.
    """

    if not row:
        return []
    step = 3 if triplet else 2
    out: list[tuple[datetime, int]] = []
    for i in range(0, len(row) - step + 1, step):
        minutes = _as_int(row[i])
        price = _as_int(row[i + 1])
        if minutes is None or price is None or price < 0:
            continue
        if triplet:
            shipping = _as_int(row[i + 2])
            if shipping and shipping > 0:
                price += shipping
        observed_at = _keepa_minutes_to_datetime(minutes)
        if observed_at is None:
            continue
        out.append((observed_at, price))
    return out


def _densify_daily(
    change_points: Sequence[tuple[datetime, int]],
    *,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, int]]:
    """Forward-fill Keepa's step function into one point per day in ``[start, end]``.

    Keepa only records a point when the price *changes*; between changes the price
    is the value at the last change. So a product whose price has not moved for
    months has no csv points in a recent window even though its price is known —
    this fills that gap by carrying the last known value forward.
    """

    if not change_points:
        return []
    ordered = sorted(change_points, key=lambda cp: cp[0])
    out: list[tuple[datetime, int]] = []
    idx = 0
    current: int | None = None
    day = start
    one_day = timedelta(days=1)
    while day <= end:
        while idx < len(ordered) and ordered[idx][0] <= day:
            current = ordered[idx][1]
            idx += 1
        if current is not None:
            out.append((day, current))
        day += one_day
    while idx < len(ordered):  # a change between the last sample and `end`
        current = ordered[idx][1]
        idx += 1
    if current is not None and (not out or out[-1][0] < end):
        out.append((end, current))
    return out


def _stat_value(stats: Mapping[str, Any] | None, key: str, index: int) -> int | None:
    if not stats:
        return None
    values = stats.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return None
    if index >= len(values):
        return None
    try:
        value = int(values[index])
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _stat_pair(stats: Mapping[str, Any] | None, key: str, index: int) -> int | None:
    """Read a ``stats.min`` / ``stats.max`` entry, which is ``[time, price]``."""

    if not stats:
        return None
    values = stats.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return None
    if index >= len(values):
        return None
    entry = values[index]
    if not isinstance(entry, Sequence) or len(entry) < 2:
        return None
    try:
        price = int(entry[1])
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


class KeepaProvider:
    """:class:`ProductDataProvider` backed by the Keepa API."""

    name = "keepa"
    capabilities = frozenset(
        {
            ProviderCapability.search,
            ProviderCapability.get_product,
            ProviderCapability.get_offers,
            ProviderCapability.get_price,
            ProviderCapability.price_history,
        }
    )

    def __init__(
        self,
        *,
        api_key: str | None,
        domain: int = 6,
        timeout_seconds: float = 20.0,
        transport: KeepaHttpTransport | None = None,
        now: datetime | None = None,
    ) -> None:
        if domain not in _DOMAIN_LOCALE:
            raise ValueError(f"unsupported Keepa domain id: {domain}")
        self._api_key = api_key
        self._domain = domain
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrllibKeepaHttpTransport()
        self._now = now
        self.market, self.currency, self._host = _DOMAIN_LOCALE[domain]
        # Short-TTL cache of the raw /product payload, keyed by ASIN. One
        # price-check makes 3-4 provider calls for the same ASIN; without this
        # that is 3-4 Keepa /product hits (~6 tokens each with offers). The
        # richest payload seen wins; entries expire fast so a repeat check still
        # gets a fresh price.
        self._product_cache: dict[str, tuple[float, Mapping[str, Any]]] = {}

    _PRODUCT_CACHE_TTL_SECONDS = 60.0

    # -- protocol ---------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search_products(self, query: str, *, limit: int = 10) -> list[ProviderProduct]:
        term = query.strip()
        if not term:
            return []
        payload = await self._request(
            "search",
            {"type": "product", "term": term},
        )
        products = payload.get("products")
        if not isinstance(products, list) or not products:
            # Keepa can return only an `asinList` for some queries; we do not spend
            # extra tokens auto-hydrating it here — callers ask for get_product.
            return []
        out: list[ProviderProduct] = []
        for raw in products[: max(limit, 0)]:
            if isinstance(raw, Mapping):
                out.append(self._parse_product(raw))
        return out

    async def get_product(self, provider_product_id: str) -> ProviderProduct | None:
        raw = await self._fetch_product(provider_product_id, offers=False, stats_days=0)
        if raw is None:
            return None
        return self._parse_product(raw)

    async def describe(self, provider_product_id: str) -> dict[str, Any]:
        """Diagnostic: what did Keepa actually return for this id? (admin use)

        Trims the huge ``csv`` arrays down to lengths so the payload is readable.
        """

        params: dict[str, Any] = {
            "asin": provider_product_id.strip().upper(),
            "history": 1,
            "stats": 90,
            "buybox": 1,
        }
        payload = await self._request("product", params)
        products = payload.get("products")
        if not isinstance(products, list) or not products or not isinstance(products[0], Mapping):
            return {"found": False, "keepa_keys": sorted(payload.keys())}
        raw = products[0]
        raw_stats = raw.get("stats")
        stats = raw_stats if isinstance(raw_stats, Mapping) else None
        raw_csv = raw.get("csv")
        csv: list[Any] = raw_csv if isinstance(raw_csv, list) else []
        return {
            "found": True,
            "asin": raw.get("asin"),
            "title": raw.get("title"),
            "keepa_keys": sorted(raw.keys()),
            "csv_index_lengths": {
                i: (len(row) if isinstance(row, list) else None) for i, row in enumerate(csv)
            },
            "stats_current": stats.get("current") if stats else None,
            "stats_keys": sorted(stats.keys()) if stats else None,
            "tokens_left": payload.get("tokensLeft"),
        }

    async def get_offers(self, provider_product_id: str) -> list[ProviderOffer]:
        raw = await self._fetch_product(provider_product_id, offers=True, stats_days=90)
        if raw is None:
            return []
        return self._parse_offers(provider_product_id, raw)

    async def get_price(self, provider_product_id: str) -> ProviderPrice | None:
        raw = await self._fetch_product(provider_product_id, offers=False, stats_days=90)
        if raw is None:
            return None
        return self._parse_price(provider_product_id, raw)

    async def get_price_history(
        self,
        provider_product_id: str,
        *,
        days: int = 180,
    ) -> ProviderPriceHistory | None:
        raw = await self._fetch_product(provider_product_id, offers=False, stats_days=days)
        if raw is None:
            return None
        return self._parse_history(provider_product_id, raw, days=days)

    # -- HTTP -----------------------------------------------------------------

    async def _request(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self._api_key:
            raise ProviderError("Keepa provider is not configured (missing KEEPA_API_KEY)")
        query = {"key": self._api_key, "domain": self._domain, **params}
        url = f"{KEEPA_API_BASE}/{endpoint}?{urllib.parse.urlencode(query)}"
        payload = await asyncio.to_thread(
            self._transport.get_json,
            url,
            timeout_seconds=self._timeout_seconds,
        )
        error = payload.get("error")
        if error:
            message = error.get("message") if isinstance(error, Mapping) else str(error)
            raise ProviderError(f"Keepa error: {message}")
        tokens_left = payload.get("tokensLeft")
        if isinstance(tokens_left, int):
            logger.info(
                "keepa call",
                extra={
                    "endpoint": endpoint,
                    "tokens_left": tokens_left,
                    "tokens_consumed": payload.get("tokensConsumed"),
                },
            )
            if tokens_left < 0:
                logger.warning("keepa token balance exhausted", extra={"tokens_left": tokens_left})
        return payload

    @staticmethod
    def _covers(product: Mapping[str, Any], *, offers: bool, stats_days: int) -> bool:
        if offers and not isinstance(product.get("offers"), list):
            return False
        if stats_days > 0 and not isinstance(product.get("stats"), Mapping):
            return False
        return True

    async def _fetch_product(
        self,
        asin: str,
        *,
        offers: bool,
        stats_days: int,
    ) -> Mapping[str, Any] | None:
        asin = asin.strip().upper()
        if not asin:
            raise ProviderProductNotFound("empty ASIN")

        cached = self._product_cache.get(asin)
        if cached is not None:
            ts, product = cached
            if time.monotonic() - ts < self._PRODUCT_CACHE_TTL_SECONDS and self._covers(
                product, offers=offers, stats_days=stats_days
            ):
                return product
            self._product_cache.pop(asin, None)

        params: dict[str, Any] = {"asin": asin, "history": 1}
        if stats_days > 0:
            params["stats"] = stats_days
            params["buybox"] = 1
        if offers:
            params["offers"] = 20
            params["buybox"] = 1
        payload = await self._request("product", params)
        products = payload.get("products")
        if not isinstance(products, list) or not products:
            return None
        first = products[0]
        if not isinstance(first, Mapping):
            return None
        # Keepa returns a stub object (title None, no csv) for an unknown ASIN.
        if first.get("title") in (None, "") and not first.get("csv"):
            return None
        self._product_cache[asin] = (time.monotonic(), first)
        return first

    # -- parsing ------------------------------------------------------------

    def _now_dt(self) -> datetime:
        return self._now or datetime.now(tz=UTC)

    def _parse_product(self, raw: Mapping[str, Any]) -> ProviderProduct:
        asin = str(raw.get("asin", "")).strip().upper()
        identifiers: dict[str, str] = {}
        if asin:
            identifiers["asin"] = asin
        for key, id_type in (("upcList", "upc"), ("eanList", "ean")):
            values = raw.get(key)
            if isinstance(values, list) and values:
                identifiers[id_type] = str(values[0]).strip().upper()

        return ProviderProduct(
            provider=self.name,
            provider_product_id=asin or str(raw.get("asin", "")),
            title=str(raw.get("title") or "").strip() or f"ASIN {asin}",
            brand=_clean_str(raw.get("brand")) or _clean_str(raw.get("manufacturer")),
            category=_category_name(raw),
            image_url=_first_image_url(raw.get("imagesCSV")),
            product_url=f"https://{self._host}/dp/{asin}" if asin else None,
            market=self.market,
            currency=self.currency,
            identifiers=identifiers,
            metadata={
                "keepa_domain": self._domain,
                "product_group": _clean_str(raw.get("productGroup")),
            },
        )

    def _current_stats(self, raw: Mapping[str, Any]) -> Mapping[str, Any] | None:
        stats = raw.get("stats")
        return stats if isinstance(stats, Mapping) else None

    def _fallback_current_from_csv(self, raw: Mapping[str, Any], index: int) -> int | None:
        csv = raw.get("csv")
        if not isinstance(csv, list) or index >= len(csv):
            return None
        series = _decode_series(csv[index], triplet=index in _TRIPLET_INDICES)
        return series[-1][1] if series else None

    def _parse_price(self, asin: str, raw: Mapping[str, Any]) -> ProviderPrice | None:
        stats = self._current_stats(raw)
        chosen_cents: int | None = None
        source = "keepa:unknown"
        for index, label, _kind in _PRICE_PRIORITY:
            value = _stat_value(stats, "current", index)
            if value is None:
                value = self._fallback_current_from_csv(raw, index)
            if value is not None:
                chosen_cents = value
                source = label
                break
        if chosen_cents is None:
            return None

        list_price = _stat_value(stats, "current", _CSV_LIST_PRICE)
        availability = "in_stock" if source != "keepa:unknown" else "unknown"
        return ProviderPrice(
            provider=self.name,
            provider_product_id=asin.strip().upper(),
            price_cents=chosen_cents,
            list_price_cents=list_price,
            currency=self.currency,
            availability=availability,
            observed_at=self._now_dt(),
            source=source,
            confidence=1.0,
            metadata={
                "avg30_cents": _stat_value(stats, "avg30", _CSV_AMAZON)
                or _stat_value(stats, "avg30", _CSV_NEW),
                "avg90_cents": _stat_value(stats, "avg90", _CSV_AMAZON)
                or _stat_value(stats, "avg90", _CSV_NEW),
            },
        )

    def _parse_offers(self, asin: str, raw: Mapping[str, Any]) -> list[ProviderOffer]:
        asin = asin.strip().upper()
        observed = self._now_dt()
        offers_raw = raw.get("offers")
        buy_box_seller = None
        stats = self._current_stats(raw)
        if stats:
            buy_box_seller = stats.get("buyBoxSellerId")

        parsed: list[ProviderOffer] = []
        if isinstance(offers_raw, list):
            for entry in offers_raw:
                if not isinstance(entry, Mapping):
                    continue
                offer = self._parse_single_offer(asin, entry, observed, buy_box_seller)
                if offer is not None:
                    parsed.append(offer)

        if parsed:
            return parsed

        # No live offer array (offers cost extra tokens / none in stock): synthesise
        # one from the current effective price so callers always get something usable.
        price = self._parse_price(asin, raw)
        if price is None or price.price_cents is None:
            return []
        return [
            ProviderOffer(
                provider=self.name,
                provider_product_id=asin,
                merchant=self._host.replace("www.", ""),
                price_cents=price.price_cents,
                shipping_cents=0,
                currency=self.currency,
                availability=price.availability,
                condition="new",
                is_buy_box=price.source == "keepa:buy_box",
                url=f"https://{self._host}/dp/{asin}",
                observed_at=observed,
                metadata={"synthesised_from": price.source},
            )
        ]

    def _parse_single_offer(
        self,
        asin: str,
        entry: Mapping[str, Any],
        observed: datetime,
        buy_box_seller: Any,
    ) -> ProviderOffer | None:
        offer_csv = entry.get("offerCSV")
        price_cents: int | None = None
        shipping_cents: int | None = None
        if isinstance(offer_csv, list) and len(offer_csv) >= 3:
            # Triplets [time, price, shipping]; the last triplet is current.
            price_cents = _as_int(offer_csv[-2])
            shipping_cents = _as_int(offer_csv[-1])
            if price_cents is not None and price_cents < 0:
                price_cents = None
            if shipping_cents is not None and shipping_cents < 0:
                shipping_cents = None
        condition_code = _as_int(entry.get("condition")) or 0
        condition = _CONDITION_BY_CODE.get(condition_code, "unknown")
        seller_id = entry.get("sellerId")
        is_amazon = bool(entry.get("isAmazon"))
        storefront = self._host.replace("www.", "")
        merchant = storefront if is_amazon else f"{storefront} (3rd party)"
        return ProviderOffer(
            provider=self.name,
            provider_product_id=asin,
            merchant=merchant,
            price_cents=price_cents,
            shipping_cents=shipping_cents,
            currency=self.currency,
            availability="in_stock" if price_cents is not None else "out_of_stock",
            condition=condition,
            is_buy_box=bool(seller_id is not None and seller_id == buy_box_seller),
            url=f"https://{self._host}/dp/{asin}",
            observed_at=observed,
            metadata={
                "seller_id": seller_id,
                "is_fba": bool(entry.get("isFBA")),
                "is_prime": bool(entry.get("isPrime")),
                "is_amazon": is_amazon,
            },
        )

    def _parse_history(
        self,
        asin: str,
        raw: Mapping[str, Any],
        *,
        days: int,
    ) -> ProviderPriceHistory:
        asin = asin.strip().upper()
        raw_csv = raw.get("csv")
        csv: list[Any] = raw_csv if isinstance(raw_csv, list) else []
        end = self._now_dt()
        start = end - timedelta(days=max(days, 1))

        # Decode the full change-point history for each candidate base series and
        # pick the deepest — Keepa's AMAZON series is usually richest, but a
        # marketplace-only item has more depth on NEW.
        candidates: dict[str, list[tuple[datetime, int]]] = {}
        for index, kind in (
            (_CSV_AMAZON, "amazon"),
            (_CSV_NEW, "new"),
            (_CSV_BUY_BOX, "buy_box"),
        ):
            if index < len(csv):
                series = _decode_series(csv[index], triplet=index in _TRIPLET_INDICES)
                if series:
                    candidates[kind] = series

        base_kind = max(candidates, key=lambda k: len(candidates[k]), default="")
        base = candidates.get(base_kind, [])
        changes_in_window = sum(1 for ts, _ in base if ts >= start)

        points = [
            ProviderPricePoint(observed_at=d, price_cents=p, kind=base_kind or "unknown")
            for d, p in _densify_daily(base, start=start, end=end)
        ]

        stats = self._current_stats(raw)
        return ProviderPriceHistory(
            provider=self.name,
            provider_product_id=asin,
            currency=self.currency,
            points=points,
            covers_from=points[0].observed_at if points else None,
            covers_to=points[-1].observed_at if points else None,
            metadata={
                "requested_days": days,
                "base_kind": base_kind or None,
                # Real price changes inside the window (vs. the densified daily
                # points) and over the product's whole tracked life.
                "source_observations": changes_in_window,
                "lifetime_observations": len(base),
                "keepa_stats": {
                    "avg30_cents": _stat_value(stats, "avg30", _CSV_AMAZON)
                    or _stat_value(stats, "avg30", _CSV_NEW),
                    "avg90_cents": _stat_value(stats, "avg90", _CSV_AMAZON)
                    or _stat_value(stats, "avg90", _CSV_NEW),
                    "avg180_cents": _stat_value(stats, "avg180", _CSV_AMAZON)
                    or _stat_value(stats, "avg180", _CSV_NEW),
                    "min_cents": _stat_pair(stats, "min", _CSV_AMAZON)
                    or _stat_pair(stats, "min", _CSV_NEW),
                    "max_cents": _stat_pair(stats, "max", _CSV_AMAZON)
                    or _stat_pair(stats, "max", _CSV_NEW),
                    "is_lowest_90d": _stat_value(stats, "isLowest90", _CSV_AMAZON),
                },
            },
        )


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _category_name(raw: Mapping[str, Any]) -> str | None:
    tree = raw.get("categoryTree")
    if isinstance(tree, list) and tree:
        last = tree[-1]
        if isinstance(last, Mapping) and last.get("name"):
            return str(last["name"]).strip()
    return _clean_str(raw.get("productGroup"))


def _first_image_url(images_csv: Any) -> str | None:
    if not isinstance(images_csv, str) or not images_csv.strip():
        return None
    first = images_csv.split(",")[0].strip()
    if not first:
        return None
    return f"https://images-na.ssl-images-amazon.com/images/I/{first}"
