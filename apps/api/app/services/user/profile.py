"""User profile service for Gate 8 personalization (anonymized IDs only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.session import SessionLocal
from app.models.user import AnonymousUser, UserEvent
from app.services.router.redis_client import create_redis_client
from app.services.user.cache import ProfileCache
from app.services.user.embedding import (
    EMBEDDING_DIM,
    MAX_CLICK_HISTORY,
    compute_user_embedding,
    empty_embedding,
)
from app.services.user.identity import normalize_anonymous_user_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    preferred_categories: list[str]
    avg_query_length: float
    click_history: list[int]
    session_count: int
    total_clicks: int
    total_feedback: int
    last_active: datetime | None
    personalization_opt_out: bool
    embedding: list[float]
    personalization_active: bool

    def bandit_features(self) -> dict[str, float]:
        emb = self.embedding if len(self.embedding) == EMBEDDING_DIM else empty_embedding()
        click_rate = 0.0
        if self.session_count > 0:
            click_rate = min(self.total_clicks / float(self.session_count), 5.0) / 5.0
        features = {
            "session_count_norm": min(self.session_count / 50.0, 1.0),
            "click_rate_norm": click_rate,
            "avg_query_length_norm": min(self.avg_query_length / 240.0, 1.0),
            "opt_out": 1.0 if self.personalization_opt_out else 0.0,
        }
        for index, value in enumerate(emb):
            features[f"emb_{index}"] = float(value)
        return features

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "preferred_categories": list(self.preferred_categories),
            "avg_query_length": self.avg_query_length,
            "click_history": list(self.click_history)[-20:],
            "session_count": self.session_count,
            "total_clicks": self.total_clicks,
            "total_feedback": self.total_feedback,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "personalization_opt_out": self.personalization_opt_out,
            "embedding_dim": len(self.embedding),
            "personalization_active": self.personalization_active,
            # Never expose raw embedding by default in public API — admin may still use as_dict.
        }


class UserProfileService:
    def __init__(
        self,
        settings: Settings,
        *,
        cache: ProfileCache | None = None,
        session_factory: Any = SessionLocal,
    ) -> None:
        self._settings = settings
        redis_client = create_redis_client(settings.redis_url)
        self._cache = cache or ProfileCache(
            redis_client,
            enabled=settings.personalization_cache_enabled,
            ttl_seconds=settings.personalization_cache_ttl_seconds,
        )
        self._session_factory = session_factory

    def enabled(self) -> bool:
        return self._settings.feature_personalization

    def get_profile(
        self,
        user_id: str,
        *,
        db: Session | None = None,
        create_if_missing: bool = True,
    ) -> UserProfile | None:
        try:
            normalized = normalize_anonymous_user_id(user_id)
        except ValueError:
            return None
        if normalized is None:
            return None

        if self.enabled():
            cached = self._cache.get(normalized)
            if cached is not None:
                return self._profile_from_payload(cached)

        owns = db is None
        session = db or self._session_factory()
        try:
            row = session.get(AnonymousUser, normalized)
            if row is None:
                if not create_if_missing or not self.enabled():
                    return None
                row = AnonymousUser(
                    user_id=normalized,
                    preferences={},
                    preferred_categories=[],
                    embedding=empty_embedding(),
                    click_history=[],
                    total_sessions=1,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            profile = self._from_row(row)
            if self.enabled():
                self._cache.set(normalized, self._cache_payload(profile))
            return profile
        except Exception:  # noqa: BLE001
            logger.exception("get_profile failed")
            if owns:
                session.rollback()
            return None
        finally:
            if owns:
                session.close()

    def set_opt_out(
        self,
        user_id: str,
        opt_out: bool,
        *,
        db: Session | None = None,
    ) -> UserProfile | None:
        profile = self.get_profile(user_id, db=db, create_if_missing=True)
        if profile is None:
            return None
        owns = db is None
        session = db or self._session_factory()
        try:
            row = session.get(AnonymousUser, profile.user_id)
            if row is None:
                return None
            row.personalization_opt_out = bool(opt_out)
            row.last_active = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            updated = self._from_row(row)
            self._cache.set(updated.user_id, self._cache_payload(updated))
            return updated
        except Exception:  # noqa: BLE001
            logger.exception("set_opt_out failed")
            session.rollback()
            return None
        finally:
            if owns:
                session.close()

    def record_event(
        self,
        user_id: str,
        *,
        event_type: str,
        offer_id: int | None = None,
        query_text: str | None = None,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
        db: Session | None = None,
    ) -> UserProfile | None:
        if not self.enabled():
            return None
        try:
            normalized = normalize_anonymous_user_id(user_id)
        except ValueError:
            return None
        if normalized is None:
            return None

        owns = db is None
        session = db or self._session_factory()
        try:
            row = session.get(AnonymousUser, normalized)
            if row is None:
                row = AnonymousUser(
                    user_id=normalized,
                    preferences={},
                    preferred_categories=[],
                    embedding=empty_embedding(),
                    click_history=[],
                    total_sessions=1,
                )
                session.add(row)
                session.flush()

            now = datetime.now(UTC)
            row.last_active = now
            event = UserEvent(
                user_id=normalized,
                event_type=event_type[:40],
                offer_id=offer_id,
                query_text=(query_text or "")[:240] or None,
                event_metadata=metadata or {},
            )
            session.add(event)

            if event_type == "session":
                row.total_sessions = int(row.total_sessions or 0) + 1
            if event_type == "query" and query_text:
                length = float(len(query_text.strip()))
                previous = float(row.avg_query_length or 0.0)
                sessions = max(int(row.total_sessions or 1), 1)
                row.avg_query_length = ((previous * (sessions - 1)) + length) / sessions
            if event_type == "click" and offer_id is not None:
                row.total_clicks = int(row.total_clicks or 0) + 1
                history = list(row.click_history or [])
                history.append(int(offer_id))
                row.click_history = history[-MAX_CLICK_HISTORY:]
                if category:
                    cats = list(row.preferred_categories or [])
                    normalized_cat = category.strip().lower()
                    if normalized_cat and normalized_cat not in cats:
                        cats.insert(0, normalized_cat)
                    row.preferred_categories = cats[:12]
            if event_type in {"rating", "feedback"}:
                row.total_feedback = int(row.total_feedback or 0) + 1

            categories = list(row.preferred_categories or [])
            click_history = list(row.click_history or [])
            if self._settings.feature_llm_user_embedding:
                from app.services.user.llm_embedding import (
                    HashFallbackEmbeddingClient,
                    QwenEmbeddingClient,
                    embed_user_history,
                )

                client: QwenEmbeddingClient | HashFallbackEmbeddingClient
                if self._settings.dashscope_api_key:
                    client = QwenEmbeddingClient(self._settings.dashscope_api_key)
                else:
                    client = HashFallbackEmbeddingClient()
                row.embedding = embed_user_history(
                    titles=[],
                    categories=categories,
                    click_history=click_history,
                    client=client,
                )
            else:
                row.embedding = compute_user_embedding(
                    click_history=click_history,
                    preferred_categories=categories,
                )
            session.commit()
            session.refresh(row)
            profile = self._from_row(row)
            self._cache.set(profile.user_id, self._cache_payload(profile))
            return profile
        except Exception:  # noqa: BLE001
            logger.exception("record_event failed")
            session.rollback()
            return None
        finally:
            if owns:
                session.close()

    def compute_embedding(self, user_id: str, *, db: Session | None = None) -> list[float]:
        profile = self.get_profile(user_id, db=db, create_if_missing=False)
        if profile is None:
            return empty_embedding()
        return list(profile.embedding)

    def stats(self, *, db: Session | None = None) -> dict[str, Any]:
        owns = db is None
        session = db or self._session_factory()
        try:
            user_count = session.scalar(select(func.count()).select_from(AnonymousUser)) or 0
            event_count = session.scalar(select(func.count()).select_from(UserEvent)) or 0
            opt_out_count = (
                session.scalar(
                    select(func.count())
                    .select_from(AnonymousUser)
                    .where(AnonymousUser.personalization_opt_out.is_(True))
                )
                or 0
            )
            return {
                "feature_enabled": self.enabled(),
                "user_count": int(user_count),
                "event_count": int(event_count),
                "opt_out_count": int(opt_out_count),
                "embedding_dim": EMBEDDING_DIM,
            }
        except Exception:  # noqa: BLE001
            logger.exception("stats failed")
            return {
                "feature_enabled": self.enabled(),
                "user_count": 0,
                "event_count": 0,
                "opt_out_count": 0,
                "embedding_dim": EMBEDDING_DIM,
            }
        finally:
            if owns:
                session.close()

    def status(self) -> dict[str, Any]:
        return {
            "feature_enabled": self.enabled(),
            "cache_enabled": self._cache.enabled,
            "cache_ttl_seconds": self._cache.ttl_seconds,
            "embedding_dim": EMBEDDING_DIM,
            "pii_policy": "anonymous_opaque_ids_only",
        }

    def _from_row(self, row: AnonymousUser) -> UserProfile:
        opt_out = bool(row.personalization_opt_out)
        active = self.enabled() and not opt_out
        embedding = list(row.embedding or [])
        if len(embedding) != EMBEDDING_DIM:
            embedding = compute_user_embedding(
                click_history=list(row.click_history or []),
                preferred_categories=list(row.preferred_categories or []),
            )
        return UserProfile(
            user_id=row.user_id,
            preferred_categories=list(row.preferred_categories or []),
            avg_query_length=float(row.avg_query_length or 0.0),
            click_history=list(row.click_history or []),
            session_count=int(row.total_sessions or 0),
            total_clicks=int(row.total_clicks or 0),
            total_feedback=int(row.total_feedback or 0),
            last_active=row.last_active,
            personalization_opt_out=opt_out,
            embedding=embedding,
            personalization_active=active,
        )

    def _cache_payload(self, profile: UserProfile) -> dict[str, Any]:
        return {
            "user_id": profile.user_id,
            "preferred_categories": profile.preferred_categories,
            "avg_query_length": profile.avg_query_length,
            "click_history": profile.click_history,
            "session_count": profile.session_count,
            "total_clicks": profile.total_clicks,
            "total_feedback": profile.total_feedback,
            "last_active": profile.last_active.isoformat() if profile.last_active else None,
            "personalization_opt_out": profile.personalization_opt_out,
            "embedding": profile.embedding,
            "personalization_active": profile.personalization_active,
        }

    def _profile_from_payload(self, payload: dict[str, Any]) -> UserProfile:
        last_active_raw = payload.get("last_active")
        last_active = None
        if isinstance(last_active_raw, str) and last_active_raw:
            try:
                last_active = datetime.fromisoformat(last_active_raw)
            except ValueError:
                last_active = None
        return UserProfile(
            user_id=str(payload["user_id"]),
            preferred_categories=list(payload.get("preferred_categories") or []),
            avg_query_length=float(payload.get("avg_query_length") or 0.0),
            click_history=[int(item) for item in (payload.get("click_history") or [])],
            session_count=int(payload.get("session_count") or 0),
            total_clicks=int(payload.get("total_clicks") or 0),
            total_feedback=int(payload.get("total_feedback") or 0),
            last_active=last_active,
            personalization_opt_out=bool(payload.get("personalization_opt_out")),
            embedding=[float(v) for v in (payload.get("embedding") or empty_embedding())],
            personalization_active=bool(payload.get("personalization_active")),
        )


def build_user_profile_service(settings: Settings) -> UserProfileService:
    return UserProfileService(settings)
