from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AffiliateClickEvent, ClickTargetType, MerchantListing, Offer, RecordStatus


@dataclass(frozen=True)
class ClickTrackingInput:
    offer_id: int
    target_type: str
    referrer: str | None = None
    user_agent: str | None = None


class ClickTrackingResult(TypedDict):
    id: int
    offer_id: int | None
    target_type: str
    target_url: str
    provider_source: str
    source_record_id: str
    market: str


def _normalize_optional(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:max_length]


def valid_click_target(value: str) -> str:
    allowed = {target.value for target in ClickTargetType}
    if value not in allowed:
        msg = f"target_type must be one of: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return value


def record_click(db: Session, payload: ClickTrackingInput) -> ClickTrackingResult | None:
    target_type = valid_click_target(payload.target_type)
    row = db.execute(
        select(Offer, MerchantListing)
        .join(MerchantListing, Offer.merchant_listing_id == MerchantListing.id)
        .where(
            Offer.id == payload.offer_id,
            Offer.record_status == RecordStatus.active.value,
            MerchantListing.record_status == RecordStatus.active.value,
        )
    ).one_or_none()
    if row is None:
        return None

    offer, listing = row
    target_url = listing.product_url
    if target_type == ClickTargetType.affiliate.value:
        target_url = offer.affiliate_link.url if offer.affiliate_link else None
    if target_url is None:
        return None

    event = AffiliateClickEvent(
        offer_id=offer.id,
        merchant_id=listing.merchant_id,
        merchant_listing_id=listing.id,
        target_type=target_type,
        target_url=target_url,
        provider_source=offer.provider_source,
        source_record_id=offer.source_record_id,
        market=offer.market,
        user_agent=_normalize_optional(payload.user_agent, 512),
        referrer=_normalize_optional(payload.referrer, 2048),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {
        "id": event.id,
        "offer_id": event.offer_id,
        "target_type": event.target_type,
        "target_url": event.target_url,
        "provider_source": event.provider_source,
        "source_record_id": event.source_record_id,
        "market": event.market,
    }
