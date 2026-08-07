"""Anonymous user profile and feedback APIs (Gate 8)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.services.canary.effective import is_feature_active
from app.services.llm_intent_parser import build_llm_intent_parser_service
from app.services.recommendations import recommend_offers
from app.services.user.identity import normalize_anonymous_user_id
from app.services.user.profile import build_user_profile_service

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/user", tags=["user"])


def _require_anonymous_user_id(
    x_anonymous_user_id: Annotated[str | None, Header(alias="X-Anonymous-User-Id")] = None,
) -> str:
    try:
        normalized = normalize_anonymous_user_id(x_anonymous_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if normalized is None:
        raise HTTPException(
            status_code=401,
            detail="X-Anonymous-User-Id header is required (opaque anonymized ID).",
        )
    return normalized


AnonymousUserId = Annotated[str, Depends(_require_anonymous_user_id)]


class UserProfileResponse(BaseModel):
    user_id: str
    preferred_categories: list[str]
    avg_query_length: float
    click_history: list[int]
    session_count: int
    total_clicks: int
    total_feedback: int
    last_active: str | None
    personalization_opt_out: bool
    embedding_dim: int
    personalization_active: bool


class UserOptOutRequest(BaseModel):
    opt_out: bool = True


class UserFeedbackRequest(BaseModel):
    offer_id: int = Field(gt=0)
    action: Literal["click", "view", "rating", "helpful", "not_helpful"]
    rating_value: float | None = Field(default=None, ge=0.0, le=1.0)
    category: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserFeedbackResponse(BaseModel):
    accepted: bool
    profile: UserProfileResponse | None = None


class UserRecommendationRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=240)
    limit: int = Field(default=5, ge=1, le=10)
    market: str = Field(default="CA", min_length=2, max_length=8)


@router.get("/profile", response_model=UserProfileResponse)
def get_user_profile(
    user_id: AnonymousUserId,
    db: DbSession,
    settings: AppSettings,
) -> UserProfileResponse:
    if not is_feature_active("personalization", settings=settings):
        raise HTTPException(
            status_code=503,
            detail="Personalization is disabled (FEATURE_PERSONALIZATION=false).",
        )
    profile = build_user_profile_service(settings).get_profile(
        user_id,
        db=db,
        create_if_missing=True,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    payload = profile.as_dict()
    return UserProfileResponse(**payload)


@router.post("/opt-out", response_model=UserProfileResponse)
def set_user_opt_out(
    payload: UserOptOutRequest,
    user_id: AnonymousUserId,
    db: DbSession,
    settings: AppSettings,
) -> UserProfileResponse:
    if not is_feature_active("personalization", settings=settings):
        raise HTTPException(
            status_code=503,
            detail="Personalization is disabled (FEATURE_PERSONALIZATION=false).",
        )
    profile = build_user_profile_service(settings).set_opt_out(
        user_id,
        payload.opt_out,
        db=db,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return UserProfileResponse(**profile.as_dict())


@router.post("/feedback", response_model=UserFeedbackResponse, status_code=201)
def submit_user_feedback(
    payload: UserFeedbackRequest,
    user_id: AnonymousUserId,
    db: DbSession,
    settings: AppSettings,
) -> UserFeedbackResponse:
    if not is_feature_active("personalization", settings=settings):
        raise HTTPException(
            status_code=503,
            detail="Personalization is disabled (FEATURE_PERSONALIZATION=false).",
        )
    event_type: str = payload.action
    if payload.action in {"helpful", "not_helpful"}:
        event_type = "feedback"
    profile = build_user_profile_service(settings).record_event(
        user_id,
        event_type=event_type,
        offer_id=payload.offer_id,
        category=payload.category,
        metadata={
            **payload.metadata,
            "action": payload.action,
            "rating_value": payload.rating_value,
        },
        db=db,
    )
    return UserFeedbackResponse(
        accepted=profile is not None,
        profile=UserProfileResponse(**profile.as_dict()) if profile else None,
    )


@router.post("/recommendations")
def personalized_recommendations(
    payload: UserRecommendationRequest,
    user_id: AnonymousUserId,
    db: DbSession,
    settings: AppSettings,
) -> dict[str, Any]:
    """Personalized recommendations; falls back to rule-based when flag/opt-out."""
    personalization_on = is_feature_active("personalization", settings=settings)
    result = recommend_offers(
        db,
        payload.intent,
        payload.limit,
        llm_intent_parser=build_llm_intent_parser_service(settings),
        user_id=user_id if personalization_on else None,
        market=payload.market,
    )
    return {
        "intent": result["intent"].__dict__,
        "strategy": result["strategy"],
        "rule_version": result["rule_version"],
        "intent_parser_version": result["intent_parser_version"],
        "ranker_version": result["ranker_version"],
        "trace_event_id": result["trace_event_id"],
        "count": len(result["results"]),
        "recommendations": result["results"],
        "evaluation_trace": result["trace"],
        "personalized": personalization_on,
        "anonymous_user_id": user_id,
    }
