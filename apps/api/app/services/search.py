from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict, cast

from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AffiliateClickEvent,
    Brand,
    CanonicalProduct,
    CashbackOffer,
    Category,
    Coupon,
    FreshnessStatus,
    Merchant,
    MerchantListing,
    Offer,
    PriceHistory,
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
    sort: str = "price_asc"
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
    click_count: int
    match_reasons: list[str]
    ranking_reasons: list[str]


class CouponSummary(TypedDict):
    code: str
    description: str
    discount_type: str
    discount_value: int
    expires_at: datetime | None


class CashbackSummary(TypedDict):
    rate_type: str
    rate_value_bps: int
    expires_at: datetime | None


class PricePoint(TypedDict):
    observed_at: datetime
    price_cents: int
    sale_price_cents: int | None


class SourceAttribution(TypedDict):
    provider_source: str
    source_record_id: str
    source_timestamp: datetime
    last_successful_update: datetime | None
    record_status: str


class OfferDetailRow(SearchResultRow):
    merchant_url: str | None
    affiliate_url: str | None
    source_attribution: SourceAttribution
    coupons: list[CouponSummary]
    cashback_offers: list[CashbackSummary]
    price_history: list[PricePoint]


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _query_terms(value: str | None) -> list[str]:
    normalized = _normalized(value)
    if normalized is None:
        return []
    terms = [term for term in normalized.split() if len(term) >= 3]
    if "backpack" in {term.casefold() for term in terms}:
        terms.append("pack")
    return terms


def _matches(value: str | None, terms: list[str]) -> bool:
    if value is None:
        return False
    normalized = value.casefold()
    return any(term.casefold() in normalized for term in terms)


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


def _active_coupon_statement(merchant_id: int) -> Select[tuple[Coupon]]:
    return (
        select(Coupon)
        .where(
            Coupon.merchant_id == merchant_id,
            Coupon.record_status == RecordStatus.active.value,
            Coupon.is_expired.is_(False),
        )
        .order_by(Coupon.expires_at.asc().nullslast(), Coupon.id.asc())
    )


def _active_cashback_statement(merchant_id: int) -> Select[tuple[CashbackOffer]]:
    return (
        select(CashbackOffer)
        .where(
            CashbackOffer.merchant_id == merchant_id,
            CashbackOffer.record_status == RecordStatus.active.value,
        )
        .order_by(CashbackOffer.rate_value_bps.desc(), CashbackOffer.id.asc())
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


def _click_count_expression() -> ColumnElement[int]:
    return (
        select(func.count(AffiliateClickEvent.id))
        .where(AffiliateClickEvent.offer_id == Offer.id)
        .correlate(Offer)
        .scalar_subquery()
    )


def _has_coupon(db: Session, merchant_id: int) -> bool:
    return (
        db.scalar(
            select(
                exists().where(
                    Coupon.merchant_id == merchant_id,
                    Coupon.record_status == RecordStatus.active.value,
                    Coupon.is_expired.is_(False),
                )
            )
        )
        is True
    )


def _has_cashback(db: Session, merchant_id: int) -> bool:
    return (
        db.scalar(
            select(
                exists().where(
                    CashbackOffer.merchant_id == merchant_id,
                    CashbackOffer.record_status == RecordStatus.active.value,
                )
            )
        )
        is True
    )


def _offer_click_count(db: Session, offer_id: int) -> int:
    return (
        db.scalar(
            select(func.count(AffiliateClickEvent.id)).where(
                AffiliateClickEvent.offer_id == offer_id
            )
        )
        or 0
    )


def _match_reasons(
    query_terms: list[str],
    offer: Offer,
    listing: MerchantListing,
    merchant: Merchant,
    product: CanonicalProduct,
) -> list[str]:
    if not query_terms:
        return ["active mock offer"]

    reasons: list[str] = []
    if _matches(product.title, query_terms) or _matches(listing.title, query_terms):
        reasons.append("product title")
    if _matches(offer.title, query_terms):
        reasons.append("offer title")
    if _matches(merchant.name, query_terms):
        reasons.append("merchant")
    if product.brand and _matches(product.brand.name, query_terms):
        reasons.append("brand")
    if product.category and _matches(product.category.name, query_terms):
        reasons.append("category")
    return reasons or ["filters"]


def _ranking_reasons(
    sort: str | None,
    offer: Offer,
    has_coupon: bool,
    has_cashback: bool,
    click_count: int,
) -> list[str]:
    reasons: list[str] = []
    current_price = offer.sale_price_cents or offer.price_cents

    if sort == "clicks_desc":
        if click_count > 0:
            click_label = "click" if click_count == 1 else "clicks"
            reasons.append(f"{click_count} mock {click_label}")
        else:
            reasons.append("no mock clicks yet")
    elif sort == "price_desc":
        reasons.append(f"higher current price: {current_price / 100:.2f} {offer.currency}")
    elif sort == "merchant":
        reasons.append("merchant name order")
    else:
        reasons.append(f"lower current price: {current_price / 100:.2f} {offer.currency}")

    if offer.sale_price_cents is not None and offer.sale_price_cents < offer.price_cents:
        reasons.append("sale price available")
    if has_coupon:
        reasons.append("coupon available")
    if has_cashback:
        reasons.append("cashback available")
    if offer.freshness_status == FreshnessStatus.fresh.value:
        reasons.append("fresh mock data")

    return reasons[:4] or ["active mock offer"]


def _search_result_row(
    db: Session,
    offer: Offer,
    listing: MerchantListing,
    merchant: Merchant,
    product: CanonicalProduct,
    query_terms: list[str],
    sort: str | None = None,
) -> SearchResultRow:
    has_coupon = _has_coupon(db, merchant.id)
    has_cashback = _has_cashback(db, merchant.id)
    click_count = _offer_click_count(db, offer.id)
    return {
        "offer_id": offer.id,
        "product_id": product.id,
        "title": product.title,
        "offer_title": offer.title,
        "merchant": merchant.name,
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
        "click_count": click_count,
        "match_reasons": _match_reasons(
            query_terms,
            offer,
            listing,
            merchant,
            product,
        ),
        "ranking_reasons": _ranking_reasons(
            sort,
            offer,
            has_coupon,
            has_cashback,
            click_count,
        ),
    }


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
    click_count = _click_count_expression()
    if filters.sort == "price_desc":
        statement = statement.order_by(effective_price.desc(), Offer.id.asc())
    elif filters.sort == "clicks_desc":
        statement = statement.order_by(click_count.desc(), effective_price.asc(), Offer.id.asc())
    elif filters.sort == "merchant":
        statement = statement.order_by(Merchant.name.asc(), effective_price.asc(), Offer.id.asc())
    else:
        statement = statement.order_by(effective_price.asc(), Offer.id.asc())
    statement = statement.limit(filters.limit)

    results: list[SearchResultRow] = []
    for offer, listing, merchant_row, product in db.execute(statement).all():
        results.append(
            _search_result_row(
                db,
                offer,
                listing,
                merchant_row,
                product,
                query_terms,
                filters.sort,
            )
        )
    return results


def get_offer_detail(db: Session, offer_id: int) -> OfferDetailRow | None:
    row = db.execute(_base_query().where(Offer.id == offer_id)).one_or_none()
    if row is None:
        return None

    offer, listing, merchant, product = row
    base = _search_result_row(db, offer, listing, merchant, product, [])
    coupons = [
        {
            "code": coupon.code,
            "description": coupon.description,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "expires_at": coupon.expires_at,
        }
        for coupon in db.scalars(_active_coupon_statement(merchant.id)).all()
    ]
    cashback_offers = [
        {
            "rate_type": cashback.rate_type,
            "rate_value_bps": cashback.rate_value_bps,
            "expires_at": cashback.expires_at,
        }
        for cashback in db.scalars(_active_cashback_statement(merchant.id)).all()
    ]
    price_history = [
        {
            "observed_at": price_point.observed_at,
            "price_cents": price_point.price_cents,
            "sale_price_cents": price_point.sale_price_cents,
        }
        for price_point in db.scalars(
            select(PriceHistory)
            .where(PriceHistory.merchant_listing_id == listing.id)
            .order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc())
            .limit(6)
        ).all()
    ]
    return cast(
        OfferDetailRow,
        {
            **base,
            "merchant_url": merchant.website_url,
            "affiliate_url": offer.affiliate_link.url if offer.affiliate_link else None,
            "source_attribution": {
                "provider_source": offer.provider_source,
                "source_record_id": offer.source_record_id,
                "source_timestamp": offer.source_timestamp,
                "last_successful_update": offer.last_successful_update,
                "record_status": offer.record_status,
            },
            "coupons": coupons,
            "cashback_offers": cashback_offers,
            "price_history": price_history,
        },
    )


def valid_freshness(value: str | None) -> str | None:
    normalized = _normalized(value)
    if normalized is None:
        return None
    allowed = {status.value for status in FreshnessStatus}
    if normalized not in allowed:
        msg = f"freshness must be one of: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized


def valid_sort(value: str | None) -> str:
    normalized = _normalized(value)
    if normalized is None:
        return "price_asc"
    allowed = {"clicks_desc", "merchant", "price_asc", "price_desc"}
    if normalized not in allowed:
        msg = f"sort must be one of: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized
