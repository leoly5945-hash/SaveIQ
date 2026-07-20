from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Brand,
    CanonicalProduct,
    CashbackOffer,
    Category,
    Coupon,
    FreshnessStatus,
    Merchant,
    MerchantListing,
    Offer,
    RecordStatus,
)


@dataclass(frozen=True)
class SearchFilters:
    query: str | None = None
    merchant: str | None = None
    brand: str | None = None
    category: str | None = None
    has_coupon: bool | None = None
    has_cashback: bool | None = None
    freshness: str | None = None
    limit: int = 20


class SearchResultRow(TypedDict):
    offer_id: int
    product_id: int
    title: str
    offer_title: str
    merchant: str
    brand: str | None
    category: str | None
    price_cents: int
    sale_price_cents: int | None
    currency: str
    market: str
    availability: str
    freshness_status: str
    provider_source: str
    product_url: str | None
    has_coupon: bool
    has_cashback: bool


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _query_terms(value: str | None) -> list[str]:
    normalized = _normalized(value)
    if normalized is None:
        return []
    return [term for term in normalized.split() if len(term) >= 3]


def _text_match(pattern: str) -> ColumnElement[bool]:
    return or_(
        CanonicalProduct.title.ilike(pattern),
        MerchantListing.title.ilike(pattern),
        Offer.title.ilike(pattern),
        Merchant.name.ilike(pattern),
        CanonicalProduct.brand.has(Brand.name.ilike(pattern)),
        CanonicalProduct.category.has(Category.name.ilike(pattern)),
    )


def _merchant_has_coupon() -> ColumnElement[bool]:
    return exists().where(
        Coupon.merchant_id == Merchant.id,
        Coupon.record_status == RecordStatus.active.value,
        Coupon.is_expired.is_(False),
    )


def _merchant_has_cashback() -> ColumnElement[bool]:
    return exists().where(
        CashbackOffer.merchant_id == Merchant.id,
        CashbackOffer.record_status == RecordStatus.active.value,
    )


def _base_query() -> Select[tuple[Offer, MerchantListing, Merchant, CanonicalProduct]]:
    return (
        select(Offer, MerchantListing, Merchant, CanonicalProduct)
        .join(MerchantListing, Offer.merchant_listing_id == MerchantListing.id)
        .join(Merchant, MerchantListing.merchant_id == Merchant.id)
        .join(CanonicalProduct, MerchantListing.canonical_product_id == CanonicalProduct.id)
        .where(
            Offer.record_status == RecordStatus.active.value,
            MerchantListing.record_status == RecordStatus.active.value,
        )
    )


def search_offers(
    db: Session,
    filters: SearchFilters,
) -> list[SearchResultRow]:
    query_terms = _query_terms(filters.query)
    merchant = _normalized(filters.merchant)
    brand = _normalized(filters.brand)
    category = _normalized(filters.category)

    statement = _base_query()

    if query_terms:
        statement = statement.where(or_(*(_text_match(f"%{term}%") for term in query_terms)))
    if merchant:
        statement = statement.where(Merchant.name.ilike(f"%{merchant}%"))
    if brand:
        statement = statement.where(CanonicalProduct.brand.has(name=brand))
    if category:
        statement = statement.where(CanonicalProduct.category.has(name=category))
    if filters.has_coupon is True:
        statement = statement.where(_merchant_has_coupon())
    elif filters.has_coupon is False:
        statement = statement.where(~_merchant_has_coupon())
    if filters.has_cashback is True:
        statement = statement.where(_merchant_has_cashback())
    elif filters.has_cashback is False:
        statement = statement.where(~_merchant_has_cashback())
    if filters.freshness:
        statement = statement.where(Offer.freshness_status == filters.freshness)

    effective_price = func.coalesce(Offer.sale_price_cents, Offer.price_cents)
    statement = statement.order_by(effective_price.asc(), Offer.id.asc()).limit(filters.limit)

    results: list[SearchResultRow] = []
    for offer, listing, merchant_row, product in db.execute(statement).all():
        has_coupon = (
            db.scalar(
                select(
                    exists().where(
                        Coupon.merchant_id == merchant_row.id,
                        Coupon.record_status == RecordStatus.active.value,
                        Coupon.is_expired.is_(False),
                    )
                )
            )
            is True
        )
        has_cashback = (
            db.scalar(
                select(
                    exists().where(
                        CashbackOffer.merchant_id == merchant_row.id,
                        CashbackOffer.record_status == RecordStatus.active.value,
                    )
                )
            )
            is True
        )
        results.append(
            {
                "offer_id": offer.id,
                "product_id": product.id,
                "title": product.title,
                "offer_title": offer.title,
                "merchant": merchant_row.name,
                "brand": product.brand.name if product.brand else None,
                "category": product.category.name if product.category else None,
                "price_cents": offer.price_cents,
                "sale_price_cents": offer.sale_price_cents,
                "currency": offer.currency,
                "market": offer.market,
                "availability": offer.availability,
                "freshness_status": offer.freshness_status,
                "provider_source": offer.provider_source,
                "product_url": listing.product_url,
                "has_coupon": has_coupon,
                "has_cashback": has_cashback,
            }
        )
    return results


def valid_freshness(value: str | None) -> str | None:
    normalized = _normalized(value)
    if normalized is None:
        return None
    allowed = {status.value for status in FreshnessStatus}
    if normalized not in allowed:
        msg = f"freshness must be one of: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized
