from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.recommendations import recommend_offers

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=240)
    limit: int = Field(default=5, ge=1, le=10)


class RecommendationIntentResponse(BaseModel):
    raw_intent: str
    search_query: str | None
    has_coupon: bool | None
    has_cashback: bool | None
    freshness: str | None
    sort: str


class RecommendationTraceStepResponse(BaseModel):
    step: str
    input: str
    output: str
    notes: list[str] = Field(default_factory=list)


class RecommendationOfferResponse(BaseModel):
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


class RecommendationResponse(BaseModel):
    intent: RecommendationIntentResponse
    strategy: str
    trace_event_id: int
    count: int
    recommendations: list[RecommendationOfferResponse] = Field(default_factory=list)
    evaluation_trace: list[RecommendationTraceStepResponse] = Field(default_factory=list)


@router.post("", response_model=RecommendationResponse)
def recommend_products(
    request: RecommendationRequest,
    db: DbSession,
) -> RecommendationResponse:
    result = recommend_offers(db, request.intent, request.limit)
    return RecommendationResponse(
        intent=RecommendationIntentResponse(**result["intent"].__dict__),
        strategy=result["strategy"],
        trace_event_id=result["trace_event_id"],
        count=len(result["results"]),
        recommendations=[
            RecommendationOfferResponse(**recommendation) for recommendation in result["results"]
        ],
        evaluation_trace=[RecommendationTraceStepResponse(**step) for step in result["trace"]],
    )
