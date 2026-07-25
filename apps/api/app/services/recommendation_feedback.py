from __future__ import annotations

from typing import TypedDict

from sqlalchemy.orm import Session

from app.models import (
    Offer,
    RecommendationFeedbackEvent,
    RecommendationFeedbackRating,
    RecommendationTraceEvent,
)


class RecommendationFeedbackResult(TypedDict):
    id: int
    trace_event_id: int
    offer_id: int
    rating: str
    reason: str | None
    source: str
    provider_source: str
    market: str


def record_recommendation_feedback(
    db: Session,
    *,
    trace_event_id: int,
    offer_id: int,
    rating: RecommendationFeedbackRating,
    reason: str | None,
    source: str,
) -> RecommendationFeedbackResult | None:
    trace_event = db.get(RecommendationTraceEvent, trace_event_id)
    offer = db.get(Offer, offer_id)
    if trace_event is None or offer is None:
        return None
    if offer_id not in trace_event.recommended_offer_ids:
        return None

    event = RecommendationFeedbackEvent(
        trace_event_id=trace_event_id,
        offer_id=offer_id,
        rating=rating.value,
        reason=reason,
        source=source,
        provider_source=offer.provider_source,
        market=offer.market,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "id": event.id,
        "trace_event_id": event.trace_event_id,
        "offer_id": offer_id,
        "rating": event.rating,
        "reason": event.reason,
        "source": event.source,
        "provider_source": event.provider_source or offer.provider_source,
        "market": event.market or offer.market,
    }
