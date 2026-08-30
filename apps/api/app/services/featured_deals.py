"""Read model for the homepage "Featured deals" strip.

These are the hand-picked real products ingested by
:class:`app.services.affiliate.curated_provider.CuratedAmazonProvider`
(``provider_source == "amazon_ca"``). We surface them as a small, honest set:
the price is a point-in-time snapshot labelled with the date it was checked,
and there is no "was" price or discount claim.
"""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CanonicalProduct, Merchant, MerchantListing, Offer, RecordStatus

CURATED_PROVIDER_SOURCE = "amazon_ca"


class FeaturedDeal(TypedDict):
    offer_id: int
    title: str
    brand: str | None
    category: str | None
    merchant: str
    price_cents: int
    currency: str
    product_url: str | None
    price_checked: str | None
    blurb: str | None


def list_featured_deals(db: Session, *, limit: int = 24) -> list[FeaturedDeal]:
    statement = (
        select(Offer, MerchantListing, Merchant, CanonicalProduct)
        .join(MerchantListing, Offer.merchant_listing_id == MerchantListing.id)
        .join(Merchant, MerchantListing.merchant_id == Merchant.id)
        .join(CanonicalProduct, MerchantListing.canonical_product_id == CanonicalProduct.id)
        .where(
            Offer.provider_source == CURATED_PROVIDER_SOURCE,
            Offer.record_status == RecordStatus.active.value,
            MerchantListing.record_status == RecordStatus.active.value,
        )
        .order_by(Offer.price_cents.asc(), Offer.id.asc())
        .limit(limit)
    )

    deals: list[FeaturedDeal] = []
    for offer, listing, merchant, product in db.execute(statement).all():
        metadata = listing.provider_metadata or {}
        deals.append(
            {
                "offer_id": offer.id,
                "title": product.title or listing.title or offer.title,
                "brand": product.brand.name if product.brand else None,
                "category": product.category.name if product.category else None,
                "merchant": merchant.name,
                "price_cents": offer.price_cents,
                "currency": offer.currency,
                "product_url": listing.product_url,
                "price_checked": metadata.get("price_checked"),
                "blurb": metadata.get("blurb"),
            }
        )
    return deals
