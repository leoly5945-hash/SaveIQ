"""Anonymous user profile and event models (Gate 8). No PII fields."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class AnonymousUser(Base):
    """Opaque anonymized user profile. Never stores email/phone/name."""

    __tablename__ = "anonymous_users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    preferred_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    avg_query_length: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_feedback: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    personalization_opt_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    click_history: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (Index("ix_anonymous_users_last_active", "last_active"),)


class UserEvent(Base):
    """Behavioral event log for anonymized users."""

    __tablename__ = "user_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("anonymous_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    offer_id: Mapped[int | None] = mapped_column(Integer)
    query_text: Mapped[str | None] = mapped_column(String(240))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_user_events_user_created", "user_id", "created_at"),
        Index("ix_user_events_type", "event_type"),
    )
