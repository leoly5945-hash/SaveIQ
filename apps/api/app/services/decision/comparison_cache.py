"""Per-product cache of cross-merchant offers (CP7 + DataForSEO).

DataForSEO's Google Shopping data is task-based, so it cannot answer inside a
synchronous price-check. This module is the bridge:

* :func:`resolve_comparison` — called from the price-check path. Returns fresh
  cached offers when we have them; otherwise submits a DataForSEO task (cold
  product) or polls an in-flight one (a task posted by an earlier check), and
  returns ``None`` for this request. Never raises.
* :func:`resolve_merchant_links` — called after matching, for the few offers that
  are actually shown: swaps the Google Shopping link for the store's own product
  page through DataForSEO's Sellers task (also task-based, so a link appears one
  check later).
* :func:`poll_pending_comparisons` — a backstop the alert cron runs so tracked
  products always get their comparison filled within a day even if nobody
  re-checks them.

Stored rows are the *raw* per-merchant offers; CP7 matching runs fresh on every
read (in :mod:`app.services.decision.price_check`) so "cheaper?" stays correct as
the reference price moves.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.comparison import ComparisonStatus, MerchantComparison
from app.providers.base import ProviderOffer
from app.providers.dataforseo import merchant_direct_url
from app.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

COMPARISON_PROVIDER = "dataforseo"

# A ready row is trusted for this long before we re-submit.
_CACHE_TTL = timedelta(hours=24)
# A pending task older than this with no result is declared failed.
_PENDING_TIMEOUT = timedelta(minutes=30)
# Don't poll a task inline until it has had a chance to run.
_MIN_POLL_AGE = timedelta(seconds=20)
# Give up on a task after this many poll attempts.
_MAX_ATTEMPTS = 6
# Re-submit a failed row only after a cool-off.
_FAILED_RETRY_AFTER = timedelta(hours=6)

# Store links are looked up only for offers that are shown, at most this many per
# product per refresh (each lookup is a paid Sellers task).
_MAX_LINK_LOOKUPS = 3
# Row keys that carry a store-link lookup across a refresh of the same listing.
_LINK_KEYS = ("merchant_url", "link_state", "link_task_id", "link_requested_at")

_KEYWORD_MAX_WORDS = 8
_KEYWORD_MAX_CHARS = 90


class _ShoppingTaskProvider(Protocol):
    def is_configured(self) -> bool: ...

    async def submit_offers_task(self, keyword: str) -> str: ...

    async def fetch_offers_task(
        self, task_id: str, *, provider_product_id: str | None = ...
    ) -> list[ProviderOffer] | None: ...


@dataclass
class ComparisonPollStats:
    pending_seen: int = 0
    completed: int = 0
    still_pending: int = 0
    failed: int = 0
    errors: int = 0


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat a stored timestamp as UTC."""

    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def shopping_keyword(title: str, brand: str | None = None) -> str:
    """Turn a marketing-heavy Amazon title into a lean Google Shopping query.

    Amazon titles read like
    ``"Amazon Echo Dot (newest model), Vibrant sounding Alexa speaker, Great …"``
    — everything after the first comma is fluff. Take the head, drop
    parentheticals, cap the length, and make sure the brand leads.
    """

    head = title.split(",", 1)[0]
    head = re.sub(r"\([^)]*\)", " ", head)
    head = re.sub(r"[^A-Za-z0-9+&.\- ]+", " ", head)
    words = [w for w in head.split() if w]
    keyword = " ".join(words[:_KEYWORD_MAX_WORDS]).strip()
    if brand:
        b = brand.strip()
        if b and b.casefold() not in keyword.casefold():
            keyword = f"{b} {keyword}".strip()
    return keyword[:_KEYWORD_MAX_CHARS].strip()


def _id_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _serialize_offers(
    offers: list[ProviderOffer], previous: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Raw rows for the cache. A store link already found for the same listing
    (same merchant and title) in ``previous`` is kept, so a daily refresh does
    not pay for the lookup again."""

    known = {
        (row.get("merchant"), row.get("title")): row
        for row in previous or []
        if row.get("link_state")
    }
    rows: list[dict[str, Any]] = []
    for o in offers:
        if not o.merchant or o.price_cents is None:
            continue
        meta = o.metadata or {}
        row: dict[str, Any] = {
            "merchant": o.merchant,
            "price_cents": o.price_cents,
            "shipping_cents": o.shipping_cents or 0,
            "currency": o.currency,
            "url": o.url,
            "title": meta.get("title"),
            "product_id": _id_str(meta.get("product_id")),
            "data_docid": _id_str(meta.get("data_docid")),
            "gid": _id_str(meta.get("gid")),
        }
        old = known.get((row["merchant"], row["title"]))
        if old is not None:
            row.update({key: old[key] for key in _LINK_KEYS if old.get(key)})
        rows.append(row)
    return rows


def _deserialize_offers(
    rows: list[dict[str, Any]] | None,
    *,
    provider_product_id: str,
    currency: str,
    observed_at: datetime,
) -> list[ProviderOffer]:
    offers: list[ProviderOffer] = []
    for row in rows or []:
        price_cents = row.get("price_cents")
        merchant = row.get("merchant")
        if price_cents is None or not merchant:
            continue
        offers.append(
            ProviderOffer(
                provider=COMPARISON_PROVIDER,
                provider_product_id=provider_product_id,
                merchant=str(merchant),
                price_cents=int(price_cents),
                shipping_cents=int(row.get("shipping_cents") or 0),
                currency=str(row.get("currency") or currency),
                availability="in_stock",
                condition="new",
                # The store's own page once the Sellers lookup found it.
                url=row.get("merchant_url") or row.get("url"),
                observed_at=observed_at,
                metadata={"title": row.get("title")},
            )
        )
    return offers


def _get_row(
    db: Session, *, provider: str, provider_product_id: str, market: str
) -> MerchantComparison | None:
    return db.execute(
        select(MerchantComparison).where(
            MerchantComparison.provider == provider,
            MerchantComparison.provider_product_id == provider_product_id,
            MerchantComparison.market == market,
        )
    ).scalar_one_or_none()


def _provider(registry: ProviderRegistry) -> _ShoppingTaskProvider | None:
    provider = registry.try_get(COMPARISON_PROVIDER)
    if provider is None or not provider.is_configured():
        return None
    if not hasattr(provider, "submit_offers_task") or not hasattr(provider, "fetch_offers_task"):
        return None
    return provider  # type: ignore[return-value]


async def resolve_comparison(
    db: Session,
    registry: ProviderRegistry,
    *,
    provider: str,
    provider_product_id: str,
    market: str,
    title: str,
    brand: str | None,
    currency: str,
    now: datetime | None = None,
) -> list[ProviderOffer] | None:
    """Fresh cached offers for the product, or ``None`` (and prime a task). Never raises."""

    now = now or _now()

    def _fresh_offers(row: MerchantComparison) -> list[ProviderOffer]:
        return _deserialize_offers(
            row.offers_json,
            provider_product_id=provider_product_id,
            currency=row.currency or currency,
            observed_at=now,
        )

    try:
        row = _get_row(
            db, provider=provider, provider_product_id=provider_product_id, market=market
        )
        ready_offers: list[ProviderOffer] | None = None
        if row is not None and row.status == ComparisonStatus.ready.value:
            ready_offers = _fresh_offers(row)
            expires_at = _aware(row.expires_at)
            if expires_at is not None and expires_at > now:
                return ready_offers

        task_provider = _provider(registry)
        if task_provider is None:
            return ready_offers

        keyword = shopping_keyword(title, brand)
        if not keyword:
            return ready_offers

        if row is not None and row.status == ComparisonStatus.pending.value:
            return await _poll_row(db, task_provider, row, now=now)

        needs_refresh = row is None or row.status == ComparisonStatus.ready.value
        if row is not None and row.status == ComparisonStatus.failed.value:
            marker = _aware(row.completed_at) or _aware(row.requested_at) or now
            needs_refresh = now - marker >= _FAILED_RETRY_AFTER
        if needs_refresh:
            await _submit(
                db,
                task_provider,
                row=row,
                provider=provider,
                provider_product_id=provider_product_id,
                market=market,
                keyword=keyword,
                currency=currency,
                now=now,
            )
        # serve stale offers rather than nothing while the refresh runs
        return ready_offers
    except Exception:  # noqa: BLE001 - comparison is best-effort, must not break the check
        logger.warning("comparison cache resolve failed", exc_info=True)
        return None


async def _submit(
    db: Session,
    task_provider: _ShoppingTaskProvider,
    *,
    row: MerchantComparison | None,
    provider: str,
    provider_product_id: str,
    market: str,
    keyword: str,
    currency: str,
    now: datetime,
) -> MerchantComparison:
    """Post a fresh task and (re)set ``row`` to pending. Keeps any prior offers."""

    task_id = await task_provider.submit_offers_task(keyword)
    if row is None:
        row = MerchantComparison(
            provider=provider,
            provider_product_id=provider_product_id,
            market=market,
        )
        db.add(row)
    row.status = ComparisonStatus.pending.value
    row.keyword = keyword
    row.task_id = task_id
    row.currency = currency
    row.requested_at = now
    row.last_polled_at = None
    row.completed_at = None
    row.expires_at = None
    row.attempts = 0
    db.flush()
    return row


async def _poll_row(
    db: Session,
    task_provider: _ShoppingTaskProvider,
    row: MerchantComparison,
    *,
    now: datetime,
) -> list[ProviderOffer] | None:
    if not row.task_id:
        row.status = ComparisonStatus.failed.value
        row.completed_at = now
        db.flush()
        return None
    requested_at = _aware(row.requested_at) or now
    if now - requested_at < _MIN_POLL_AGE:
        return None

    row.last_polled_at = now
    row.attempts = (row.attempts or 0) + 1
    offers = await task_provider.fetch_offers_task(
        row.task_id, provider_product_id=row.provider_product_id
    )
    if offers is None:
        if now - requested_at > _PENDING_TIMEOUT or row.attempts >= _MAX_ATTEMPTS:
            row.status = ComparisonStatus.failed.value
            row.completed_at = now
        db.flush()
        return None

    row.status = ComparisonStatus.ready.value
    row.offers_json = _serialize_offers(offers, row.offers_json)
    row.completed_at = now
    row.expires_at = now + _CACHE_TTL
    db.flush()
    return _deserialize_offers(
        row.offers_json,
        provider_product_id=row.provider_product_id,
        currency=row.currency,
        observed_at=now,
    )


def _same_seller(a: str, b: str) -> bool:
    left, right = (re.sub(r"[^a-z0-9]+", "", text.casefold()) for text in (a, b))
    return bool(left and right) and (left in right or right in left)


async def resolve_merchant_links(
    db: Session,
    registry: ProviderRegistry,
    *,
    provider: str,
    provider_product_id: str,
    market: str,
    shown_urls: list[str],
    now: datetime | None = None,
) -> dict[str, str]:
    """Store links for the shown offers: ``{google shopping url: store url}``.

    ``shown_urls`` are the links of the offers the shopper is about to see. For
    each one still pointing at Google, this submits a Sellers task (first time)
    or reads its result (a later check). Never raises.
    """

    now = now or _now()
    found: dict[str, str] = {}
    try:
        task_provider = registry.try_get(COMPARISON_PROVIDER)
        if (
            task_provider is None
            or not task_provider.is_configured()
            or not hasattr(task_provider, "submit_sellers_task")
            or not hasattr(task_provider, "fetch_sellers_task")
        ):
            return found
        row = _get_row(
            db, provider=provider, provider_product_id=provider_product_id, market=market
        )
        if row is None or not row.offers_json:
            return found
        offers = [dict(offer) for offer in row.offers_json]
        lookups = sum(1 for offer in offers if offer.get("link_state"))
        changed = False
        for offer in offers:
            if offer.get("url") not in shown_urls:
                continue
            state = offer.get("link_state")
            if state is None:
                ids = {key: offer.get(key) for key in ("product_id", "data_docid", "gid")}
                if not any(ids.values()) or lookups >= _MAX_LINK_LOOKUPS:
                    continue
                lookups += 1
                changed = True
                try:
                    offer["link_task_id"] = await task_provider.submit_sellers_task(**ids)
                except Exception:  # noqa: BLE001 - one failed lookup must not stop the rest
                    logger.warning("sellers task submit failed", exc_info=True)
                    offer["link_state"] = "failed"
                    continue
                offer["link_state"] = "pending"
                offer["link_requested_at"] = now.isoformat()
            elif state == "pending":
                requested_at = datetime.fromisoformat(offer["link_requested_at"])
                if now - requested_at < _MIN_POLL_AGE:
                    continue
                try:
                    shops = await task_provider.fetch_sellers_task(offer["link_task_id"])
                except Exception:  # noqa: BLE001
                    logger.warning("sellers task fetch failed", exc_info=True)
                    offer["link_state"] = "failed"
                    changed = True
                    continue
                if shops is None:
                    if now - requested_at > _PENDING_TIMEOUT:
                        offer["link_state"] = "failed"
                        changed = True
                    continue
                changed = True
                offer["link_state"] = "no_match"
                for shop in shops:
                    if not _same_seller(str(shop.get("seller_name") or ""), offer["merchant"]):
                        continue
                    direct = merchant_direct_url(shop.get("url"), shop.get("domain"))
                    if direct:
                        offer["merchant_url"] = direct
                        offer["link_state"] = "ready"
                        found[offer["url"]] = direct
                        break
        if changed:
            row.offers_json = offers
            db.flush()
    except Exception:  # noqa: BLE001 - store links are best-effort, must not break the check
        logger.warning("merchant link resolve failed", exc_info=True)
    return found


async def poll_pending_comparisons(
    db: Session,
    registry: ProviderRegistry,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> ComparisonPollStats:
    """Advance every in-flight comparison task. Safe to call from a cron."""

    now = now or _now()
    stats = ComparisonPollStats()
    task_provider = _provider(registry)
    if task_provider is None:
        return stats

    rows = list(
        db.execute(
            select(MerchantComparison)
            .where(MerchantComparison.status == ComparisonStatus.pending.value)
            .order_by(MerchantComparison.requested_at)
            .limit(limit)
        ).scalars()
    )
    for row in rows:
        stats.pending_seen += 1
        try:
            # the cron has no "too young to poll" guard — tasks here are seconds old
            row.last_polled_at = now
            row.attempts = (row.attempts or 0) + 1
            offers = (
                await task_provider.fetch_offers_task(
                    row.task_id, provider_product_id=row.provider_product_id
                )
                if row.task_id
                else None
            )
            if offers is None:
                requested_at = _aware(row.requested_at) or now
                if (
                    not row.task_id
                    or now - requested_at > _PENDING_TIMEOUT
                    or row.attempts >= _MAX_ATTEMPTS
                ):
                    row.status = ComparisonStatus.failed.value
                    row.completed_at = now
                    stats.failed += 1
                else:
                    stats.still_pending += 1
                continue
            row.status = ComparisonStatus.ready.value
            row.offers_json = _serialize_offers(offers, row.offers_json)
            row.completed_at = now
            row.expires_at = now + _CACHE_TTL
            stats.completed += 1
        except Exception:  # noqa: BLE001 - one bad task must not stop the sweep
            stats.errors += 1
            logger.warning(
                "comparison poll failed",
                extra={"product_id": row.provider_product_id},
                exc_info=True,
            )
    db.flush()
    return stats
