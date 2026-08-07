from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.models import RecommendationFeedbackRating
from app.observability.metrics import observe_recommendation
from app.services.canary.effective import is_feature_active
from app.services.llm_intent_parser import build_llm_intent_parser_service
from app.services.recommendation_feedback import record_recommendation_feedback
from app.services.recommendations import recommend_offers
from app.services.user.identity import normalize_anonymous_user_id
from app.services.user.profile import build_user_profile_service

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=240)
    limit: int = Field(default=5, ge=1, le=10)
    anonymous_user_id: str | None = Field(default=None, max_length=64)
    market: str = Field(default="CA", min_length=2, max_length=8)


class RecommendationFeedbackRequest(BaseModel):
    trace_event_id: int = Field(gt=0)
    offer_id: int = Field(gt=0)
    rating: RecommendationFeedbackRating
    reason: str | None = Field(default=None, max_length=240)
    source: str = Field(default="staging_ui", min_length=3, max_length=40)
    anonymous_user_id: str | None = Field(default=None, max_length=64)


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
    settings: AppSettings,
    x_anonymous_user_id: Annotated[str | None, Header(alias="X-Anonymous-User-Id")] = None,
) -> RecommendationResponse:
    user_id = request.anonymous_user_id or x_anonymous_user_id
    if user_id:
        try:
            user_id = normalize_anonymous_user_id(user_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = recommend_offers(
        db,
        request.intent,
        request.limit,
        llm_intent_parser=build_llm_intent_parser_service(settings),
        user_id=user_id if is_feature_active("personalization", settings=settings) else None,
        market=request.market,
    )
    observe_recommendation(strategy=str(result["strategy"]))
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
    settings: AppSettings,
    x_anonymous_user_id: Annotated[str | None, Header(alias="X-Anonymous-User-Id")] = None,
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
    user_id = request.anonymous_user_id or x_anonymous_user_id
    if is_feature_active("personalization", settings=settings) and user_id:
        try:
            normalized = normalize_anonymous_user_id(user_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if normalized:
            satisfaction = 1.0 if request.rating.value == "helpful" else 0.0
            build_user_profile_service(settings).record_event(
                normalized,
                event_type="feedback",
                offer_id=request.offer_id,
                metadata={
                    "rating": request.rating.value,
                    "user_satisfaction": satisfaction,
                    "trace_event_id": request.trace_event_id,
                },
                db=db,
            )
    return RecommendationFeedbackResponse(**result)
