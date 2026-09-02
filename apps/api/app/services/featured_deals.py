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
"""

from __future__ import annotations

import re
from typing import TypedDict

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalProduct,
    Category,
    Merchant,
    MerchantListing,
    Offer,
    RecordStatus,
)

CURATED_PROVIDER_SOURCE = "amazon_ca"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    return _SLUG_STRIP.sub("-", value.casefold()).strip("-")


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


class DealCategory(TypedDict):
    name: str
    slug: str
    count: int


def _row_to_deal(
    offer: Offer, listing: MerchantListing, merchant: Merchant, product: CanonicalProduct
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
    return [_row_to_deal(*row) for row in db.execute(statement).all()]


def get_featured_deal(db: Session, slug: str) -> FeaturedDeal | None:
    target = slugify(slug)
    for row in db.execute(_base_statement().order_by(Offer.id.asc())).all():
        deal = _row_to_deal(*row)
        if deal["slug"] == target:
            return deal
    return None


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
