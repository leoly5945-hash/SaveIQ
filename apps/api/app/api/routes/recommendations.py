from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import RecommendationFeedbackRating
from app.services.recommendation_feedback import record_recommendation_feedback
from app.services.recommendations import recommend_offers

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=240)
    limit: int = Field(default=5, ge=1, le=10)


class RecommendationFeedbackRequest(BaseModel):
    trace_event_id: int = Field(gt=0)
    offer_id: int = Field(gt=0)
    rating: RecommendationFeedbackRating
    reason: str | None = Field(default=None, max_length=240)
    source: str = Field(default="staging_ui", min_length=3, max_length=40)


class RecommendationFeedbackResponse(BaseModel):
    id: int
    trace_event_id: int
    offer_id: int
    rating: str
    reason: str | None
    source: str
    provider_source: str
    market: str


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


class RecommendationDecisionExplanationResponse(BaseModel):
    summary: str
    matched_intent: list[str] = Field(default_factory=list)
    ranking_signals: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)


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
    decision_explanation: RecommendationDecisionExplanationResponse


class RecommendationResponse(BaseModel):
    intent: RecommendationIntentResponse
    strategy: str
    rule_version: str
    intent_parser_version: str
    ranker_version: str
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
        rule_version=result["rule_version"],
        intent_parser_version=result["intent_parser_version"],
        ranker_version=result["ranker_version"],
        trace_event_id=result["trace_event_id"],
        count=len(result["results"]),
        recommendations=[
            RecommendationOfferResponse.model_validate(recommendation)
            for recommendation in result["results"]
        ],
        evaluation_trace=[RecommendationTraceStepResponse(**step) for step in result["trace"]],
    )


@router.post("/feedback", response_model=RecommendationFeedbackResponse, status_code=201)
def submit_recommendation_feedback(
    request: RecommendationFeedbackRequest,
    db: DbSession,
) -> RecommendationFeedbackResponse:
    result = record_recommendation_feedback(
        db,
        trace_event_id=request.trace_event_id,
        offer_id=request.offer_id,
        rating=request.rating,
        reason=request.reason,
        source=request.source,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendation trace or offer was not found for feedback.",
        )
    return RecommendationFeedbackResponse(**result)
