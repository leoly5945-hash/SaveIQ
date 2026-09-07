"""CP15 — user-facing product tracking + price alerts.

Separate from the affiliate ``price_history`` chain (which is keyed to
``merchant_listings`` from the ingestion pipeline). These tables track products a
*user* asked us to watch — usually by pasting a URL — and the alerts they set on
them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.affiliate import TimestampMixin, enum_column


class AlertKind(StrEnum):
    any_drop = "any_drop"  # fires when the price falls below the baseline
    below = "below"  # fires when the price is <= threshold_cents
    at_or_below_average = "at_or_below_average"  # fires at/under the 90-day average


class AlertStatus(StrEnum):
    active = "active"
    fired = "fired"
    paused = "paused"
    unsubscribed = "unsubscribed"


class TrackedProduct(Base, TimestampMixin):
    __tablename__ = "tracked_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_product_id: Mapped[str] = mapped_column(String(180), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    product_url: Mapped[str | None] = mapped_column(String(2048))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    observations: Mapped[list[PriceObservation]] = relationship(
        back_populates="tracked_product",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[PriceAlert]] = relationship(
        back_populates="tracked_product",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_product_id",
            "market",
            name="uq_tracked_products_provider_id_market",
        ),
    )


class PriceObservation(Base):
    __tablename__ = "price_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracked_product_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    avg90_cents: Mapped[int | None] = mapped_column(Integer)
    verdict: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    tracked_product: Mapped[TrackedProduct] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint(
            "tracked_product_id",
            "observed_at",
            name="uq_price_observations_tracked_observed",
        ),
        Index("ix_price_observations_tracked_observed", "tracked_product_id", "observed_at"),
    )


class PriceAlert(Base, TimestampMixin):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracked_product_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    kind: Mapped[str] = enum_column(AlertKind, default=AlertKind.any_drop)
    threshold_cents: Mapped[int | None] = mapped_column(Integer)
    baseline_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = enum_column(AlertStatus, default=AlertStatus.active)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    tracked_product: Mapped[TrackedProduct] = relationship(back_populates="alerts")

    __table_args__ = (
        Index("ix_price_alerts_tracked", "tracked_product_id"),
        Index("ix_price_alerts_email", "email"),
        Index("ix_price_alerts_status", "status"),
    )
