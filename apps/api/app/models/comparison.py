"""Cross-merchant comparison cache (CP7 + DataForSEO).

DataForSEO's Google Shopping data is **task-based** — you POST a query, wait,
then GET the result — so it cannot answer inside a synchronous price-check.
Instead we cache the raw cross-merchant offers per product here: the first check
of a cold product submits a task and returns no comparison; a later check (or the
alert cron) polls the task, stores the offers, and every check after that renders
the comparison from this table.

Stored offers are the *raw* per-merchant rows (merchant/price/url/title). CP7
matching runs fresh on every read so the "cheaper?" call stays correct as the
reference (Amazon) price moves.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.models.affiliate import TimestampMixin, enum_column


class ComparisonStatus(StrEnum):
    pending = "pending"  # a DataForSEO task is in flight
    ready = "ready"  # offers_json is populated and not yet expired
    failed = "failed"  # the task errored or never completed — give up until refresh


class MerchantComparison(Base, TimestampMixin):
    __tablename__ = "merchant_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The reference product these offers compare against (the pasted Amazon item).
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_product_id: Mapped[str] = mapped_column(String(180), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)

    status: Mapped[str] = enum_column(ComparisonStatus, default=ComparisonStatus.pending)
    keyword: Mapped[str | None] = mapped_column(String(512))
    task_id: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    # list[{merchant, price_cents, shipping_cents, currency, url, title}]
    offers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_product_id",
            "market",
            name="uq_merchant_comparisons_provider_id_market",
        ),
        Index("ix_merchant_comparisons_status", "status"),
    )
