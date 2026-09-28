"""Read model for the "Featured deals" surfaces.

These are the hand-picked real products ingested by
:class:`app.services.affiliate.curated_provider.CuratedAmazonProvider`
(``provider_source == "amazon_ca"``). We surface them as a small, honest set:
the price is a point-in-time snapshot labelled with the date it was checked,
and there is no "was" price or discount claim.

Beyond the homepage strip, each deal gets its own indexable page
(``/deal/<slug>``) and every category gets a listing page
(``/category/<slug>``), so the site is real, browsable content rather than a
bare product grid.

The daily price poll also re-checks every curated ASIN against Keepa (see
:func:`curated_amazon_products` and ``run_alert_cycle``), so each deal can carry
its latest *recorded* price and 90-day average. :func:`list_price_drops` is the
"below its 90-day average today" read-out built from those real observations —
no invented "was" price, only what Keepa's history shows.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalProduct,
    Category,
    Merchant,
    MerchantListing,
    Offer,
    RecordStatus,
)
from app.models.tracking import PriceObservation, TrackedProduct
from app.services.decision.deal_score import Verdict

CURATED_PROVIDER_SOURCE = "amazon_ca"
# The daily poll records curated products under the Keepa provider, Canada.
TRACKING_PROVIDER = "keepa"
TRACKING_MARKET = "CA"

# A "price drop" is a latest recorded price at least this far under the
# product's own 90-day average, recorded recently enough to call it "today",
# AND scored BUY by the decision engine — which requires the price to be
# within 5% of its 90-day low. The low guard matters: Keepa's average can be
# pulled up by a stretch of high prices, so "% below average" alone can
# overstate a drop that is nowhere near the product's usual low.
PRICE_DROP_MIN_PCT = 5
PRICE_DROP_VERDICT = Verdict.buy.value
PRICE_DROP_MAX_AGE = timedelta(hours=36)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    return _SLUG_STRIP.sub("-", value.casefold()).strip("-")


class LatestPrice(TypedDict):
    price_cents: int
    currency: str
    avg90_cents: int | None
    pct_below_avg90: int | None
    verdict: str | None
    observed_at: str


class FeaturedDeal(TypedDict):
    offer_id: int
    slug: str
    title: str
    brand: str | None
    category: str | None
    category_slug: str | None
    merchant: str
    price_cents: int
    currency: str
    product_url: str | None
    price_checked: str | None
    blurb: str | None
    latest_price: LatestPrice | None


class CuratedProduct(TypedDict):
    asin: str
    title: str
    product_url: str | None


class DealCategory(TypedDict):
    name: str
    slug: str
    count: int


def _as_utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; Postgres keeps the tz. Stored values are UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _pct_below(price_cents: int, avg90_cents: int | None) -> int | None:
    if not avg90_cents or avg90_cents <= 0:
        return None
    return round((avg90_cents - price_cents) / avg90_cents * 100)


def _latest_prices(db: Session, asins: list[str]) -> dict[str, LatestPrice]:
    """Latest recorded observation per curated ASIN, in one query."""

    if not asins:
        return {}
    latest = (
        select(
            PriceObservation.tracked_product_id.label("tracked_id"),
            func.max(PriceObservation.observed_at).label("observed_at"),
        )
        .group_by(PriceObservation.tracked_product_id)
        .subquery()
    )
    rows = db.execute(
        select(TrackedProduct.provider_product_id, PriceObservation)
        .join(PriceObservation, PriceObservation.tracked_product_id == TrackedProduct.id)
        .join(
            latest,
            (latest.c.tracked_id == PriceObservation.tracked_product_id)
            & (latest.c.observed_at == PriceObservation.observed_at),
        )
        .where(
            TrackedProduct.provider == TRACKING_PROVIDER,
            TrackedProduct.market == TRACKING_MARKET,
            TrackedProduct.provider_product_id.in_(asins),
        )
    ).all()
    result: dict[str, LatestPrice] = {}
    for asin, obs in rows:
        result[asin] = {
            "price_cents": obs.effective_price_cents,
            "currency": obs.currency,
            "avg90_cents": obs.avg90_cents,
            "pct_below_avg90": _pct_below(obs.effective_price_cents, obs.avg90_cents),
            "verdict": obs.verdict,
            "observed_at": _as_utc(obs.observed_at).isoformat(),
        }
    return result


def _asin(listing: MerchantListing) -> str:
    return listing.provider_product_id.strip().upper()


def _row_to_deal(
    offer: Offer,
    listing: MerchantListing,
    merchant: Merchant,
    product: CanonicalProduct,
    latest: dict[str, LatestPrice] | None = None,
) -> FeaturedDeal:
    metadata = listing.provider_metadata or {}
    title = product.title or listing.title or offer.title
    return {
        "offer_id": offer.id,
        "slug": slugify(title),
        "title": title,
        "brand": product.brand.name if product.brand else None,
        "category": product.category.name if product.category else None,
        "category_slug": product.category.slug if product.category else None,
        "merchant": merchant.name,
        "price_cents": offer.price_cents,
        "currency": offer.currency,
        "product_url": listing.product_url,
        "price_checked": metadata.get("price_checked"),
        "blurb": metadata.get("blurb"),
        "latest_price": (latest or {}).get(_asin(listing)),
    }


def _base_statement() -> Select[tuple[Offer, MerchantListing, Merchant, CanonicalProduct]]:
    return (
        select(Offer, MerchantListing, Merchant, CanonicalProduct)
        .join(MerchantListing, Offer.merchant_listing_id == MerchantListing.id)
        .join(Merchant, MerchantListing.merchant_id == Merchant.id)
        .join(CanonicalProduct, MerchantListing.canonical_product_id == CanonicalProduct.id)
        .where(
            Offer.provider_source == CURATED_PROVIDER_SOURCE,
            Offer.record_status == RecordStatus.active.value,
            MerchantListing.record_status == RecordStatus.active.value,
        )
    )


def list_featured_deals(
    db: Session,
    *,
    limit: int = 100,
    category_slug: str | None = None,
) -> list[FeaturedDeal]:
    statement = _base_statement().order_by(Offer.price_cents.asc(), Offer.id.asc())
    if category_slug:
        statement = statement.where(CanonicalProduct.category.has(Category.slug == category_slug))
    statement = statement.limit(limit)
    rows = db.execute(statement).all()
    latest = _latest_prices(db, [_asin(row[1]) for row in rows])
    return [_row_to_deal(*row, latest) for row in rows]


def get_featured_deal(db: Session, slug: str) -> FeaturedDeal | None:
    target = slugify(slug)
    for row in db.execute(_base_statement().order_by(Offer.id.asc())).all():
        deal = _row_to_deal(*row)
        if deal["slug"] == target:
            deal["latest_price"] = _latest_prices(db, [_asin(row[1])]).get(_asin(row[1]))
            return deal
    return None


def curated_amazon_products(db: Session) -> list[CuratedProduct]:
    """Every active curated ASIN, for the daily poll to track."""

    seen: dict[str, CuratedProduct] = {}
    for _offer, listing, _merchant, product in db.execute(_base_statement()).all():
        asin = _asin(listing)
        if asin and asin not in seen:
            seen[asin] = {
                "asin": asin,
                "title": product.title or listing.title,
                "product_url": listing.product_url,
            }
    return list(seen.values())


def list_price_drops(
    db: Session,
    *,
    limit: int = 12,
    now: datetime | None = None,
    min_pct: int = PRICE_DROP_MIN_PCT,
    max_age: timedelta = PRICE_DROP_MAX_AGE,
) -> list[FeaturedDeal]:
    """Curated deals whose latest recorded price is under their 90-day average
    and near their 90-day low (a BUY verdict from the same rules as Price
    Check).

    Only fresh observations count (``max_age``), so a stale reading never shows
    up as "today". Largest drop first. Empty when nothing qualifies — callers
    must say so rather than pad the list.
    """

    now = now or datetime.now(tz=UTC)
    rows = db.execute(_base_statement().order_by(Offer.id.asc())).all()
    latest = _latest_prices(db, [_asin(row[1]) for row in rows])
    drops: list[FeaturedDeal] = []
    seen: set[str] = set()
    for row in rows:
        asin = _asin(row[1])
        price = latest.get(asin)
        if asin in seen or price is None:
            continue
        pct = price["pct_below_avg90"]
        observed = datetime.fromisoformat(price["observed_at"])
        if pct is None or pct < min_pct or now - observed > max_age:
            continue
        if price["verdict"] != PRICE_DROP_VERDICT:
            continue
        seen.add(asin)
        drops.append(_row_to_deal(*row, latest))
    drops.sort(key=lambda d: -(d["latest_price"] or {}).get("pct_below_avg90", 0))
    return drops[:limit]


def list_deal_categories(db: Session) -> list[DealCategory]:
    counts: dict[str, DealCategory] = {}
    for row in db.execute(_base_statement()).all():
        deal = _row_to_deal(*row)
        name = deal["category"]
        cat_slug = deal["category_slug"]
        if not name or not cat_slug:
            continue
        entry = counts.setdefault(cat_slug, {"name": name, "slug": cat_slug, "count": 0})
        entry["count"] += 1
    return sorted(counts.values(), key=lambda c: c["name"].casefold())
