"""Core types and the :class:`ProductDataProvider` protocol (CP4)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ProviderCapability(StrEnum):
    """What a concrete provider can actually answer.

    Callers check ``capability in provider.capabilities`` before dispatching so a
    thin source (search-only, or price-only) never has to raise
    :class:`NotImplementedError` on a method it cannot serve.
    """

    search = "search"
    get_product = "get_product"
    get_offers = "get_offers"
    get_price = "get_price"
    price_history = "price_history"


class ProviderError(RuntimeError):
    """A provider call failed for an operational reason (transport, auth, quota).

    Distinct from "the product simply isn't in this source" — that is
    :class:`ProviderProductNotFound`, a subclass callers may treat as an empty
    result rather than an error.
    """


class ProviderProductNotFound(ProviderError):
    """The source has no record for the requested provider id."""


class ProviderProduct(BaseModel):
    """A product as a single source describes it — not yet canonicalised."""

    provider: str
    provider_product_id: str
    title: str
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    market: str
    currency: str
    # identifier_type -> value, e.g. {"asin": "B0...", "upc": "0842..."} — upper-cased.
    identifiers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderOffer(BaseModel):
    """One buyable offer for a product from a single merchant/seller."""

    provider: str
    provider_product_id: str
    merchant: str
    price_cents: int | None = None
    shipping_cents: int | None = None
    currency: str
    availability: str = "unknown"
    condition: str = "new"
    is_buy_box: bool = False
    url: str | None = None
    observed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_cents(self) -> int | None:
        """Price plus shipping, when a price is known."""

        if self.price_cents is None:
            return None
        return self.price_cents + max(self.shipping_cents or 0, 0)


class ProviderPrice(BaseModel):
    """The current effective price for a product from one source.

    ``list_price_cents`` is the merchant's *stated* list / RRP when the source
    reports one. It is never a computed "was" price and must not be turned into a
    discount percentage — the decision engine derives cheap/expensive from
    observed history, not from a merchant's strike-through claim.
    """

    provider: str
    provider_product_id: str
    price_cents: int | None = None
    list_price_cents: int | None = None
    currency: str
    availability: str = "unknown"
    observed_at: datetime
    # Where the number came from, e.g. "keepa:buy_box" / "keepa:amazon".
    source: str
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderPricePoint(BaseModel):
    """One historical price observation."""

    observed_at: datetime
    price_cents: int
    # "amazon" | "new" | "used" | "buy_box" | "sale" — the series this point is on.
    kind: str = "unknown"


class ProviderPriceHistory(BaseModel):
    """A time-ordered price series for a product from one source."""

    provider: str
    provider_product_id: str
    currency: str
    points: list[ProviderPricePoint] = Field(default_factory=list)
    covers_from: datetime | None = None
    covers_to: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ProductDataProvider(Protocol):
    """Read-side adapter over an external product/price source.

    Implementations are queried on demand and must not touch the database. Every
    method may raise :class:`ProviderError` on an operational failure; lookups for
    an unknown id return ``None`` / ``[]`` (or raise
    :class:`ProviderProductNotFound`, which callers may catch as an empty result).
    """

    name: str
    market: str
    currency: str
    capabilities: frozenset[ProviderCapability]

    def is_configured(self) -> bool:
        """True when the adapter has what it needs to make live calls."""

    async def search_products(self, query: str, *, limit: int = 10) -> list[ProviderProduct]:
        """Candidate products for a free-text query, best match first."""

    async def get_product(self, provider_product_id: str) -> ProviderProduct | None:
        """The canonical record for a provider id, or ``None`` if unknown."""

    async def get_offers(self, provider_product_id: str) -> list[ProviderOffer]:
        """Every buyable offer visible for the product."""

    async def get_price(self, provider_product_id: str) -> ProviderPrice | None:
        """The single current effective price, or ``None`` if unavailable."""

    async def get_price_history(
        self,
        provider_product_id: str,
        *,
        days: int = 180,
    ) -> ProviderPriceHistory | None:
        """Historical observations for the trailing ``days``, when kept."""
