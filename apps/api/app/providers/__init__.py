"""Product data providers (CP4).

A *product data provider* is a read-side adapter over an external source of
product, offer and price data — Keepa (Amazon price history), a Google Shopping
data vendor, a marketplace affiliate API, or a hand-maintained fixture. It answers
four questions and, when the source supports it, a fifth:

* ``search_products(query)`` — find candidate products for a free-text query.
* ``get_product(id)`` — the canonical product record for a provider id.
* ``get_offers(id)`` — every buyable offer we can see for that product.
* ``get_price(id)`` — the single current effective price.
* ``get_price_history(id)`` — historical observations, when the source keeps them.

This is deliberately separate from
:mod:`app.services.affiliate` (the batch ingestion pipeline that writes
``merchant_listings`` / ``offers`` / ``price_history``). Providers here are
queried on demand — by the URL price-checker (CP6), the decision engine
(CP9-CP11) and scheduled polling — and never write to the database themselves.

Nothing is registered unless it is configured: with no ``KEEPA_API_KEY`` the
default registry is simply empty and callers get ``None`` / an empty list.
"""

from app.providers.base import (
    ProductDataProvider,
    ProviderCapability,
    ProviderError,
    ProviderOffer,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderPricePoint,
    ProviderProduct,
    ProviderProductNotFound,
)
from app.providers.registry import (
    ProviderRegistry,
    build_default_registry,
    get_provider_registry,
    reset_provider_registry_for_tests,
)

__all__ = [
    "ProductDataProvider",
    "ProviderCapability",
    "ProviderError",
    "ProviderOffer",
    "ProviderPrice",
    "ProviderPriceHistory",
    "ProviderPricePoint",
    "ProviderProduct",
    "ProviderProductNotFound",
    "ProviderRegistry",
    "build_default_registry",
    "get_provider_registry",
    "reset_provider_registry_for_tests",
]
