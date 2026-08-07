"""SQLAlchemy model for contextual bandit decision logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class BanditLog(Base):
    __tablename__ = "bandit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reward: Mapped[float | None] = mapped_column(Float)
    user_id: Mapped[str | None] = mapped_column(String(120))
    rule_action: Mapped[str | None] = mapped_column(String(64))
    bandit_action: Mapped[str | None] = mapped_column(String(64))
    mode: Mapped[str | None] = mapped_column(String(32))
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    explored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
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
        Index("ix_bandit_logs_created", "created_at"),
        Index("ix_bandit_logs_action", "action"),
        Index("ix_bandit_logs_mode", "mode"),
    )
